# ComfyUI Integration — Local Image Generation

> Zero cloud API costs for image generation.

## Setup

ComfyUI runs on EUREKAI at `http://192.168.1.47:8188`.

### API Call

```python
import urllib.request, json

def generate_image(prompt, workflow_api_path="workflow_api.json"):
    """Generate an image via ComfyUI API."""
    with open(workflow_api_path) as f:
        workflow = json.load(f)
    
    # Set prompt in workflow
    workflow["6"]["inputs"]["text"] = prompt  # CLIP Text Encode node
    
    # Queue prompt
    req = urllib.request.Request(
        "http://192.168.1.47:8188/prompt",
        data=json.dumps({"prompt": workflow}).encode(),
        headers={"Content-Type": "application/json"}
    )
    resp = urllib.request.urlopen(req)
    return json.loads(resp.read())
```

### Simple HTTP Request

```bash
# Check system stats
curl http://192.168.1.47:8188/system_stats

# Get available models
curl http://192.168.1.47:8188/object_info

# Queue a prompt (via simple API)
curl -X POST http://192.168.1.47:8188/prompt \
  -H "Content-Type: application/json" \
  -d '{"prompt": {"6": {"inputs": {"text": "a cat"}, "class_type": "CLIPTextEncode"}}}'
```

## Token Savings

| Approach | Cost | Tokens |
|----------|------|--------|
| DALL-E 3 API | $0.04/image | ~500 API tokens |
| Midjourney API | $0.04/image | ~500 API tokens |
| **ComfyUI local** | **$0 (electricity)** | **~0 API tokens** |

## Workflow Templates

See `workflows/comfyui/` for reusable workflow JSON files:
- `txt2img_basic.json` — basic text-to-image
- `txt2img_hires.json` — with hires fix
- `img2img.json` — image-to-image
- `inpainting.json` — masked inpainting

## Integration with Botte Secrète

ComfyUI complements Hailo-8 in the vision pipeline:

```
Text Prompt → ComfyUI (generation) → Hailo-8 (quality check) → Output
                                                    ↓
                                            Object detection
                                            on generated image
```
