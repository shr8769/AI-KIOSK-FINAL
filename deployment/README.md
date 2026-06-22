# VidyaSahayak Deployment Guide
**System Version:** 1.0.0 | **Author:** Harsha (Engineering Lead)

This guide details the deployment of the **VidyaSahayak** campus AI kiosk system on physical hardware or development environments.

---

## 1. Hardware Prerequisites
For standard kiosk operations with interactive speech and local LLM processing:
* **Host Machine:** Intel i7 / AMD Ryzen 7 (8+ cores)
* **GPU:** NVIDIA RTX 3060 / 4060 or better (minimum 8GB VRAM) for local ASR & LLM inference.
* **Camera:** USB Webcam supporting 720p at 30 FPS.
* **Microphone:** Directional boundary microphone (USB) for voice isolation.
* **Display:** Full HD (1920x1080) Touchscreen display.

---

## 2. Software Prerequisites
Ensure the host machine runs Linux (Ubuntu 22.04 LTS recommended) or Windows 10/11 with:
* Docker Engine 24.0.0+ and Docker Compose v2.20.0+
* NVIDIA Container Toolkit (for GPU pass-through in Docker)
* CUDA Toolkit 12.1+ installed on host
* Python 3.10+ (for local/manual runs)

---

## 3. Configuration & Environment Variables
Create an `.env` file in the project root:

```ini
# API Keys (For cloud fallback, e.g. Gemini RAG)
GEMINI_API_KEY=your_gemini_api_key_here

# Local LLM Integration (Ollama / Qwen3-8B)
OLLAMA_HOST=http://localhost:11434
LOCAL_MODEL_NAME=qwen2.5:8b

# Speech Integration (Whisper & TTS)
WHISPER_MODEL_SIZE=base
TTS_LANGUAGE=en

# Session Storage
REDIS_HOST=redis
REDIS_PORT=6379
SQLITE_DB_PATH=database/sessions.db

# Hardware settings
CAMERA_INDEX=0
YOLO_MODEL_PATH=detection/models/yolov8n.pt
```

---

## 4. Deploying via Docker Compose

We provide a multi-container Docker setup that packages all services (FastAPI backend, React frontend, Redis, and Ollama) for single-command launch.

### Step 1: Start Ollama and download models (if running locally)
If running Ollama in a docker container:
```bash
docker compose up -d ollama
docker compose exec ollama ollama pull qwen2.5:8b
```

### Step 2: Build and start the kiosk application
```bash
docker compose up -d --build
```

The services will start at the following addresses:
* **Frontend Web App:** `http://localhost:3000`
* **FastAPI Backend Swagger UI:** `http://localhost:8000/docs`
* **Redis Cache:** `localhost:6379`

---

## 5. Manual / Development Run
If you prefer running services on the host machine directly:

### 1. Initialize Virtual Environment
```powershell
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Run Database Migrations & Ingest Knowledge Base
```bash
python scripts/data_ingestion/ingest.py
```

### 3. Run FastAPI Backend
```bash
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Run YOLO Presence Detector (in separate terminal)
```bash
python detection/detector.py
```

### 5. Run Frontend Web App (in separate terminal)
```bash
cd frontend
npm install
npm run dev
```

---

## 6. Service Management (Systemd)
To ensure the backend daemon and YOLO detector run continuously on a kiosk reboot, configure systemd unit files on Linux:

### Backend Service (`/etc/systemd/system/vidyasahayak-backend.service`)
```ini
[Unit]
Description=VidyaSahayak FastAPI Backend Service
After=network.target

[Service]
User=kiosk
WorkingDirectory=/home/kiosk/AI-KIOSK
ExecStart=/home/kiosk/AI-KIOSK/venv/bin/uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start services:
```bash
sudo systemctl daemon-reload
sudo systemctl enable vidyasahayak-backend.service
sudo systemctl start vidyasahayak-backend.service
```

---

## 7. Troubleshooting & Verification

### 1. Warmup Local Model Cache
To avoid a 30s delay on the first user query, execute the warmup check immediately after startup:
```bash
python scripts/setup/warmup.py
```

### 2. Verify YOLO Camera Feed
If the camera fails to initialize, verify the device index:
```bash
ls -l /dev/video*
```
Adjust `CAMERA_INDEX` in the `.env` file accordingly.
