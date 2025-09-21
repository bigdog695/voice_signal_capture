# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Voice Signal Capture is a distributed voice recognition system with three main components:

1. **Backend Daemon** (`backend-daemon/`) - ASR daemon using FunASR that processes raw PCM audio chunks via ZMQ
2. **WebSocket Server** (`websocket-server/`) - FastAPI server that bridges ZMQ events to WebSocket clients
3. **Electron Frontend** (`electron-chat-frontend/`) - React-based Electron chat application

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

## Environment Configuration

### Backend Daemon
- `INPUT_ZMQ_ENDPOINT` (default: `tcp://0.0.0.0:5556`)
- `OUTPUT_ZMQ_ENDPOINT` (default: `tcp://0.0.0.0:5557`)
- `ASR_MODEL` (default: `paraformer-zh`)
- `ASR_MODEL_REV` (default: `v2.0.4`)

### WebSocket Server
- `ASR_EVENTS_ENDPOINT` (default: `tcp://127.0.0.1:5557`)
- `WS_BROADCAST_ALL` (default: `0`) - Set to `1` for broadcast mode

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

## Testing and Validation

The WebSocket server includes a health endpoint at `/health` for connectivity testing. The frontend provides connection testing in the settings panel.

## Build Dependencies

- **Python**: funasr, numpy, scipy, pyzmq, fastapi, uvicorn
- **Node.js**: React 18, Electron 25, Vite 5, electron-builder
- **System**: CUDA support optional for ASR acceleration