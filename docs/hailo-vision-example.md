# Haio-8 Vision — exemple bout-en-bout

Pipeline complet de classification d'image avec Hailo-8 sur EUREKAI.

## Prérequis
- Hailo-8 branché sur EUREKAI (192.168.1.47)
- Service Python sur :8767
- Rust backend sur :8769

## Exemple

```bash
# 1. Vérifier que le Hailo-8 est prêt
curl http://192.168.1.47:8769/health
# {"status":"ok","hailo":"connected","models":["resnet18","yolov8","ocr"]}

# 2. Classifier une image
curl -F "file=@photo.jpg" http://192.168.1.47:8767/classify
# {"predictions":[{"class":"golden_retriever","confidence":0.94},...]}

# 3. Détecter des objets
curl -F "file=@photo.jpg" http://192.168.1.47:8767/detect
# {"objects":[{"label":"dog","bbox":[10,20,200,300],"confidence":0.92},...]}

# 4. OCR
curl -F "file=@document.jpg" http://192.168.1.47:8767/ocr
# {"text":"Hello World\nLine 2..."}
```

## Intégration Hermes
Via le MCP server hailo_vision :
- `hailo_classify(image_path)` → top-5 predictions
- `hailo_detect(image_path)` → bounding boxes
- `hailo_ocr(image_path)` → texte extrait
- `hailo_status()` → état device

Voir `skills/hermes_bridge/` pour le mapping des outils MCP → Hermes.
