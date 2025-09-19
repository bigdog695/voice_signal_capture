Voice Signal Capture: Backend Split
==================================

Overview
- This repo is split into two Python projects:
  - `backend-daemon`: ZMQ PULL->PUB ASR daemon (runs FunASR, produces events)
  - `websocket-server`: FastAPI WebSocket server that SUBscribes to daemon events and forwards to clients by IP

Data Flow
1. Producers push raw PCM chunks to `tcp://<daemon-host>:5556` (daemon PULL bind).
2. Daemon recognizes speech and publishes events to `tcp://<daemon-host>:5557` (daemon PUB bind).
3. WebSocket server connects to `tcp://<daemon-host>:5557` as SUB, reads events, and routes messages to clients whose IP matches `peer_ip`.
4. If no matching client is connected, the message is dropped.

Endpoints
- WebSocket: `ws://<ws-server>:8000/listening`
- Health: `http://<ws-server>:8000/health`

Environment
- Daemon:
  - `INPUT_ZMQ_ENDPOINT` (default `tcp://0.0.0.0:5556`)
  - `OUTPUT_ZMQ_ENDPOINT` (default `tcp://0.0.0.0:5557`)
  - `ASR_MODEL` (default `paraformer-zh`)
  - `ASR_MODEL_REV` (default `v2.0.4`)
- WS Server:
  - `ASR_EVENTS_ENDPOINT` (default `tcp://127.0.0.1:5557`)

Event Schema (daemon PUB and WS forward)
```json
{
  "type": "asr_result" | "call_finished",
  "text": "...",              // call_finished uses empty string
  "peer_ip": "1.2.3.4",
  "source": "micA"
}
```

Notes
- FORCE_LISTENING_DEBUG mode is removed in the WebSocket server. All routing is IP-based; unmatched events are dropped.
- The old `python-backend/main.py` is left intact for reference but is superseded by the split above.
