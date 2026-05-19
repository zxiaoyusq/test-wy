# AI Character Pipeline Backend

FastAPI backend skeleton for the technical-test prototype.

## Scope

The backend exposes four fixed, independent modules:

- AI character generation
- AI video generation
- Motion capture
- Facial capture

Modules are not auto-orchestrated. Each module creates its own job and writes outputs to local storage. Downstream modules can reference upstream asset IDs, which lets the Vue3 frontend present a fixed step-by-step workflow.

## Tech Stack

- Python 3.13
- FastAPI
- Pydantic v2
- Local JSON metadata and local asset files for the demo
- Reserved production path: PostgreSQL + object storage

## Run

```powershell
cd D:\dev\orders\test\backend
conda activate base
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Health check:

```text
GET http://127.0.0.1:8000/health
```

OpenAPI docs:

```text
http://127.0.0.1:8000/docs
```

## API

```text
GET  /health

GET  /api/assets
GET  /api/assets/{asset_id}
GET  /api/assets/{asset_id}/file

POST /api/character/jobs
GET  /api/character/jobs
GET  /api/character/jobs/{job_id}

POST /api/video/jobs
GET  /api/video/jobs
GET  /api/video/jobs/{job_id}

POST /api/motion/jobs
GET  /api/motion/jobs
GET  /api/motion/jobs/{job_id}

POST /api/facial/jobs
GET  /api/facial/jobs
GET  /api/facial/jobs/{job_id}
```

## Local Data Layout

```text
data/
  jobs/
    job_xxx.json
  assets/
    _index/
      asset_xxx.json
    character/
      job_xxx/
    video/
      job_xxx/
    motion/
      job_xxx/
    facial/
      job_xxx/
  logs/
```

## Provider Strategy

Current implementation uses Qwen-Image for text-to-image character generation, Wan image-to-video for video generation, and mock providers for the remaining unfinished integrations:

- `QwenImageProvider`: calls `qwen-image-2.0-pro`, downloads generated PNG files to local assets
- `WanImageToVideoProvider`: calls `wan2.7-i2v-2026-04-25`, polls the async task, downloads generated MP4 files to local assets
- `MockMotionProvider`
- `MockFacialProvider`

The request and output contracts are shaped so these can later be replaced with real providers:

- Tripo 3D API
- MediaPipe/OpenPose or external motion-capture API
- MediaPipe FaceLandmarker/ARKit 52/Audio2Face style facial-capture API

Set the Qwen-Image API key before starting the backend:

```powershell
$env:DASHSCOPE_API_KEY="sk-..."
```

The default DashScope base URL is Beijing:

```text
https://dashscope.aliyuncs.com/api/v1
```

For Singapore, set:

```powershell
$env:DASHSCOPE_BASE_URL="https://dashscope-intl.aliyuncs.com/api/v1"
```

## Example: Character Job

```json
{
  "prompt": "二次元写实混合风格，东方废土少年机械术士",
  "reference_image_asset_id": null,
  "generate_image": true,
  "generate_multiview": false,
  "generate_3d": false,
  "image_provider": "qwen-image-2.0-pro",
  "model3d_provider": "tripo",
  "params": {
    "style": "semi-realistic anime",
    "negative_prompt": "低分辨率，低画质，肢体畸形，手指畸形，文字模糊",
    "prompt_extend": true,
    "watermark": false,
    "seed": 12345
  }
}
```

The generated image is always requested as `512*512` and saved under:

```text
data/assets/character/{job_id}/character_image_1.png
```

Character generation also applies a backend-side fixed prompt constraint before calling Qwen-Image: every user prompt is forced into a full-body character turnaround sheet with front, side, and back views. The original user prompt, fixed system prompt, and final effective prompt are all recorded in `character_manifest.json`.
