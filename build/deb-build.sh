#!/bin/bash
# Arma el .deb de konta2r para Ubuntu amd64.
# Uso:  ./build/deb-build.sh [VERSION]     (default 0.1.0)
# Requiere: dist/konta2r/ ya compilado (pyinstaller build/konta2r.spec),
#           dpkg-deb, fakeroot (opcionales pero recomendados).
set -euo pipefail
cd "$(dirname "$0")/.."

VERSION="${1:-0.1.0}"
ARCH="amd64"
PKG="konta2r_${VERSION}_${ARCH}"
WORK="build/deb-pkg/${PKG}"

[ -x dist/konta2r/konta2r ] || {
  echo "ERROR: falta dist/konta2r/konta2r. Primero: pyinstaller build/konta2r.spec" >&2
  exit 1
}

rm -rf "${WORK}"
mkdir -p "${WORK}"/DEBIAN \
         "${WORK}"/usr/bin \
         "${WORK}"/usr/share/konta2r \
         "${WORK}"/usr/share/applications \
         "${WORK}"/usr/share/pixmaps \
         "${WORK}"/usr/share/doc/konta2r

cp -r dist/konta2r "${WORK}/usr/share/konta2r/konta2r"
cp build/konta2r-launcher.sh "${WORK}/usr/bin/konta2r"
cp build/konta2r.desktop "${WORK}/usr/share/applications/konta2r.desktop"
cp build/deb-icon/konta2r.png "${WORK}/usr/share/pixmaps/konta2r.png"
cp README.md "${WORK}/usr/share/doc/konta2r/README.md"
[ -x "${WORK}/usr/bin/konta2r" ] || chmod +x "${WORK}/usr/bin/konta2r"
find "${WORK}/usr/share/konta2r/konta2r" -type f -name "konta2r" -exec chmod +x {} \;
chmod 644 "${WORK}/usr/share/applications/konta2r.desktop"

# Nombres -0t64 en Ubuntu 24.04 / Debian 13; sin sufijo en 22.04 / Debian 12.
cat > "${WORK}/DEBIAN/control" <<EOF
Package: konta2r
Version: ${VERSION}
Section: science
Priority: optional
Architecture: ${ARCH}
Maintainer: liberticl <liberticl@users.noreply.github.com>
Depends: libgl1, libglib2.0-0 | libglib2.0-0t64, libv4l-0 | libv4l-0t64
Description: Conteo de tránsito con visión artificial (cámara local)
 Detecta y cuenta peatones, bicicletas, autos, motos, buses, camiones,
 patinetas y mascotas desde una cámara local con YOLO26n (ONNX,
 ejecución 100% offline). Sincroniza con la API de andeschileong.cl.
EOF

if command -v fakeroot >/dev/null; then
  fakeroot dpkg-deb --build "${WORK}" "build/${PKG}.deb"
else
  dpkg-deb --build "${WORK}" "build/${PKG}.deb"
fi
echo "OK: build/${PKG}.deb"
dpkg-deb --info "build/${PKG}.deb"
dpkg-deb --contents "build/${PKG}.deb" | wc -l
