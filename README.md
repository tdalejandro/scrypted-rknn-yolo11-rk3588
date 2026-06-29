# scrypted-rknn-yolo11-rk3588

Community fork/patch of the Scrypted Rockchip RKNN object detection plugin.

This version targets RK3588 and uses:

- `rknn_toolkit_lite2 2.3.2`
- `librknnrt.so 2.3.2`
- YOLO11n RKNN model
- static input shape `960x544`
- default `SCRYPTED_RKNN_MAX_WORKERS=4`
- filtered static-shape RKNN dynamic-range warnings during runtime init

## Status

Tested on:

- Scrypted `0.143.0`
- Rockchip RK3588
- Linux ARM64
- RKNN driver `0.9.8`
- RKNN model version `6`

Observed production log:

```text
Using model .../yolo11n_rk3588_optimized.rknn (contenido: YOLO11n 960x544)
RKNN Runtime Information, librknnrt version: 2.3.2
RKNN Driver Information, version: 0.9.8
RKNN Model Information, version: 6, toolkit version: 2.3.2
model inference type: static_shape
```

## Model

Expected model filename:

```text
yolo11n_rk3588_optimized.rknn
```

The plugin downloads the model from:

```text
https://github.com/tdalejandro/scrypted-rknn-yolo11-rk3588/releases/download/v0.1.0/yolo11n_rk3588_optimized.rknn
```

Recommended checksum for the tested 960x544 model:

```text
sha256 f0ef2a43d4e9bc3ac56b9b2da2d02b60a3826887d624b9924da31539b74feeae
```

Do not publish private camera images, RTSP URLs, Scrypted backups, or credentials.

## Notes

This is not an official Scrypted plugin release. Treat it as a community patch/fork for testing on RK3588.

Review the licenses of Scrypted, Rockchip RKNN tooling, RKNN Model Zoo, and Ultralytics YOLO11 before publishing binaries or trained/exported model artifacts.
