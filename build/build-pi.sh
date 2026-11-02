#!/bin/bash
# Compila konta2r para Raspberry Pi 4B (aarch64) mediante emulación QEMU.
# Uso: ./build/build-pi.sh
# Salida: releases/rpi/konta2r/ (binario + .onnx + Tcl/Tk).
# Tarda 20-60 min en x86 (emulación); en la Pi nativa usar en su lugar:
#   pip install -r requirements-pi.txt pyinstaller && pyinstaller build/konta2r.spec
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f /proc/sys/fs/binfmt_misc/qemu-aarch64 ]; then
  echo "Registrando QEMU aarch64 (requiere privilegios)..."
  docker run --rm --privileged multiarch/qemu-user-static --reset -p yes
fi

docker buildx build --platform linux/arm64 \
  -f build/Dockerfile.pi -t konta2r-pi-builder --load .

CID=$(docker create konta2r-pi-builder)
rm -rf releases/rpi/konta2r
mkdir -p releases/rpi
docker cp "$CID:/src/dist/konta2r" releases/rpi/konta2r
docker rm "$CID" >/dev/null
file releases/rpi/konta2r/konta2r
echo "OK: releases/rpi/konta2r/"
