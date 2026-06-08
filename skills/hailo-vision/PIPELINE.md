# Hailo-8 Vision Pipeline

> Edge AI vision — zero cloud API costs, 15W TDP.

## Available Models

| Model | Task | Speed |
|-------|------|-------|
| `yolov8m.hef` | Object detection | 30+ FPS |
| `yolov5m_wo_spp_60p.hef` | Object detection (alt) | 30+ FPS |
| `resnet_v1_18.hef` | Image classification | 60+ FPS |
| `ssd_mobilenet_v1.hef` | Lightweight detection | 60+ FPS |
| `nanodet_repvgg.hef` | Nano detection | 60+ FPS |
| `paddle_ocr_v5_mobile_detection.hef` | OCR text detection | 30+ FPS |
| `paddle_ocr_v5_mobile_recognition.hef` | OCR text recognition | 30+ FPS |
| `shortcut_net.hef` | Classification | 60+ FPS |
| `shortcut_net_nv12.hef` | Classification (NV12) | 60+ FPS |
| `multi_network_shortcut_net.hef` | Multi-network | 30+ FPS |

## API Usage

### Detection (YOLOv8)

```python
from hailo_vision import detect

results = detect(
    image_path="photo.jpg",
    model="yolov8m.hef",
    confidence=0.5
)
# Returns: [{"label": "person", "confidence": 0.92, "bbox": [x1,y1,x2,y2]}, ...]
```

### Classification (ResNet-18)

```python
from hailo_vision import classify

results = classify(
    image_path="photo.jpg",
    top_k=5
)
# Returns: [{"label": "tabby cat", "confidence": 0.87}, ...]
```

### OCR (PaddleOCR v5)

```python
from hailo_vision import ocr

text = ocr(
    image_path="document.jpg",
    lang="fr+en"
)
# Returns: [{"text": "Hello", "confidence": 0.95, "bbox": [x1,y1,x2,y2]}, ...]
```

## MCP Integration

When running on EUREKAI (192.168.1.47), the Hailo-8 MCP server provides:

```bash
# Classify an image
mcp_hailo_vision_hailo_classify --image_path /tmp/photo.jpg

# Detect objects
mcp_hailo_vision_hailo_detect --image_path /tmp/photo.jpg

# Extract text
mcp_hailo_vision_hailo_ocr --image_path /tmp/document.jpg

# Device status
mcp_hailo_vision_hailo_status
```

## Pipeline: Vision → Knowledge

Hailo-8 vision feeds into the knowledge pipeline:

```
Camera/Image → Hailo-8 Detection → Structured JSON → Qdrant Index
                                              ↓
                                    Token-efficient context
                                    (objects, text, labels)
```

Instead of sending full images to cloud APIs (costing tokens + money),
Hailo-8 extracts structured metadata locally:

- **Before**: Send 2MB image to GPT-4V → 4000 tokens
- **After**: Hailo detects 5 objects → 50 tokens of structured JSON
- **Savings**: ~98% token reduction for vision tasks

## Requirements

- Hailo-8 PCIe module (EUREKAI server)
- HailoRT 4.18+
- Python 3.8+
- `hailo-platform-sdk` package

## Status Check

```python
import urllib.request, json

resp = urllib.request.urlopen("http://192.168.1.47:8767/status")
print(json.loads(resp.read()))
```
