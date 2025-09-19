import os
import json
import time
import logging
from datetime import datetime
from typing import Dict, Tuple, Optional

import numpy as np
import scipy.signal
import zmq


# ================= Logging =================
LOG_NAME = "ASRDaemon"
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger(LOG_NAME)


# ================= Config =================
# Input ZMQ endpoint where raw PCM chunks arrive (producer sends via PUSH)
INPUT_ZMQ_ENDPOINT = os.getenv("INPUT_ZMQ_ENDPOINT", "tcp://0.0.0.0:5556")

# Output ZMQ endpoint to publish recognized text events (WS server subscribes)
OUTPUT_ZMQ_ENDPOINT = os.getenv("OUTPUT_ZMQ_ENDPOINT", "tcp://0.0.0.0:5557")

# Model settings
MODEL_NAME = os.getenv("ASR_MODEL", "paraformer-zh")
MODEL_REV = os.getenv("ASR_MODEL_REV", "v2.0.4")

try:
    import torch  # noqa: F401
    DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
except Exception:
    DEVICE = "cpu"


# ================= ASR Model =================
asr_funasr_model = None


def rt_event(event: str, **fields):
    payload = {"evt": event, "ts": datetime.utcnow().isoformat() + "Z", **fields}
    try:
        log.info("RT " + json.dumps(payload, ensure_ascii=False))
    except Exception:
        log.info(f"RT {{'evt':'{event}','error':'log_serialize_failed'}}")


def load_funasr_model():
    global asr_funasr_model
    if asr_funasr_model is not None:
        return asr_funasr_model
    try:
        os.environ.setdefault("USE_TORCH", "1")
        from funasr import AutoModel
        rt_event("asr_model_loading_start", model=MODEL_NAME, rev=MODEL_REV, device=DEVICE)
        asr_funasr_model = AutoModel(
            model=MODEL_NAME,
            model_revision=MODEL_REV,
            vad_model="fsmn-vad",
            vad_model_revision="v2.0.4",
            punc_model="ct-punc",
            punc_model_revision="v2.0.4",
            device=DEVICE,
        )
        rt_event("asr_model_loaded", model=MODEL_NAME, device=DEVICE)
    except Exception as e:
        rt_event("asr_model_load_failed", error=str(e))
        asr_funasr_model = None
    return asr_funasr_model


def _asr_generate_blocking(pcm_bytes: bytes) -> Optional[str]:
    try:
        audio_8k = np.frombuffer(pcm_bytes, dtype=np.int16)
        if audio_8k.size == 0:
            return None
        # simple VAD-ish energy gate
        if np.abs(audio_8k).mean() < 5:
            return None
        audio_16k = scipy.signal.resample_poly(audio_8k, up=2, down=1).astype(np.float32) / 32768.0
        result = asr_funasr_model.generate(input=audio_16k)
        if result and len(result) > 0:
            txt = result[0].get('text')
            if txt and txt.strip():
                return txt.strip()
    except Exception as e:
        rt_event("asr_generate_error", error=str(e))
    return None


def main():
    log.info("========================================")
    log.info("ASR Backend Daemon - PULL->PUB")
    log.info("========================================")
    log.info(f"Input ZMQ:  {INPUT_ZMQ_ENDPOINT} (PULL bind)")
    log.info(f"Output ZMQ: {OUTPUT_ZMQ_ENDPOINT} (PUB bind)")
    log.info(f"Model: {MODEL_NAME} rev={MODEL_REV} device={DEVICE}")

    load_funasr_model()
    if asr_funasr_model is None:
        rt_event("fatal_model_unavailable")
        raise SystemExit(2)

    ctx = zmq.Context.instance()
    pull_sock = ctx.socket(zmq.PULL)
    pub_sock = ctx.socket(zmq.PUB)
    # Enable fast close
    pull_sock.setsockopt(zmq.LINGER, 0)
    pub_sock.setsockopt(zmq.LINGER, 0)

    try:
        pull_sock.bind(INPUT_ZMQ_ENDPOINT)
        pub_sock.bind(OUTPUT_ZMQ_ENDPOINT)
        rt_event("daemon_bind_ok", pull=INPUT_ZMQ_ENDPOINT, pub=OUTPUT_ZMQ_ENDPOINT)
    except Exception as e:
        rt_event("daemon_bind_error", error=str(e))
        raise

    # state minimal: (peer_ip, source) -> {chunks, bytes}
    call_state: Dict[Tuple[str, str], Dict[str, int]] = {}

    try:
        while True:
            try:
                meta_raw, pcm = pull_sock.recv_multipart()
            except Exception as e:
                rt_event("pull_recv_error", error=str(e))
                time.sleep(0.02)
                continue

            try:
                meta = json.loads(meta_raw.decode('utf-8'))
            except Exception as e:
                rt_event("meta_decode_error", error=str(e))
                continue

            peer_ip = meta.get('peer_ip', 'unknown')
            source = meta.get('source', 'unknown')
            start_ts = meta.get('start_ts')
            end_ts = meta.get('end_ts')
            is_finished = bool(meta.get('IsFinished', False))

            key = (peer_ip, source)
            if key not in call_state:
                call_state[key] = {"chunks": 0, "bytes": 0}

            st = call_state[key]
            if pcm:
                st["chunks"] += 1
                st["bytes"] += len(pcm)
                txt = _asr_generate_blocking(pcm)
                if txt:
                    event = {
                        'type': 'asr_result',
                        'text': txt,
                        'peer_ip': peer_ip,
                        'source': source,
                    }
                    try:
                        pub_sock.send_json(event)
                    except Exception as e:
                        rt_event('pub_send_error', error=str(e))

            if is_finished:
                finish_evt = {
                    'type': 'call_finished',
                    'text': '',
                    'peer_ip': peer_ip,
                    'source': source,
                }
                try:
                    pub_sock.send_json(finish_evt)
                except Exception as e:
                    rt_event('pub_send_error', error=str(e))
                st['chunks'] = 0
                st['bytes'] = 0

    except KeyboardInterrupt:
        rt_event("daemon_interrupt")
    finally:
        try:
            pull_sock.close(0)
            pub_sock.close(0)
            ctx.term()
        except Exception:
            pass
        rt_event("daemon_exit")


if __name__ == "__main__":
    main()
