#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
REPO_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)

mkdir -p "$REPO_DIR/dist"
cd "$REPO_DIR"

zip -qr dist/plugin.zip \
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
    -x '*/__pycache__/*' '*.pyc' '.DS_Store'

echo "built dist/plugin.zip"
