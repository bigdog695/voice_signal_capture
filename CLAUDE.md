# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Voice Signal Capture is a distributed voice recognition system with four main components:

1. **Backend Daemon** (`backend-daemon/`) - ASR daemon using FunASR that processes raw PCM audio chunks via ZMQ
2. **WebSocket Server** (`websocket-server/`) - FastAPI server that bridges ZMQ events to WebSocket clients
3. **Electron Frontend** (`electron-chat-frontend/`) - React-based Electron chat application
4. **AI Ticket Generator** (`ai-generated-ticket/`) - FastAPI service that converts voice recognition text into standardized government hotline tickets using DeepSeek 14B model

## Architecture

The system follows a producer-consumer pattern with ZMQ messaging:

```
Audio Producers → ZMQ PULL (5556) → ASR Daemon → ZMQ PUB (5557) → WebSocket Server → WebSocket Clients
```

**Data Flow:**
1. Audio producers send raw PCM chunks to `tcp://<daemon-host>:5556` (daemon PULL bind)
2. ASR daemon recognizes speech and publishes events to `tcp://<daemon-host>:5557` (daemon PUB bind)
3. WebSocket server subscribes to daemon events and routes to clients by IP matching
4. Frontend connects via WebSocket to receive real-time transcription events

**ZMQ Message Format:**
Audio producers can send 2-part or 3-part messages:
- **2-part**: `[metadata_json, near_end_pcm]` - Standard mode, AEC falls back to noise suppression only
- **3-part**: `[metadata_json, near_end_pcm, far_end_pcm]` - Full AEC mode with reference signal

Where:
- `near_end_pcm`: Microphone audio (接线员麦克风 - with potential echo)
- `far_end_pcm`: Reference audio (市民音频 - what's playing in the headset)

**Event Schema:**
```json
{
  "type": "asr_result" | "call_finished",
  "text": "transcribed text",
  "peer_ip": "client.ip.address",
  "source": "micA"
}
```

## Development Commands

### Backend Daemon
```bash
cd backend-daemon
pip install -r requirements.txt
python daemon.py
```

### WebSocket Server
```bash
cd websocket-server
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### Electron Frontend
```bash
cd electron-chat-frontend

# Install dependencies and prepare offline UMD assets
npm install
npm run prepare

# Development (UI + Electron)
npm run dev:full

# Build React frontend only
npm run build:react

# Package Electron app
npm run pack

# Full build with installer
npm run build
```

### AI Ticket Generator
```bash
cd ai-generated-ticket
pip install -r requirements.txt

# Start Ollama service with DeepSeek model
ollama pull deepseek-r1:14b
ollama serve

# Start ticket service
python app.py
# or
./start_service.sh
```

## Environment Configuration

### Backend Daemon
- `INPUT_ZMQ_ENDPOINT` (default: `tcp://0.0.0.0:5556`)
- `OUTPUT_ZMQ_ENDPOINT` (default: `tcp://0.0.0.0:5557`)
- `ASR_MODEL` (default: `paraformer-zh`)
- `ASR_MODEL_REV` (default: `v2.0.4`)
- `ASR_INPUT_SAMPLE_RATE` (default: `8000`)
- `ASR_ENERGY_GATE` (default: `0`) - Energy gate threshold for silence filtering

#### AEC (Acoustic Echo Cancellation) Settings
- `ENABLE_AEC` (default: `1`) - Enable/disable echo cancellation
- `ENABLE_NS` (default: `1`) - Enable/disable noise suppression
- `ENABLE_AGC` (default: `0`) - Enable/disable automatic gain control
- `AEC_FRAME_SIZE_MS` (default: `10`) - Frame size in milliseconds (10, 20, or 30)
- `AEC_FILTER_LENGTH_MS` (default: `200`) - AEC filter length in milliseconds (50-500)

**Note:** AEC requires installing either `webrtc-audio-processing` (recommended) or `speexdsp-python` (fallback). See [requirements.txt](backend-daemon/requirements.txt) for details.

### WebSocket Server
- `ASR_EVENTS_ENDPOINT` (default: `tcp://127.0.0.1:5557`)
- `WS_BROADCAST_ALL` (default: `0`) - Set to `1` for broadcast mode

### AI Ticket Generator
- `DEEPSEEK_API_URL` (default: `http://127.0.0.1:11434/api/generate`)
- Service port: `8001`
- Max retries: `2`
- Request timeout: `60` seconds

## Key Implementation Details

### Electron Frontend Architecture
- Uses React with Vite for UI development
- Supports offline operation with vendor UMD files in `vendor/` directory
- Security-hardened with `contextIsolation: true` and `nodeIntegration: false`
- Preload script provides safe IPC bridge via `window.electronAPI`

### ZMQ Message Routing
- WebSocket server filters events by `peer_ip` field to route to correct clients
- Unmatched events are dropped (no broadcast unless `WS_BROADCAST_ALL=1`)
- IP-based routing enables multi-client support

### ASR Processing
- Uses FunASR with configurable Chinese models (default: paraformer-zh)
- Processes 8kHz PCM audio by default
- Energy gate filtering available via `ASR_ENERGY_GATE` environment variable
- **Audio Preprocessing Pipeline:**
  1. **AEC (Acoustic Echo Cancellation)** - Removes echo from far-end audio leaking into microphone
  2. **NS (Noise Suppression)** - Reduces background noise
  3. **AGC (Automatic Gain Control)** - Normalizes audio volume (optional)
  4. **Resampling** - Converts input audio to 16kHz for ASR model
  5. **FunASR Recognition** - Generates text transcription

**AEC Backend Support:**
- Primary: WebRTC Audio Processing Module (best quality, industry standard)
- Fallback: Speex DSP (good compatibility, lighter weight)
- Graceful degradation: If no AEC library installed, falls back to noise suppression only

### AI Ticket Processing
- Uses DeepSeek 14B model via Ollama for intelligent text summarization
- Supports 12345 citizen hotline standard ticket types (咨询|求助|投诉|举报|建议|其他)
- Intelligent JSON extraction handles model responses with thinking tags
- Automatic retry mechanism for parsing failures

## Testing and Validation

The WebSocket server includes a health endpoint at `/health` for connectivity testing. The frontend provides connection testing in the settings panel.

The AI ticket generator provides comprehensive test scripts and health endpoints at `/health` and `/` for service validation.

## Build Dependencies

- **Python**: funasr, numpy, scipy, pyzmq, fastapi, uvicorn
- **Node.js**: React 18, Electron 25, Vite 5, electron-builder
- **System**: CUDA support optional for ASR acceleration