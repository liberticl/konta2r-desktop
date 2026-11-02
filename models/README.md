# Modelos ONNX — konta2r-desktop

Detección de objetos en tiempo real con **YOLO26n** (variante *nano*),
exportado a ONNX para inferencia local con `onnxruntime` (CPU).
No se requiere GPU ni conexión: todo corre en el equipo.

## Archivos

| Archivo | Tamaño | Entrada | Uso recomendado |
|---|---|---|---|
| `yolo26n-320.onnx` | ~9,8 MB | `images` `[1, 3, 320, 320]` float32 | Raspberry Pi 4B y equipos con ≤ 2 GB libres. Default en instalaciones nuevas con poca RAM. |
| `yolo26n.onnx` | ~9,9 MB | `images` `[1, 3, 640, 640]` float32 | PC de escritorio / Ubuntu x64. Default en el resto. Más detalle a igual escena. |

Ambos comparten arquitectura y pesos equivalentes (tamaño casi idéntico);
difieren en la **resolución de entrada**, no en capacidad del modelo.
El tamaño se elige en Config → *Modelo (320/640)* y aplica sin reiniciar.

## Formato de entrada

1. **Cover-resize + letterbox centrado:** la imagen se escala con
   `scale = max(S/ancho, S/alto)` (recorta lo que sobresale) y se centra
   en un canvas `S×S` (igual que la versión web del contador).
2. **Conversión:** BGR → RGB, normalizado a `[0, 1]`, layout NCHW `float32`.
3. El tensor se entrega en el input **`images`** con batch 1.

## Formato de salida

Tensor **`output0`** de forma `[1, 300, 6]` (`float32`), sin NMS interno:
cada una de las 300 filas es `[x1, y1, x2, y2, score, classId]`, con
coordenadas en píxeles del modelo (`0…S`).

La app filtra por confianza (`CONF_DEFAULT = 0.50`, ajustable en Config),
redondea `classId` y mapea a contador solo estas 9 clases COCO:

| `classId` | Clase COCO | Contador | Etiqueta |
|---|---|---|---|
| 0 | person | person | peatón |
| 1 | bicycle | bicycle | bicicleta |
| 2 | car | car | auto |
| 3 | motorcycle | motorcycle | moto |
| 5 | bus | bus | bus |
| 7 | truck | truck | camión |
| 15 / 16 | cat / dog | pet | mascota |
| 36 | skateboard | skater | patineta |

El resto de las 80 clases COCO se ignora a propósito: no aporta al
conteo de tránsito y solo sumaría falsos positivos y registros basura.

## Rendimiento orientativo

Medido en CPU con `onnxruntime` (3 hilos efectivos, ver `settings.py`):

| Modelo | PC x64 típico | Raspberry Pi 4B |
|---|---|---|
| 320 | ~10–20 fps | ~5–10 fps (rango útil para conteo) |
| 640 | ~3–8 fps | ~1–3 fps (no apto para medición en vivo) |

Valores aproximados: dependen del CPU, la resolución de cámara y la
carga del sistema. Regla práctica: bajo ~5 fps sostenidos el tracker
pierde cruces y las direcciones `A→B`/`B→A` dejan de ser fiables —
en ese caso, bajar a 320.

## Origen de los archivos

No se versionan en git por peso. Se copian desde el repo web:

```bash
cp /home/francisco/andeschileong/andeschileong-v2/apps/mediciones/static/mediciones/models/yolo26n-320.onnx models/
cp /home/francisco/andeschileong/andeschileong-v2/apps/mediciones/static/mediciones/models/yolo26n.onnx models/
```

Si falta el tamaño pedido al iniciar, la app usa el otro automáticamente
y avisa con un toast (ver `infer.default_model_path`).
