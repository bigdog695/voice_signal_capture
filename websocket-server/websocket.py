import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Set, Tuple, List

import zmq.asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(script_dir, ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
# Allow importing sibling modules (e.g., ws_ticket_routes.py)
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from common.logging_utils import NoRTFilter, configure_rotating_logger, log_event


LOG_NAME = "WSServer"

# --- Logging Setup ---
# Create logs directory. This will be created inside the 'websocket-server' directory.
LOG_DIR = os.path.join(script_dir, "main_logs")
os.makedirs(LOG_DIR, exist_ok=True)

log = logging.getLogger(LOG_NAME)
log.setLevel(logging.INFO)
log.propagate = False

if log.hasHandlers():
    log.handlers.clear()

configure_rotating_logger(
    log,
    LOG_DIR,
    "ws-active.txt",
    when="H",
    interval=1,
    suffix_format="%y-%m-%d-%H",
    align_to_period_start=True,
    file_extension="txt",
)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s"))
stream_handler.addFilter(NoRTFilter())
log.addHandler(stream_handler)
# --- End Logging Setup ---


# --- Configuration ---
ASR_EVENTS_ENDPOINT = os.getenv("ASR_EVENTS_ENDPOINT", "tcp://0.0.0.0:5557")
WS_BROADCAST_ALL = os.getenv("WS_BROADCAST_ALL", "0").strip().lower() in {"1", "true", "yes", "on"}
WS_ALLOWED_ORIGINS_RAW = os.getenv("WS_ALLOWED_ORIGINS", "*")
WS_ALLOWED_ORIGINS = [origin.strip() for origin in WS_ALLOWED_ORIGINS_RAW.split(",") if origin.strip()] or ["*"]


# --- FastAPI App Setup ---
app = FastAPI(title="Voice Listening WebSocket", version="1.0.0")

allow_all_origins = any(origin == "*" for origin in WS_ALLOWED_ORIGINS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if allow_all_origins else WS_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Runtime State ---
LISTENING_CLIENTS: Dict[str, WebSocket] = {}
CLIENT_IP_MAPPING: Dict[str, Optional[str]] = {}
ZMQ_TASK: Optional[asyncio.Task] = None


def _client_ip_from_ws(websocket: WebSocket) -> str:
    try:
        headers = {k.lower(): v for k, v in websocket.headers.items()}
        for header in ("x-forwarded-for", "x-real-ip", "x-client-ip"):
            if header in headers and headers[header]:
                return headers[header].split(",")[0].strip()
    except Exception:
        pass
    client = getattr(websocket, "client", None)
    if client and getattr(client, "host", None):
        return client.host
    return "unknown"


async def _zmq_consume_loop():
    ctx = zmq.asyncio.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.LINGER, 0)
    sub.setsockopt(zmq.SUBSCRIBE, b"")  # subscribe all
    sub.bind(ASR_EVENTS_ENDPOINT)
    log_event(log, 'zmq_sub_connected', endpoint=ASR_EVENTS_ENDPOINT)
    log_event(log, 'zmq_consume_loop_start', endpoint=ASR_EVENTS_ENDPOINT)

    try:
        while True:
            msg = await sub.recv()
            try:
                if isinstance(msg, (bytes, bytearray)):
                    raw_len = len(msg)
                    raw_preview = msg[:200].decode('utf-8', errors='replace')
                    text_preview = None
                    # Try extract "text" field for more human readable log (unescaped)
                    try:
                        tmp_obj = json.loads(raw_preview)
                        if isinstance(tmp_obj, dict) and 'text' in tmp_obj:
                            # limit text preview length to 120 chars for safety
                            text_preview = str(tmp_obj.get('text'))[:120]
                    except Exception:
                        pass
                    if text_preview is not None:
                        log_event(log, 'zmq_raw_msg_received', bytes=raw_len, preview=raw_preview, text_preview=text_preview)
                    else:
                        log_event(log, 'zmq_raw_msg_received', bytes=raw_len, preview=raw_preview)
                else:
                    log_event(log, 'zmq_raw_msg_received', type=str(type(msg)))
            except Exception as e:
                log_event(log, 'zmq_raw_log_error', error=str(e))
            try:
                evt = json.loads(msg.decode('utf-8')) if isinstance(msg, (bytes, bytearray)) else msg
            except Exception:
                # sub may deliver JSON via send_json (already parsed) in some contexts
                if isinstance(msg, dict):
                    evt = msg
                else:
                    try:
                        # log decode failure with preview
                        preview = msg[:200].decode('utf-8', errors='replace') if isinstance(msg, (bytes, bytearray)) else str(msg)[:200]
                        log_event(log, 'zmq_json_decode_error', preview=preview)
                    except Exception:
                        log_event(log, 'zmq_json_decode_error')
                    continue

            try:
                evt_text_preview = None
                if isinstance(evt.get('text'), str):
                    evt_text_preview = evt.get('text')[:120]
                elif 'text' in evt and evt.get('text') is not None:
                    evt_text_preview = str(evt.get('text'))[:120]
                log_event(
                    log,
                    'zmq_evt_parsed',
                    evt_type=evt.get('type'),
                    peer_ip=evt.get('peer_ip'),
                    source=evt.get('source'),
                    unique_key=evt.get('unique_key'),
                    ssrc=evt.get('ssrc'),
                    text=evt_text_preview,
                    is_finished=evt.get('is_finished', False),
                )
            except Exception:
                pass

            await _dispatch_asr_event(evt)
    except asyncio.CancelledError:
        log_event(log, 'zmq_consume_cancel')
    finally:
        try:
            sub.close(0)
            ctx.term()
        except Exception:
            pass
        log_event(log, 'zmq_consume_exit')


async def _dispatch_asr_event(evt: Dict):
    # Expect schema from daemon: {type, text, peer_ip, source, unique_key, ssrc}
    if not isinstance(evt, dict):
        return
    if 'type' not in evt:
        return
    # In non-broadcast mode we require peer_ip to route; in broadcast mode we don't
    if not WS_BROADCAST_ALL and 'peer_ip' not in evt:
        return

    unique_key = evt.get('unique_key')
    ssrc = evt.get('ssrc')
    peer_ip = evt.get('peer_ip')
    text_preview = None
    if 'text' in evt and evt.get('text') is not None:
        try:
            text_preview = str(evt.get('text'))[:120]
        except Exception:
            text_preview = '<unserializable>'

    clients_snapshot: List[Tuple[str, WebSocket]] = list(LISTENING_CLIENTS.items())

    if WS_BROADCAST_ALL:
        # Broadcast to all connected clients
        if not clients_snapshot:
            log_event(log, 'broadcast_no_clients', total_clients=0)
            return
        log_event(
            log,
            'broadcast_event',
            total_clients=len(clients_snapshot),
            evt_type=evt.get('type'),
            unique_key=unique_key,
            ssrc=ssrc,
            text=text_preview,
        )
        tasks: List[asyncio.Task] = []
        for cid, ws in clients_snapshot:
            tasks.append(asyncio.create_task(ws.send_text(json.dumps(evt, ensure_ascii=False))))
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            problem: Set[str] = set()
            for idx, res in enumerate(results):
                if isinstance(res, Exception) and idx < len(clients_snapshot):
                    cid = clients_snapshot[idx][0]
                    problem.add(cid)
                    log_event(
                        log,
                        'broadcast_client_send_error',
                        client_id=cid,
                        error=str(res),
                        unique_key=unique_key,
                        ssrc=ssrc,
                        text=text_preview,
                    )
            for pc in problem:
                LISTENING_CLIENTS.pop(pc, None)
                CLIENT_IP_MAPPING.pop(pc, None)
                log_event(
                    log,
                    'client_removed_send_fail',
                    client_id=pc,
                    reason='broadcast_send_fail',
                    unique_key=unique_key,
                    ssrc=ssrc,
                    text=text_preview,
                )
        return

    # --- Original targeted routing by peer_ip ---
    target_ip = peer_ip if peer_ip else 'unknown'
    target_clients: List[Tuple[str, WebSocket]] = []
    for cid, ws in clients_snapshot:
        if CLIENT_IP_MAPPING.get(cid) == target_ip:
            target_clients.append((cid, ws))

    tasks: List[asyncio.Task] = []
    for cid, ws in target_clients:
        log_event(
            log,
            'send_data_to_client',
            client_id=cid,
            target_ip=target_ip,
            unique_key=unique_key,
            ssrc=ssrc,
            text=text_preview,
        )
        tasks.append(asyncio.create_task(ws.send_text(json.dumps(evt, ensure_ascii=False))))

    if not target_clients:
        log_event(
            log,
            'no_target_clients_found',
            target_ip=target_ip,
            total_clients=len(LISTENING_CLIENTS),
            unique_key=unique_key,
            ssrc=ssrc,
            text=text_preview,
        )

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        problem_clients: Set[str] = set()
        for idx, res in enumerate(results):
            if isinstance(res, Exception) and idx < len(target_clients):
                cid = target_clients[idx][0]
                problem_clients.add(cid)
                log_event(
                    log,
                    'client_send_error',
                    client_id=cid,
                    error=str(res),
                    unique_key=unique_key,
                    ssrc=ssrc,
                    text=text_preview,
                )
        for pc in problem_clients:
            LISTENING_CLIENTS.pop(pc, None)
            CLIENT_IP_MAPPING.pop(pc, None)
            log_event(
                log,
                'client_removed_send_fail',
                client_id=pc,
                unique_key=unique_key,
                ssrc=ssrc,
                text=text_preview,
            )


@app.on_event("startup")
async def startup_event():
    # Self-check: verify websockets library availability for proper upgrade support
    try:
        import websockets  # noqa: F401
        log_event(log, 'websockets_lib_detected', version=getattr(__import__('websockets'), '__version__', 'unknown'))
    except Exception as e:
        log_event(log, 'websockets_lib_missing', error=str(e))
    global ZMQ_TASK
    if ZMQ_TASK is None or ZMQ_TASK.done():
        ZMQ_TASK = asyncio.create_task(_zmq_consume_loop())
        log_event(log, 'zmq_consumer_started')


@app.on_event("shutdown")
async def shutdown_event():
    global ZMQ_TASK
    if ZMQ_TASK and not ZMQ_TASK.done():
        ZMQ_TASK.cancel()


@app.get("/health")
async def health():
    return {
        'status': 'ok',
        'clients': len(LISTENING_CLIENTS),
        'endpoint': ASR_EVENTS_ENDPOINT,
        'ts': datetime.utcnow().isoformat() + 'Z'
    }

# --- Include routes (ticket generation moved out) ---
try:
    from ws_ticket_routes import router as ticket_router
    app.include_router(ticket_router)
    log_event(log, 'routes_loaded', module='ws_ticket_routes')
except Exception as e:
    log_event(log, 'routes_load_error', error=str(e))


@app.websocket("/listening")
async def websocket_listening_endpoint(websocket: WebSocket):
    await websocket.accept()
    import uuid
    client_id = uuid.uuid4().hex[:8]
    client_ip = _client_ip_from_ws(websocket)

    LISTENING_CLIENTS[client_id] = websocket
    CLIENT_IP_MAPPING[client_id] = client_ip
    log_event(log, 'client_connect', client_id=client_id, client_ip=client_ip, total_clients=len(LISTENING_CLIENTS))

    async def server_heartbeat():
        while True:
            try:
                await websocket.send_text(json.dumps({'type': 'server_heartbeat', 'ts': datetime.utcnow().isoformat() + 'Z'}))
                await asyncio.sleep(1.0)
            except Exception:
                break
    hb_task = asyncio.create_task(server_heartbeat())

    try:
        while True:
            try:
                # keep the socket alive; we only care about ping/pong
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except WebSocketDisconnect:
                break
            except Exception as e:
                log_event(log, 'client_recv_error', client_id=client_id, error=str(e))
                break
            try:
                data = json.loads(msg)
            except Exception:
                continue
            if data.get('type') == 'ping':
                await websocket.send_text(json.dumps({'type': 'pong', 'ts': datetime.utcnow().isoformat() + 'Z'}))
                log_event(log, 'client_ping', client_id=client_id)
            elif data.get('type') == 'stop_listening':
                await websocket.send_text(json.dumps({'type': 'stopped', 'ts': datetime.utcnow().isoformat() + 'Z'}))
                break
    finally:
        hb_task.cancel()
        LISTENING_CLIENTS.pop(client_id, None)
        CLIENT_IP_MAPPING.pop(client_id, None)
    log_event(log, 'client_disconnect', client_id=client_id, client_ip=client_ip, remaining=len(LISTENING_CLIENTS))


if __name__ == "__main__":
    import uvicorn

    log.info("========================================")
    log.info("Voice WS Server - v1.0.0")
    log.info("========================================")
    log.info(f"ASR_EVENTS_ENDPOINT: {ASR_EVENTS_ENDPOINT}")
    log.info(f"WS_BROADCAST_ALL: {WS_BROADCAST_ALL}")

    # Allow overriding listen port (default 8000) so frontend config can match dynamically.
    PORT = int(os.getenv("WS_SERVER_PORT", "8000"))
    RELOAD_ENABLED = os.getenv("UVICORN_RELOAD", "true").strip().lower() in {"1", "true", "yes", "on"}

    try:
        log_event(log, 'server_starting', port=PORT, host='0.0.0.0', reload=RELOAD_ENABLED)
    except Exception:
        pass

    module_name = os.path.splitext(os.path.basename(__file__))[0]
    if RELOAD_ENABLED:
        uvicorn.run(f"{module_name}:app", host="0.0.0.0", port=PORT, reload=True, log_level="info")
    else:
        uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="info")
