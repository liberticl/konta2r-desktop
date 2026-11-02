# konta2r-desktop

Port desktop (Python) del contador web con **camara local** (sin URL/HLS/archivo).
Detecta y cuenta peatones, bicicletas, autos, motos, buses, camiones,
patinetas y mascotas con YOLO26n (ONNX, 100% offline) y sincroniza con la
API de andeschileong.cl (ver `docs/api.md` en el repo web).

## Instalación rápida en Ubuntu (recomendado)

1. Descarga `releases/linux/konta2r_v0.1.0.deb` (~120 MB).
2. Doble clic al `.deb` → se abre en el instalador de software → **Instalar**.
   (Equivalente en terminal: `sudo apt install ./releases/linux/konta2r_v0.1.0.deb`.)
3. Abre **konta2r** desde el menú de aplicaciones (o doble clic al
   lanzador). La primera vez crea `~/.config/konta2r/` automáticamente.

> El `.deb` instala en `/usr/share/konta2r/` (app auto-contenida, no
> requiere Python del sistema) y deja el lanzador en `/usr/bin/konta2r`
> más el acceso directo con icono en el menú.

## Familias Linux compatibles

El binario `.deb` está compilado para **x86_64 + glibc** (Ubuntu 24.04).
Funciona tal cual en:

| Familia | Versiones probadas / esperadas | Notas |
|---|---|---|
| Ubuntu | 22.04 LTS, 24.04 LTS | Soporte principal (`.deb` + doble clic). |
| Derivados directos de Ubuntu | Linux Mint 21/22, Pop!\_OS 22.04/24.04, Zorin OS 17/18, elementary OS 7/8, Kubuntu/Xubuntu/Lubuntu 22.04/24.04 | Mismo formato `.deb` y mismas librerías base; instalar igual que en Ubuntu. |
| Debian | 12 (bookworm) | Compatible: mismo `.deb` (`sudo apt install ./konta2r_*.deb`). Requiere escritorio con X11 o Wayland. |
| Otras x86_64 con glibc ≥ 2.35 | Fedora 38+, openSUSE Leap 15.5+/Tumbleweed, Arch/Manjaro | No hay `.deb`; convertir con `alien` o correr el binario de `dist/` directo. |

**No compatibles con este binario:**

| Caso | Alternativa |
|---|---|
| Raspberry Pi OS (ARM64) | Ver sección *Raspberry Pi* más abajo (bundle ARM64, no usar el `.deb` x86_64). |
| Distros musl (Alpine, postmarketOS) | Correr desde Python (ver abajo). |
| 32 bits (i386/armhf) | Correr desde Python en equipo de 64 bits, o compilar nativo. |
| Sin entorno gráfico | La app exige pantalla (Tk). En servidores, usar X-forwarding o una sesión con escritorio. |

## Ejecutar desde Python (otros Linux)

Para cualquier distro x86_64/ARM64 con Python 3.11+ y escritorio:

```bash
# 1. Clonar y entrar
git clone <repo> konta2r-desktop && cd konta2r-desktop

# 2. Python 3.11
pyenv install 3.11.18
pyenv virtualenv 3.11.18 konta2r
pyenv local konta2r
# Alternativa sin pyenv: python3 -m venv .venv && source .venv/bin/activate

# 3. Tkinter (obligatorio para la ventana; si falta, la app lo indica al abrir)
#    Debian/Ubuntu/Raspbian: sudo apt install python3-tk
#    Fedora:                 sudo dnf install python3-tkinter
#    Arch:                   sudo pacman -S tk
#    Con pyenv hay que tener libtk8.6-dev instalado ANTES de compilar Python.

# 4. Dependencias (en ARM usar requirements-pi.txt)
pip install -r requirements.txt        # x86_64
# pip install -r requirements-pi.txt   # Raspberry Pi OS 64-bit

# 5. Modelos (no se versionan por peso)
mkdir -p models
cp /ruta/al/repo-web/.../mediciones/models/yolo26n-320.onnx models/
cp /ruta/al/repo-web/.../mediciones/models/yolo26n.onnx models/
# (ver detalle técnico en models/README.md)

# 6. Ejecutar
python -m konta2r
```

## Windows (10/11 de 64 bits)

### Instalación con ejecutable

1. Descarga `releases/windows/konta2r_vX.Y.Z.exe` (se publica solo
   junto a cada release de GitHub; lo compila automáticamente
   Actions en Windows real con Python 3.11).
2. Doble clic para abrir. La primera vez, Windows SmartScreen puede
   advertir porque el `.exe` no está firmado digitalmente:
   *Más información → Ejecutar de todas formas*.
3. No requiere instalación ni Python: lleva intérprete, modelo y
   dependencias dentro. Los datos quedan en `%APPDATA%\konta2r\` y
   fotos/videos/CSV en `%USERPROFILE%\konta2r\`.

### Correr desde Python

```powershell
# 1. Instala Python 3.11 desde python.org (marca "Add python.exe to PATH";
#    ya incluye Tcl/Tk, no hay que instalar nada extra para la ventana)
# 2. En una terminal, desde la carpeta del repo:
py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
mkdir models
# 3. Modelos: cópialos del repo web o descárgalos (ver models/README.md):
#    https://andeschileong.cl/recursos/mediciones/contador/model/?size=320
#    https://andeschileong.cl/recursos/mediciones/contador/model/
# 4. Ejecutar
python -m konta2r
```

Notas Windows: requiere Windows 10/11 de 64 bits. Las cámaras se listan
como `0 · Cámara 0`, etc. (nombres genéricos de DirectShow; opcional:
`pip install pygrabber` para ver nombres reales). Si `onnxruntime` no
carga por DLL faltante, instala *Microsoft Visual C++ Redistributable*
(x64) y reintenta.

## Raspberry Pi (ARM64, Raspberry Pi OS 64-bit)

El `.deb` de Ubuntu **no sirve** en la Pi (x86_64 vs ARM64). Opciones:

**A. Bundle ARM64** (cuando se publique en `releases/rpi/`):
descomprime `konta2r-rpi-arm64.tar.gz` y ejecuta el binario `konta2r`.
Es un onedir de PyInstaller compilado para aarch64, con todo incluido.

**B. Compilar nativo en la Pi** (recomendado si el bundle no existe
para tu versión):

```bash
# Raspberry Pi OS 64-bit con escritorio (Lite no sirve: no hay GUI)
sudo apt install python3-tk python3-dev libgl1 build-essential
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-pi.txt   # wheels ARM64 (onnxruntime, headless cv2)
# modelos en models/ (ver models/README.md) y luego:
python -m konta2r
```

Notas Raspberry Pi (probado en Pi 4B):

* **Usa siempre el modelo 320** (viene sugerido por defecto): el 640
  da ~1–3 fps y el conteo deja de ser fiable (ver `models/README.md`).
* Cierra otras aplicaciones: inferencia + video compiten por los
  4 cores. Si grabas video, pon *Grabar 1 de cada N* en 2 o 3.
* Cámara: las USB funcionan directo (V4L2, se listan con nombre).
  El módulo de cámara oficial (Pi Camera) usa el stack libcamera y
  **no** aparece como `/dev/video` clásico: para ese caso se
  recomienda una webcam USB.
* La primera ejecución genera fingerprint y registra el equipo igual
  que en PC; sin internet queda encolado y sincroniza al reconectar.

Config: Linux `~/.config/konta2r/config.json`, Windows `%APPDATA%/konta2r`.
DB y log en la misma carpeta. Fotos/videos/CSV en `~/konta2r/`.
Idiomas: español, inglés, portugués (Config, aplica al guardar).
Tema claro/oscuro: Config, aplica al guardar.

## Compilar (crear el ejecutable y el `.deb`)

Probado en Ubuntu 24.04 x64, Python 3.11 (pyenv). El resultado sale en
`dist/konta2r/` (~350 MB, app + intérprete + modelos incluidos).

```bash
# 1. Entorno y dependencias
pyenv virtualenv 3.11.18 konta2r && pyenv local konta2r
pip install -r requirements.txt
~/.pyenv/versions/konta2r/bin/pip install pyinstaller
# (usar el pip del virtualenv, no el del sistema)

# 2. Modelos en models/ (ver paso 5 anterior)

# 3. Compilar con el spec del repo (onedir + GUI sin consola)
pyinstaller build/konta2r.spec
./dist/konta2r/konta2r   # prueba: debe abrir la ventana y cargar el modelo

# 4. Armar el .deb (requiere dpkg-deb; fakeroot opcional)
./build/deb-build.sh            # genera releases/linux/konta2r_v0.1.0.deb
./build/deb-build.sh 0.2.0      # con otra versión

# 5. (Opcional) revisar contenido e instalar local
dpkg-deb --contents releases/linux/konta2r_v0.1.0.deb | head -30
sudo apt install ./releases/linux/konta2r_v0.1.0.deb
```

Notas de compilación:

- El spec (`build/konta2r.spec`) usa rutas absolutas desde `SPECPATH`,
  así que debe invocarse desde la raíz del repo.
- Se empaquetan los `.onnx` (`datas`) y los assets de CustomTkinter
  (`collect_all`); `PIL._tkinter_finder` va en `hiddenimports` (sin eso,
  el binario congela al pegar el primer frame en el canvas).
- El icono sale de `build/deb-icon/konta2r.png` (generado con PIL) y se
  instala en `/usr/share/pixmaps/konta2r.png`.
- Dependencias del sistema declaradas en el `.deb` (`DEBIAN/control`):
  `libgl1, libglib2.0-0, libv4l-0 | libv4l2-0` — el resto va empaquetado.
- Para Raspberry Pi OS 64-bit, compilar **nativo en la Pi**
  (`pip install -r requirements-pi.txt` + mismo spec); el binario x86_64
  no sirve en ARM y viceversa. Usar modelo 320 en la Pi.

## Plataformas (módulo `konta2r/platform.py`)

| Tema | Ubuntu | Raspberry Pi OS | Windows |
|---|---|---|---|
| Cámara | V4L2, nombres vía `v4l2-ctl`/sysfs | Igual que Ubuntu | DirectShow, nombres genéricos (`pygrabber` opcional para nombres) |
| Enumeración | solo nodos existentes en sysfs, sin reabrir la cámara en uso, sin ruido en log | igual | 0-5 (cada fallo MSMF es lento) + `CAP_DSHOW` |
| Modelo inicial | 640px (RAM>2GB) | 320px siempre | 640px (RAM>2GB) |
| Inferencia | CPU, máx 4 hilos | CPU, máx 4 hilos | CPU, máx 4 hilos |
| Tkinter | `sudo apt install python3-tk` (con pyenv: `libtk8.6-dev` y recompilar) | `sudo apt install python3-tk` | incluido en python.org |
| Sin pantalla | error claro (usa escritorio o X-forwarding) | igual (Lite no corre GUI) | n/a |

Todo el estado UI corre en el hilo de Tk (`after`); el watcher de red es
1 hebra + 1 socket cada 20s. Para emular otra plataforma:
`KONTA2R_PLATFORM=linux|rpi|windows`.

## API

- `POST /api/trafico/register/` auto-registro (fingerprint SHA256 máquina+coords). Guarda el token.
- `POST /api/trafico/` un registro por evento con su `datetime` real (offline-first: cola SQLite, envía pendientes al reconectar).
- Con línea: `line {x1,y1,x2,y2}` + `direction_counts {a_to_b, b_to_a}` (consistentes con el total) + `side_names {a, b}` opcional.
- `PATCH /api/trafico/device/` renombrar.
- Si el token expira (401/403), re-registra automáticamente.
