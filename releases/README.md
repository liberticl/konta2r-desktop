# Releases por sistema

Binarios listos para instalar/usar, uno por plataforma.
Los genera CI o el script correspondiente (no se versionan en git
los binarios grandes; este directorio conserva solo la estructura).

| Carpeta | Artefacto | Cómo se genera |
|---|---|---|
| `linux/` | `konta2r_vX.Y.Z.deb` (amd64) | `./build/deb-build.sh X.Y.Z` en Ubuntu 22.04/24.04 x64 |
| `windows/` | `konta2r_vX.Y.Z.exe` (x64, futuro) | PyInstaller en Windows (`build\konta2r.spec`) |
| `macos/` | `konta2r_vX.Y.Z.dmg` (arm64/x64, futuro) | PyInstaller en macOS |
| `rpi/` | `konta2r_vX.Y.Z_arm64.deb` (futuro) | `pyinstaller build/konta2r.spec` nativo en Raspberry Pi OS 64-bit + `deb-build.sh` adaptado a `ARCH=arm64` |

Formato de nombre: `konta2r_vX.Y.Z` + extensión del instalador
(`.deb`, `.exe`, `.dmg`). La arquitectura se deduce de la carpeta
(`rpi` = ARM64, resto = x64), salvo que el nombre la indique.
