WebSocket Server
================

Purpose
- Hosts the `/listening` WebSocket endpoint.
- Subscribes to ASR daemon events over ZMQ (SUB).
- Parses events and forwards messages to clients whose IP matches `peer_ip`.
- No FORCE_LISTENING_DEBUG; if no client for that IP, the message is dropped.

Config (env)
- `ASR_EVENTS_ENDPOINT` (default `tcp://127.0.0.1:5557`)

Run
```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Event format forwarded to clients (same as daemon output):
```json
{
  "type": "asr_result" | "call_finished",
  "text": "...",              // call_finished uses empty string
  "peer_ip": "1.2.3.4",
  "source": "micA"
}
```
