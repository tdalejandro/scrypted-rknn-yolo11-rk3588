#!/usr/bin/env sh
set -eu

CONTAINER="${SCRYPTED_CONTAINER:-scrypted}"
PLUGIN_DIR="${SCRYPTED_RKNN_PLUGIN_DIR:-/server/volume/plugins/@scrypted/rknn}"
MODEL_NAME="${SCRYPTED_RKNN_MODEL:-yolo11n_rk3588_optimized.rknn}"

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
MODEL_SRC="$REPO_DIR/models/$MODEL_NAME"
REMOTE_TMP="/tmp/scrypted-rknn-yolo11-rk3588-install"
BACKUP_NAME="community-yolo11-install-$(date +%Y%m%dT%H%M%S%z)"

if ! command -v docker >/dev/null 2>&1; then
    echo "docker command not found" >&2
    exit 1
fi

if [ ! -f "$MODEL_SRC" ]; then
    echo "missing model: $MODEL_SRC" >&2
    exit 1
fi

docker exec "$CONTAINER" test -d "$PLUGIN_DIR/zip/unzipped"
docker exec "$CONTAINER" mkdir -p "$PLUGIN_DIR/backups/$BACKUP_NAME" "$PLUGIN_DIR/files" "$REMOTE_TMP"

docker exec "$CONTAINER" cp -a "$PLUGIN_DIR/zip/unzipped" "$PLUGIN_DIR/backups/$BACKUP_NAME/unzipped"
docker exec "$CONTAINER" sh -c "cp -a '$PLUGIN_DIR'/zip/*.zip '$PLUGIN_DIR/backups/$BACKUP_NAME/' 2>/dev/null || true"

tar -C "$REPO_DIR" -cf - \
    README.md \
    requirements.txt \
    main.py \
    common \
    det_utils \
    detect \
    predict \
    rec_utils \
    rknn \
    scrypted_sdk \
    | docker exec -i "$CONTAINER" sh -c "rm -rf '$REMOTE_TMP' && mkdir -p '$REMOTE_TMP' && tar -C '$REMOTE_TMP' -xf -"

docker exec "$CONTAINER" sh -c "cp -a '$REMOTE_TMP'/. '$PLUGIN_DIR/zip/unzipped/'"
docker cp "$MODEL_SRC" "$CONTAINER:$PLUGIN_DIR/files/$MODEL_NAME"

docker exec "$CONTAINER" sh -c "zip_file=\$(find '$PLUGIN_DIR/zip' -maxdepth 1 -name '*.zip' | head -n 1); if [ -n \"\$zip_file\" ] && command -v zip >/dev/null 2>&1; then cd '$PLUGIN_DIR/zip/unzipped' && zip -qr \"\$zip_file\" .; else echo 'warning: zip command not found or zip package missing; patched unzipped tree only'; fi"

echo "installed YOLO11n RKNN patch into $CONTAINER:$PLUGIN_DIR"
echo "backup: $PLUGIN_DIR/backups/$BACKUP_NAME"
echo "restart the Rockchip NPU Object Detection plugin from Scrypted UI"
