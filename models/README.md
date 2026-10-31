# Modelos ONNX

Copia aqui desde el repo web (no se versionan por peso):
```
cp /home/francisco/andeschileong/andeschileong-v2/apps/mediciones/static/mediciones/models/yolo26n-320.onnx models/
cp /home/francisco/andeschileong/andeschileong-v2/apps/mediciones/static/mediciones/models/yolo26n.onnx models/
```
- `yolo26n-320.onnx` (~9.8 MB): default, recomendado Pi4B.
- `yolo26n.onnx` (640, ~9.9 MB): mejor precision en PC.
Entrada `images` (1,3,S,S) RGB 0-1; salida `output0` [300,6] x1,y1,x2,y2,score,class.
