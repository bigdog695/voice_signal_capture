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
import heapq
from collections import defaultdict
from dataclasses import dataclass, field


# ================= Priority Queue for Event Ordering =================
@dataclass(order=True)
class PendingEvent:
    """Event pending to be published, ordered by voice_start_ts"""
    voice_start_ts: float
    event: dict = field(compare=False)
    receive_time: float = field(compare=False)


class EventQueueManager:
    """
    Manages priority queues per peer_ip to ensure events are published
    in order of voice_start_ts (when voice actually started speaking).
    """
    def __init__(self, pub_sock, max_delay_sec: float = 5.0):
        """
        Args:
            pub_sock: ZMQ PUB socket to publish events
            max_delay_sec: Maximum time to buffer events waiting for ordering
        """
        self.pub_sock = pub_sock
        self.max_delay_sec = max_delay_sec
        # peer_ip -> priority queue (min heap)
        self.queues: Dict[str, list] = defaultdict(list)
        # peer_ip -> last published voice_start_ts
        self.last_published: Dict[str, float] = {}

    def add_event(self, event: dict, voice_start_ts: float):
        """Add an event to the appropriate peer_ip queue"""
        peer_ip = event.get('peer_ip', 'unknown')
        receive_time = time.time()

        pending = PendingEvent(
            voice_start_ts=voice_start_ts,
            event=event,
            receive_time=receive_time
        )
        heapq.heappush(self.queues[peer_ip], pending)

    def try_publish_ready_events(self):
        """
        Publish events that are ready (in order and not waiting for earlier events).
        Call this periodically or after adding new events.
        """
        current_time = time.time()

        for peer_ip, queue in list(self.queues.items()):
            if not queue:
                continue

            while queue:
                # Peek at the earliest event by voice_start_ts
                earliest = queue[0]

                # Check if we should publish this event:
                # 1. It's the next in sequence (voice_start_ts >= last published)
                # 2. OR it's been waiting too long (max_delay_sec exceeded)
                last_pub_ts = self.last_published.get(peer_ip, 0)
                time_waiting = current_time - earliest.receive_time

                should_publish = (
                    earliest.voice_start_ts >= last_pub_ts or
                    time_waiting >= self.max_delay_sec
                )

                if should_publish:
                    # Remove from queue and publish
                    heapq.heappop(queue)

                    try:
                        self.pub_sock.send_json(earliest.event, ensure_ascii=False)
                        self.last_published[peer_ip] = earliest.voice_start_ts

                        log_event(
                            log,
                            'event_published_from_queue',
                            peer_ip=peer_ip,
                            voice_start_ts=earliest.voice_start_ts,
                            text=earliest.event.get('text', '')[:50],
                            queue_size=len(queue),
                            wait_time_ms=int(time_waiting * 1000)
                        )
                    except Exception as e:
                        log_event(log, 'pub_send_error', error=str(e))
                else:
                    # Not ready yet, wait for earlier events
                    break

            # Cleanup empty queues
            if not queue:
                del self.queues[peer_ip]

    def flush_all(self):
        """Flush all pending events (call on shutdown or call_finished)"""
        for peer_ip, queue in list(self.queues.items()):
            while queue:
                pending = heapq.heappop(queue)
                try:
                    self.pub_sock.send_json(pending.event, ensure_ascii=False)
                except Exception as e:
                    log_event(log, 'pub_send_error', error=str(e))
            del self.queues[peer_ip]

    def flush_peer(self, peer_ip: str):
        """Flush all pending events for a specific peer_ip"""
        if peer_ip in self.queues:
            queue = self.queues[peer_ip]
            while queue:
                pending = heapq.heappop(queue)
                try:
                    self.pub_sock.send_json(pending.event, ensure_ascii=False)
                except Exception as e:
                    log_event(log, 'pub_send_error', error=str(e))
            del self.queues[peer_ip]
            if peer_ip in self.last_published:
                del self.last_published[peer_ip]


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

# AEC (Acoustic Echo Cancellation) settings
ENABLE_AEC = os.getenv("ENABLE_AEC", "1") == "1"  # Enable AEC by default
ENABLE_NS = os.getenv("ENABLE_NS", "1") == "1"  # Enable noise suppression by default
ENABLE_AGC = os.getenv("ENABLE_AGC", "0") == "1"  # AGC disabled by default
AEC_FRAME_SIZE_MS = int(os.getenv("AEC_FRAME_SIZE_MS", "10"))  # Frame size in ms
AEC_FILTER_LENGTH_MS = int(os.getenv("AEC_FILTER_LENGTH_MS", "200"))  # Filter length in ms

try:
    import torch  # noqa: F401
    DEVICE = "cuda:0" if torch.cuda.is_available() else "cpu"
except Exception:
    DEVICE = "cpu"


# ================= ASR Model & Preprocessor =================
asr_funasr_model = None
audio_preprocessor = None


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


def load_audio_preprocessor():
    global audio_preprocessor
    if audio_preprocessor is not None:
        return audio_preprocessor
    try:
        from audio_preprocessor import AudioPreprocessor
        audio_preprocessor = AudioPreprocessor(
            sample_rate=ASR_INPUT_SR if ASR_INPUT_SR > 0 else 8000,
            enable_aec=ENABLE_AEC,
            enable_ns=ENABLE_NS,
            enable_agc=ENABLE_AGC,
            frame_size_ms=AEC_FRAME_SIZE_MS,
            filter_length_ms=AEC_FILTER_LENGTH_MS,
        )
        log_event(log, "audio_preprocessor_loaded",
                  aec=ENABLE_AEC, ns=ENABLE_NS, agc=ENABLE_AGC)
    except Exception as e:
        log_event(log, "audio_preprocessor_load_failed", error=str(e))
        audio_preprocessor = None
    return audio_preprocessor


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


def _load_allow_list(path: str) -> Optional[set]:
    try:
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            lines = [ln.strip() for ln in f.readlines()]
        ips = {ln for ln in lines if ln}
        if not ips:
            return None
        return ips
    except Exception as e:
        log_event(log, "allow_list_load_error", error=str(e))
        return None

def _asr_generate_blocking(pcm_bytes: bytes, far_end_pcm: Optional[bytes] = None) -> Optional[Dict]:
    """
    Process audio and return ASR result with VAD timestamp.

    Returns:
        Dict with keys: 'text', 'vad_start_ms' (first voice activity timestamp in ms)
        or None if no speech detected
    """
    try:
        audio = np.frombuffer(pcm_bytes, dtype=np.int16)
        if audio.size == 0:
            return None

        # Apply AEC preprocessing if available
        if audio_preprocessor is not None:
            far_audio = None
            if far_end_pcm:
                far_audio = np.frombuffer(far_end_pcm, dtype=np.int16)
                if far_audio.size == 0:
                    far_audio = None

            # Process with AEC
            audio = audio_preprocessor.process(audio, far_audio)

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

        # Generate with sentence timestamp to get VAD info
        result = asr_funasr_model.generate(
            input=audio_f,
            sentence_timestamp=True,  # Enable VAD timestamps
        )

        txt = _extract_text(result)
        if not txt:
            return None

        # Extract VAD timestamp (first voice activity start time in ms)
        vad_start_ms = 0
        try:
            if isinstance(result, list) and result:
                item = result[0]
                if isinstance(item, dict):
                    # FunASR returns timestamp as [[start_ms, end_ms], ...]
                    timestamp = item.get('timestamp')
                    if timestamp and isinstance(timestamp, list) and len(timestamp) > 0:
                        if isinstance(timestamp[0], list) and len(timestamp[0]) > 0:
                            vad_start_ms = int(timestamp[0][0])
        except Exception as e:
            log_event(log, "vad_timestamp_extract_error", error=str(e))

        return {
            'text': txt,
            'vad_start_ms': vad_start_ms
        }
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
    log.info(f"AEC: enabled={ENABLE_AEC}, NS={ENABLE_NS}, AGC={ENABLE_AGC}")

    # Load whitelist from a file named 'allow_list' under the current script directory.
    allow_list_path = os.path.join(script_dir, 'allow_list')
    allow_ips = _load_allow_list(allow_list_path)
    if allow_ips is None:
        log_event(log, "allow_list_mode", mode="allow_all")
    else:
        try:
            sample = list(allow_ips)[:5]
        except Exception:
            sample = []
        log_event(log, "allow_list_mode", mode="whitelist_active", count=len(allow_ips), sample=sample)

    load_funasr_model()
    if asr_funasr_model is None:
        log_event(log, "fatal_model_unavailable")
        raise SystemExit(2)

    # Load audio preprocessor
    load_audio_preprocessor()
    if audio_preprocessor is None:
        log.warning("Audio preprocessor not available, AEC will be disabled")
    else:
        log.info("Audio preprocessor loaded successfully")

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

    # Initialize event queue manager
    event_queue_mgr = EventQueueManager(pub_sock, max_delay_sec=5.0)
    log.info("Event queue manager initialized (max_delay=5.0s)")

    try:
        while True:
            try:
                # Receive message (can be 2-part or 3-part)
                msg_parts = pull_sock.recv_multipart()
                if len(msg_parts) == 2:
                    meta_raw, pcm = msg_parts
                    far_end_pcm = None
                elif len(msg_parts) == 3:
                    meta_raw, pcm, far_end_pcm = msg_parts
                else:
                    log_event(log, "invalid_msg_parts", parts=len(msg_parts))
                    continue
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

            # Whitelist filtering: if allow_list exists and is non-empty, only process whitelisted IPs
            if allow_ips is not None and peer_ip not in allow_ips:
                log_event(log, "ip_not_allowed", peer_ip=peer_ip, source=source, unique_key=unique_key, ssrc=ssrc)
                continue

            key = (peer_ip, source, unique_key, ssrc)
            if key not in call_state:
                call_state[key] = {"chunks": 0, "bytes": 0, "last_text": None}

            st = call_state[key]
            if pcm:
                st["chunks"] += 1
                st["bytes"] += len(pcm)
                # Pass far_end_pcm to ASR for AEC processing
                asr_result = _asr_generate_blocking(pcm, far_end_pcm)
                if asr_result:
                    txt = asr_result['text']
                    vad_start_ms = asr_result['vad_start_ms']
                    st["last_text"] = txt

                    # Calculate voice_start_ts based on chunk_start_ts + VAD offset
                    chunk_start_ts = start_ts if start_ts is not None else 0
                    voice_start_ts = chunk_start_ts + (vad_start_ms / 1000.0)

                    # Build event with new timestamp fields
                    event = {
                        'type': 'asr_update',
                        'text': txt,
                        'peer_ip': peer_ip,
                        'source': source,
                        'unique_key': unique_key,
                        'ssrc': ssrc,
                        'is_finished': is_finished,
                        # New timestamp fields
                        'voice_start_ts': voice_start_ts,  # Actual voice start time
                        'chunk_start_ts': chunk_start_ts,  # Original chunk start time
                        'offset_ms': vad_start_ms,  # VAD offset from chunk start
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
                        voice_start_ts=voice_start_ts,
                        vad_offset_ms=vad_start_ms,
                    )

                    # Add to priority queue instead of direct publish
                    event_queue_mgr.add_event(event, voice_start_ts)

                    # Try to publish ready events
                    event_queue_mgr.try_publish_ready_events()

            if is_finished:
                # Flush all pending events for this peer before sending call_finished
                log_event(log, 'flushing_pending_events', peer_ip=peer_ip, source=source)
                event_queue_mgr.flush_peer(peer_ip)

                finish_evt = {
                    'type': 'call_finished',
                    'text': '',
                    'peer_ip': peer_ip,
                    'source': source,
                    'unique_key': unique_key,
                    'ssrc': ssrc,
                    'is_finished': True,
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
        # Flush all pending events before shutdown
        log_event(log, "flushing_all_pending_events_on_shutdown")
        event_queue_mgr.flush_all()

        try:
            pull_sock.close(0)
            pub_sock.close(0)
            ctx.term()
        except Exception:
            pass
        log_event(log, "daemon_exit")


if __name__ == "__main__":
    main()
