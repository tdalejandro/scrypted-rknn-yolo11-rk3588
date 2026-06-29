import asyncio
import concurrent.futures
import io
import os
import platform
import sys
import threading
import traceback
from typing import Any, Coroutine, List, Tuple
import urllib.request

import numpy as np
from PIL.Image import Image
from rknnlite.api import RKNNLite

from predict import PredictPlugin, Prediction
from predict.rectangle import Rectangle

import scrypted_sdk
from scrypted_sdk import DeviceProvider, ScryptedDeviceType, ScryptedInterface

# for Rockchip-optimized models, the postprocessing is slightly different from the original models
from .optimized.yolo import post_process, IMG_SIZE, CLASSES

from .text_recognition import TEXT_RECOGNITION_NATIVE_ID, TextRecognition


rknn_verbose = False
lib_download = 'https://github.com/airockchip/rknn-toolkit2/raw/v2.3.2/rknpu2/runtime/Linux/librknn_api/aarch64/librknnrt.so'
model_download_tmpl = 'https://github.com/tdalejandro/scrypted-rknn-yolo11-rk3588/releases/download/v0.1.0/{}_{}_optimized.rknn'
lib_path = '/usr/lib/librknnrt.so'
DEFAULT_MAX_WORKERS = 4
stderr_filter_lock = threading.Lock()


def ensure_compatibility_and_get_cpu():
    err_msg = 'RKNN plugin is only supported on Linux/ARM64 platform with a Rockchip CPU'
    if platform.machine() != 'aarch64':
        raise RuntimeError(err_msg)

    if platform.system() != 'Linux':
        raise RuntimeError(err_msg)

    try:
        with open('/proc/device-tree/compatible') as f:
            device_compatible_str = f.read()
            if 'rk3562' in device_compatible_str:
                return 'rk3562'
            elif 'rk3566' in device_compatible_str:
                return 'rk3566'
            elif 'rk3568' in device_compatible_str:
                return 'rk3568'
            elif 'rk3576' in device_compatible_str:
                return 'rk3576'
            elif 'rk3588' in device_compatible_str:
                return 'rk3588'
            else:
                raise RuntimeError(err_msg)
    except IOError as e:
        print('Failed to read /proc/device-tree/compatible: {}'.format(e))
        print('If you are running this via Docker, ensure you are launching the container with --privileged option')
        raise


def parse_int(value, default, minimum=None, maximum=None):
    try:
        ret = int(value)
    except (TypeError, ValueError):
        ret = default
    if minimum is not None:
        ret = max(ret, minimum)
    if maximum is not None:
        ret = min(ret, maximum)
    return ret


class FilteredStderr(io.TextIOBase):
    ignored_patterns = (
        'RKNN_QUERY_INPUT_DYNAMIC_RANGE',
        'RKNN_ERR_MODEL_INVALID',
        'If it is a static shape RKNN model, please ignore',
    )


def init_runtime_quiet(rknn):
    with stderr_filter_lock:
        read_fd, write_fd = os.pipe()
        saved_stdout_fd = os.dup(1)
        saved_stderr_fd = os.dup(2)
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(write_fd, 1)
        os.dup2(write_fd, 2)
        os.close(write_fd)
        try:
            ret = rknn.init_runtime()
        finally:
            sys.stdout.flush()
            sys.stderr.flush()
            os.dup2(saved_stdout_fd, 1)
            os.dup2(saved_stderr_fd, 2)
            os.close(saved_stdout_fd)
            os.close(saved_stderr_fd)
            with os.fdopen(read_fd, 'rb') as reader:
                captured = reader.read().decode(errors='replace').splitlines()

        for line in captured:
            if not any(pattern in line for pattern in FilteredStderr.ignored_patterns):
                print(line)
        return ret


class RKNNPlugin(PredictPlugin, DeviceProvider):
    labels = {i: CLASSES[i] for i in range(len(CLASSES))}
    rknn_runtimes: dict
    executor: concurrent.futures.ThreadPoolExecutor
    text_recognition: TextRecognition = None
    cpu: str

    def __init__(self, nativeId=None):
        super().__init__(nativeId)
        self.cpu = ensure_compatibility_and_get_cpu()
        self.modelName = 'yolo11n'

        self.rknn_runtimes = {}
        self.max_workers = parse_int(os.environ.get('SCRYPTED_RKNN_MAX_WORKERS'), DEFAULT_MAX_WORKERS, 1, 4)
        print('RKNN max workers: {}'.format(self.max_workers))

        if not os.path.exists(lib_path):
            installation = os.environ.get('SCRYPTED_INSTALL_ENVIRONMENT')
            if installation in ('docker', 'lxc'):
                print('Downloading librknnrt.so from {}'.format(lib_download))
                urllib.request.urlretrieve(lib_download, lib_path)
            else:
                raise RuntimeError('librknnrt.so not found. Please download it from {} and place it at {}'.format(lib_download, lib_path))

        model_download = model_download_tmpl.format(self.modelName, self.cpu)
        model_file = os.path.basename(model_download)
        model_path = self.downloadFile(model_download, model_file)
        print('Using model {} (contenido: YOLO11n 960x544)'.format(model_path))

        test_rknn = RKNNLite(verbose=rknn_verbose)
        ret = test_rknn.load_rknn(model_path)
        if ret != 0:
            raise RuntimeError('Failed to load model: {}'.format(ret))

        ret = init_runtime_quiet(test_rknn)
        if ret != 0:
            raise RuntimeError('Failed to init runtime: {}'.format(ret))
        test_rknn.release()

        def executor_initializer():
            thread_name = threading.current_thread().name
            rknn = RKNNLite(verbose=rknn_verbose)
            ret = rknn.load_rknn(model_path)
            if ret != 0:
                raise RuntimeError('Failed to load model: {}'.format(ret))

            ret = init_runtime_quiet(rknn)
            if ret != 0:
                raise RuntimeError('Failed to init runtime: {}'.format(ret))

            self.rknn_runtimes[thread_name] = rknn
            print('RKNNLite runtime initialized on thread {}'.format(thread_name))

        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix=type(self).__name__, initializer=executor_initializer)

        asyncio.create_task(self.discoverRecognitionModels())

    async def discoverRecognitionModels(self) -> None:
        devices = [
            {
                "nativeId": TEXT_RECOGNITION_NATIVE_ID,
                "name": "Rockchip NPU Text Recognition",
                "type": ScryptedDeviceType.API.value,
                "interfaces": [
                    ScryptedInterface.ObjectDetection.value,
                ],
            }
        ]
        await scrypted_sdk.deviceManager.onDevicesChanged({
            "devices": devices,
        })

    async def getDevice(self, nativeId: str) -> TextRecognition:
        try:
            if nativeId == TEXT_RECOGNITION_NATIVE_ID:
                self.text_recognition = self.text_recognition or TextRecognition(nativeId, self.cpu)
                return self.text_recognition
        except:
            traceback.print_exc()
            raise

    def get_input_details(self) -> Tuple[int]:
        return (IMG_SIZE[0], IMG_SIZE[1], 3)

    def get_input_size(self) -> Tuple[int, int]:
        return IMG_SIZE

    async def detect_once(self, input: Image, settings: Any, src_size, cvss) -> Coroutine[Any, Any, Any]:
        def inference(input_tensor):
            rknn = self.rknn_runtimes[threading.current_thread().name]
            outputs = rknn.inference(inputs=[input_tensor])
            return outputs

        async def predict(input_tensor):
            fut = asyncio.wrap_future(self.executor.submit(inference, input_tensor))
            outputs = await fut
            boxes, classes, scores = post_process(outputs)

            predictions: List[Prediction] = []
            for i in range(len(classes)):
                #print(CLASSES[classes[i]], scores[i])
                predictions.append(Prediction(
                    classes[i],
                    float(scores[i]),
                    Rectangle(float(boxes[i][0]), float(boxes[i][1]), float(boxes[i][2]), float(boxes[i][3]))
                ))

            return self.create_detection_result(predictions, src_size, cvss)
        input_tensor = np.expand_dims(np.asarray(input), axis=0)
        return await predict(input_tensor)
