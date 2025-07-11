# asr_server.py
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import numpy as np
import logging
import asyncio
from funasr import AutoModel   # FunASR 1.x
# ------------------------------------------------------------
# CONFIG
MODEL_NAME: str = "paraformer-zh-streaming"
MODEL_REV: str = "v2.0.4"      # keep in sync with HF / MS tag
DEVICE: str = "cpu"            # or "cuda" if a GPU is available

# 600 ms frame    →  0 look-ahead | 10 visible | 5 future
CHUNK_SIZE = [0, 10, 5]
ENC_LB = 4     # encoder look-back (chunks)
DEC_LB = 1     # decoder look-back (chunks)

SAMPLES_PER_FRAME = CHUNK_SIZE[1] * 960          # 9 600
BYTES_PER_FRAME = SAMPLES_PER_FRAME * 2          # 19 200 (16-bit PCM)
# ------------------------------------------------------------

# Logging ---------------------------------------------------------------------
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("ASR")

# FastAPI + CORS --------------------------------------------------------------
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173", "http://localhost:5174", "http://localhost:5175",
        "http://127.0.0.1:5173", "http://127.0.0.1:5174", "http://127.0.0.1:5175",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Model loading ---------------------------------------------------------------
try:
    log.info(f"Loading FunASR model '{MODEL_NAME}' (streaming)…")
    model = AutoModel(
        model=MODEL_NAME,
        model_revision=MODEL_REV,
        mode="online",
        device=DEVICE,
        hub="hf",             # pull from Hugging Face; change to "ms" if faster
    )
    log.info("Model ready.")
except Exception as exc:                      # noqa: BLE001
    log.exception("Model load failed: %s", exc)
    model = None

# -----------------------------------------------------------------------------


@app.get("/")
async def root():
    return {
        "message": "FunASR WebSocket Service",
        "status": "healthy" if model else "unhealthy",
        "model": MODEL_NAME,
    }


@app.get("/health")
async def health():
    return {"status": "healthy" if model else "unhealthy"}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await ws.accept()
    log.info("WebSocket accepted")

    if model is None:
        await ws.close(code=1011, reason="ASR model unavailable")
        return

    cache: dict = {}
    buf = bytearray()

    try:
        while True:
            # 1) gather raw bytes ------------------------------------------------
            chunk = await ws.receive_bytes()
            buf.extend(chunk)

            # 2) run recogniser for every full frame ----------------------------
            while len(buf) >= BYTES_PER_FRAME:
                frame = bytes(buf[:BYTES_PER_FRAME])
                del buf[:BYTES_PER_FRAME]

                audio = (np.frombuffer(frame, dtype=np.int16)
                           .astype(np.float32) / 32768.0)

                res = model.generate(
                    input=audio,
                    cache=cache,
                    is_final=False,
                    chunk_size=CHUNK_SIZE,
                    encoder_chunk_look_back=ENC_LB,
                    decoder_chunk_look_back=DEC_LB,
                )

                text = _extract_text(res)
                if text:
                    await ws.send_text(text)

    except WebSocketDisconnect:
        log.info("Client gone – flushing final audio.")
        if buf:
            audio = (np.frombuffer(buf, dtype=np.int16)
                       .astype(np.float32) / 32768.0)
            res = model.generate(
                input=audio,
                cache=cache,
                is_final=True,
                chunk_size=CHUNK_SIZE,
                encoder_chunk_look_back=ENC_LB,
                decoder_chunk_look_back=DEC_LB,
            )
            text = _extract_text(res)
            if text:
                await ws.send_text(text)

    finally:
        await ws.close()
        log.info("WebSocket closed.")


# -----------------------------------------------------------------------------


def _extract_text(result):
    """
    FunASR returns a list of dicts. We only care about the first text-bearing
    field it exposes.
    """
    if not result:
        return None
    if isinstance(result, list) and result:
        item = result[0]
        if isinstance(item, dict):
            for key in ("text", "transcript", "result", "sentence"):
                if key in item and item[key]:
                    return item[key]
        elif isinstance(item, str):
            return item
    elif isinstance(result, str):
        return result
    return None
