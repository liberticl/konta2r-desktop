# Logo oficial konta2r

Adoptado nov-2026. K blanca inscrita en anillo-rueda; la flecha roja perfora
el anillo (el cruce = evento contado); lente con reflejo en el mástil.

## Archivos

| Archivo | Uso |
|---|---|
| `konta2r-logo.svg` | Lockup oficial con wordmark (documentos, web, presentaciones) |
| `konta2r-icon.svg` | Fuente maestra del icono (solo icono, 256×256) |
| `konta2r-icon-512.png` | Icono app 512px (sincronizado con `build/deb-icon/konta2r.png`, lo usa `konta2r.spec`) |
| `konta2r-icon-48.png` | Icono 48px (sincronizado con `build/deb-icon/konta2r-48.png`, va a `/usr/share/pixmaps`) |

## Paleta

| Elemento | Color | Origen |
|---|---|---|
| Fondo | `#245A91` | PUCV PANTONE 2945 U (RGB 36,90,145) |
| K + anillo | blanco | Norma PUCV: monocromo sobre fondo a color |
| Flecha | `#A6192E` | PUCV PANTONE 1807, equivalente digital |
| Aro interior | `#9C7C3C` | PUCV dorado 873, aprox. plana (el metálico no tiene equivalente exacto) |
| Lente | `#0A2A4A` | Pupila + brillo arriba-izquierda (convención de reflejo) |
| Wordmark `konta` | `#2241A8` | Azul marca andeschileong.cl (`hugo_site/assets/css/main.css`) |
| Wordmark `2r` | `#A6192E` | Rojo PUCV = las dos direcciones A→B / B→A |

## Regenerar PNG

```bash
inkscape assets/logo/konta2r-icon.svg --export-type=png --export-filename=build/deb-icon/konta2r.png -w 512
inkscape assets/logo/konta2r-icon.svg --export-type=png --export-filename=build/deb-icon/konta2r-48.png -w 48
```
