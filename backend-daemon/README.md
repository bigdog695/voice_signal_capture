ASR Backend Daemon
===================

Purpose
- Listens for raw audio chunks over ZMQ (PULL, default tcp://0.0.0.0:5556)
- Runs ASR using FunASR
- Publishes recognized events over ZMQ (PUB, default tcp://0.0.0.0:5557)

Config (env)
- `INPUT_ZMQ_ENDPOINT` (default `tcp://0.0.0.0:5556`)
- `OUTPUT_ZMQ_ENDPOINT` (default `tcp://0.0.0.0:5557`)
- `ASR_MODEL` (default `paraformer-zh`)
- `ASR_MODEL_REV` (default `v2.0.4`)

Run
```bash
pip install -r requirements.txt
python daemon.py
```

Output Event Format (simplified)
```json
{
  "type": "asr_result" | "call_finished",
  "text": "...",              // call_finished uses empty string
  "peer_ip": "1.2.3.4",
  "source": "micA"
}
```
