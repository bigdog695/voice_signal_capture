import os
# Suppress all progress bars before any imports
os.environ.setdefault("TQDM_DISABLE", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

import sys
import json
import time
import logging
from typing import Dict, Tuple, Optional

script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(script_dir, ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from common.logging_utils import configure_rotating_logger, NoRTFilter, log_event

import numpy as np
import scipy.signal
import zmq
import math


# ================= Logging =================
LOG_NAME = "ASRDaemon"

# --- Logging Setup ---
# Create logs directory. This will be created inside the 'backend-daemon' directory.
LOG_DIR = os.path.join(script_dir, "daemon_logs")
os.makedirs(LOG_DIR, exist_ok=True)

log = logging.getLogger(LOG_NAME)
log.setLevel(logging.INFO)
log.propagate = False

if log.hasHandlers():
    log.handlers.clear()


configure_rotating_logger(
    log,
    LOG_DIR,
    "daemon-active.log",
    when="H",
    interval=1,
    suffix_format="%y-%m-%d-%H",
    align_to_period_start=True,
)

# Stream handler
stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
stream_handler.addFilter(NoRTFilter())
log.addHandler(stream_handler)
# --- End Logging Setup ---

# Suppress root logger messages from funasr decoding
class FunasrFilter(logging.Filter):
    def filter(self, record):
        message = record.getMessage()
        return "decoding, utt:" not in message

logging.getLogger().addFilter(FunasrFilter())


# ================= Config =================
# Input ZMQ endpoint where raw PCM chunks arrive (producer sends via PUSH)
INPUT_ZMQ_ENDPOINT = os.getenv("INPUT_ZMQ_ENDPOINT", "tcp://0.0.0.0:5556")

# Output ZMQ endpoint to publish recognized text events (WS server subscribes)
OUTPUT_ZMQ_ENDPOINT = os.getenv("OUTPUT_ZMQ_ENDPOINT", "tcp://100.120.2.227:5557")

# Model settings
# Default to non-streaming model as requested
MODEL_NAME = os.getenv("ASR_MODEL", "paraformer-zh")
MODEL_REV = os.getenv("ASR_MODEL_REV", "v2.0.4")
ASR_INPUT_SR = int(os.getenv("ASR_INPUT_SAMPLE_RATE", "8000"))
ASR_ENERGY_GATE = float(os.getenv("ASR_ENERGY_GATE", "0"))  # 0 disables gate

try:
    import torch  # noqa: F401
    DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
except Exception:
    DEVICE = "cpu"


# ================= ASR Model =================
asr_funasr_model = None


def load_funasr_model():
    global asr_funasr_model
    if asr_funasr_model is not None:
        return asr_funasr_model
    try:
        os.environ.setdefault("USE_TORCH", "1")
        from funasr import AutoModel
        log_event(log, "asr_model_loading_start", model=MODEL_NAME, rev=MODEL_REV, device=DEVICE)
        asr_funasr_model = AutoModel(
            model=MODEL_NAME,
            model_revision=MODEL_REV,
            vad_model="fsmn-vad",
            vad_model_revision="v2.0.4",
            punc_model="ct-punc",
            punc_model_revision="v2.0.4",
            device=DEVICE,
        )
        log_event(log, "asr_model_loaded", model=MODEL_NAME, device=DEVICE)
    except Exception as e:
        log_event(log, "asr_model_load_failed", error=str(e))
        asr_funasr_model = None
    return asr_funasr_model


def _extract_text(result) -> Optional[str]:
    try:
        if not result:
            return None
        if isinstance(result, list) and result:
            item = result[0]
            if isinstance(item, dict):
                for key in ("text", "value", "transcript", "result", "sentence"):
                    v = item.get(key)
                    if isinstance(v, str) and v.strip():
                        return v.strip()
            elif isinstance(item, str) and item.strip():
                return item.strip()
        elif isinstance(result, dict):
            for key in ("text", "value", "transcript", "result", "sentence"):
                v = result.get(key)
                if isinstance(v, str) and v.strip():
                    return v.strip()
        elif isinstance(result, str) and result.strip():
            return result.strip()
    except Exception:
        pass
    return None


def _asr_generate_blocking(pcm_bytes: bytes) -> Optional[str]:
    try:
        audio = np.frombuffer(pcm_bytes, dtype=np.int16)
        if audio.size == 0:
            return None
        # optional simple energy gate
        if ASR_ENERGY_GATE > 0 and np.abs(audio).mean() < ASR_ENERGY_GATE:
            return None

        # resample to 16k for FunASR models
        if ASR_INPUT_SR <= 0:
            src_sr = 8000
        else:
            src_sr = ASR_INPUT_SR

        if src_sr == 16000:
            audio_f = audio.astype(np.float32) / 32768.0
        else:
            up = 16000
            down = src_sr
            g = math.gcd(up, down)
            up //= g
            down //= g
            audio_f = scipy.signal.resample_poly(audio, up=up, down=down).astype(np.float32) / 32768.0

        result = asr_funasr_model.generate(input=audio_f)
        txt = _extract_text(result)
        if txt:
            return txt
    except Exception as e:
        log_event(log, "asr_generate_error", error=str(e))
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
        log_event(log, "fatal_model_unavailable")
        raise SystemExit(2)

    ctx = zmq.Context.instance()
    pull_sock = ctx.socket(zmq.PULL)
    pub_sock = ctx.socket(zmq.PUB)
    # Enable fast close
    pull_sock.setsockopt(zmq.LINGER, 0)
    pub_sock.setsockopt(zmq.LINGER, 0)

    try:
        pull_sock.bind(INPUT_ZMQ_ENDPOINT)
        pub_sock.connect(OUTPUT_ZMQ_ENDPOINT)
        log_event(log, "daemon_bind_ok", pull=INPUT_ZMQ_ENDPOINT, pub=OUTPUT_ZMQ_ENDPOINT)
    except Exception as e:
        log_event(log, "daemon_bind_error", error=str(e))
        raise

    # state minimal: (peer_ip, source, unique_key, ssrc) -> {chunks, bytes}
    call_state: Dict[Tuple[str, str, Optional[str], Optional[str]], Dict[str, object]] = {}

    try:
        while True:
            try:
                meta_raw, pcm = pull_sock.recv_multipart()
            except Exception as e:
                log_event(log, "pull_recv_error", error=str(e))
                time.sleep(0.02)
                continue

            try:
                meta = json.loads(meta_raw.decode('utf-8'))
            except Exception as e:
                log_event(log, "meta_decode_error", error=str(e))
                continue

            peer_ip = meta.get('peer_ip', 'unknown')
            source = meta.get('source', 'unknown')
            start_ts = meta.get('start_ts')
            end_ts = meta.get('end_ts')
            unique_key = meta.get('unique_key')
            ssrc = meta.get('ssrc')
            is_finished = bool(meta.get('IsFinished', False))

            key = (peer_ip, source, unique_key, ssrc)
            if key not in call_state:
                call_state[key] = {"chunks": 0, "bytes": 0, "last_text": None}

            st = call_state[key]
            if pcm:
                st["chunks"] += 1
                st["bytes"] += len(pcm)
                txt = _asr_generate_blocking(pcm)
                if txt:
                    st["last_text"] = txt
                    event = {
                        'type': 'asr_update',
                        'text': txt,
                        'peer_ip': peer_ip,
                        'source': source,
                        'unique_key': unique_key,
                        'ssrc': ssrc,
                    }
                    log_event(
                        log,
                        'asr_update_generated',
                        text=event['text'],
                        peer_ip=peer_ip,
                        source=source,
                        unique_key=unique_key,
                        ssrc=ssrc,
                        is_finished=is_finished,
                    )
                    try:
                        pub_sock.send_json(event, ensure_ascii=False)
                    except Exception as e:
                        log_event(log, 'pub_send_error', error=str(e))

            if is_finished:
                finish_evt = {
                    'type': 'call_finished',
                    'text': '',
                    'peer_ip': peer_ip,
                    'source': source,
                    'unique_key': unique_key,
                    'ssrc': ssrc,
                }
                log_event(
                    log,
                    'call_finished_generated',
                    peer_ip=peer_ip,
                    source=source,
                    unique_key=unique_key,
                    ssrc=ssrc,
                    is_finished=is_finished,
                )
                try:
                    pub_sock.send_json(finish_evt, ensure_ascii=False)
                except Exception as e:
                    log_event(log, 'pub_send_error', error=str(e))
                st['chunks'] = 0
                st['bytes'] = 0
                st['last_text'] = None

    except KeyboardInterrupt:
        log_event(log, "daemon_interrupt")
    finally:
        try:
            pull_sock.close(0)
            pub_sock.close(0)
            ctx.term()
        except Exception:
            pass
        log_event(log, "daemon_exit")


if __name__ == "__main__":
    main()
