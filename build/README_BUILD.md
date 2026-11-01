# Build

## Ubuntu x64
```bash
pip install -r requirements.txt pyinstaller
pyinstaller build/konta2r.spec
./dist/konta2r/konta2r
```

## Raspbian Pi4B
1. Emulado (test x86): `docker buildx build --platform linux/arm64 -f build/Dockerfile.pi --load .`
   con qemu-aarch64 (`docker run --rm --privileged multiarch/qemu-user-static --reset -p yes`).
2. Nativo ARM solo en release: en la Pi4B con Raspberry Pi OS 64-bit:
```bash
pip install -r requirements-pi.txt pyinstaller
pyinstaller build/konta2r.spec
```
Usar modelo 320 (`"model_size": 320` en config) en Pi4B por RAM/CPU.

## Windows
```bash
pip install -r requirements.txt pyinstaller
pyinstaller build\konta2r.spec
dist\konta2r\konta2r.exe
```

Onefile windowed: el spec usa `console=False`; para onefile cambia a
`EXE(..., exclude_binaries=False)` o `pyinstaller --onefile --windowed -n konta2r konta2r/__main__.py`.
