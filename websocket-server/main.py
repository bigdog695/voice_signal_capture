import os
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Set, Tuple, List

import zmq.asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


LOG_NAME = "WSServer"
logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger(LOG_NAME)


# ================= Config =================
# Where to subscribe ASR daemon events
ASR_EVENTS_ENDPOINT = os.getenv("ASR_EVENTS_ENDPOINT", "tcp://127.0.0.1:5557")

app = FastAPI(title="Voice WS Server", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# client_id -> websocket
LISTENING_CLIENTS: Dict[str, WebSocket] = {}
# client_id -> ip
CLIENT_IP_MAPPING: Dict[str, str] = {}

ZMQ_TASK: Optional[asyncio.Task] = None


def rt_event(event: str, **fields):
    payload = {"evt": event, "ts": datetime.utcnow().isoformat() + "Z", **fields}
    try:
        log.info("RT " + json.dumps(payload, ensure_ascii=False))
    except Exception:
        log.info(f"RT {{'evt':'{event}','error':'log_serialize_failed'}}")


def _client_ip_from_ws(ws: WebSocket) -> str:
    ip = "unknown"
    try:
        if hasattr(ws, 'client') and ws.client:
            ip = ws.client.host
        elif hasattr(ws, 'scope') and ws.scope.get('client'):
            ip = ws.scope['client'][0]
        elif hasattr(ws, 'headers'):
            xff = ws.headers.get('x-forwarded-for')
            if xff:
                ip = xff.split(',')[0].strip()
            else:
                xri = ws.headers.get('x-real-ip')
                if xri:
                    ip = xri
    except Exception as e:
        rt_event('ip_extraction_error', error=str(e))
    return ip


async def _zmq_consume_loop():
    ctx = zmq.asyncio.Context.instance()
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt(zmq.LINGER, 0)
    sub.setsockopt(zmq.SUBSCRIBE, b"")  # subscribe all
    sub.connect(ASR_EVENTS_ENDPOINT)
    rt_event('zmq_sub_connected', endpoint=ASR_EVENTS_ENDPOINT)

    try:
        while True:
            msg = await sub.recv()
            try:
                evt = json.loads(msg.decode('utf-8')) if isinstance(msg, (bytes, bytearray)) else msg
            except Exception:
                # sub may deliver JSON via send_json (already parsed) in some contexts
                if isinstance(msg, dict):
                    evt = msg
                else:
                    continue

            await _dispatch_asr_event(evt)
    except asyncio.CancelledError:
        rt_event('zmq_consume_cancel')
    finally:
        try:
            sub.close(0)
            ctx.term()
        except Exception:
            pass
        rt_event('zmq_consume_exit')


async def _dispatch_asr_event(evt: Dict):
    # Expect simplified schema from daemon: {type, text, peer_ip, source}
    if not isinstance(evt, dict):
        return
    if 'type' not in evt or 'peer_ip' not in evt:
        return
    target_ip = evt.get('peer_ip', 'unknown')

    # build target client list by IP
    clients_snapshot: List[Tuple[str, WebSocket]] = list(LISTENING_CLIENTS.items())
    target_clients: List[Tuple[str, WebSocket]] = []
    for cid, ws in clients_snapshot:
        if CLIENT_IP_MAPPING.get(cid) == target_ip:
            target_clients.append((cid, ws))

    tasks: List[asyncio.Task] = []
    for cid, ws in target_clients:
        rt_event('send_data_to_client', client_id=cid)
        tasks.append(asyncio.create_task(ws.send_text(json.dumps(evt, ensure_ascii=False))))

    if not target_clients:
        rt_event('no_target_clients_found', target_ip=target_ip, total_clients=len(LISTENING_CLIENTS))

    if tasks:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        problem_clients: Set[str] = set()
        for idx, res in enumerate(results):
            if isinstance(res, Exception) and idx < len(target_clients):
                cid = target_clients[idx][0]
                problem_clients.add(cid)
                rt_event('client_send_error', client_id=cid, error=str(res))
        for pc in problem_clients:
            LISTENING_CLIENTS.pop(pc, None)
            CLIENT_IP_MAPPING.pop(pc, None)
            rt_event('client_removed_send_fail', client_id=pc)


@app.on_event("startup")
async def startup_event():
    global ZMQ_TASK
    if ZMQ_TASK is None or ZMQ_TASK.done():
        ZMQ_TASK = asyncio.create_task(_zmq_consume_loop())
        rt_event('zmq_consumer_started')


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


@app.websocket("/listening")
async def websocket_listening_endpoint(websocket: WebSocket):
    await websocket.accept()
    import uuid
    client_id = uuid.uuid4().hex[:8]
    client_ip = _client_ip_from_ws(websocket)

    LISTENING_CLIENTS[client_id] = websocket
    CLIENT_IP_MAPPING[client_id] = client_ip
    rt_event('client_connect', client_id=client_id, client_ip=client_ip, total_clients=len(LISTENING_CLIENTS))

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
                rt_event('client_recv_error', client_id=client_id, error=str(e))
                break
            try:
                data = json.loads(msg)
            except Exception:
                continue
            if data.get('type') == 'ping':
                await websocket.send_text(json.dumps({'type': 'pong', 'ts': datetime.utcnow().isoformat() + 'Z'}))
                rt_event('client_ping', client_id=client_id)
            elif data.get('type') == 'stop_listening':
                await websocket.send_text(json.dumps({'type': 'stopped', 'ts': datetime.utcnow().isoformat() + 'Z'}))
                break
    finally:
        hb_task.cancel()
        LISTENING_CLIENTS.pop(client_id, None)
        CLIENT_IP_MAPPING.pop(client_id, None)
        rt_event('client_disconnect', client_id=client_id, client_ip=client_ip, remaining=len(LISTENING_CLIENTS))


if __name__ == "__main__":
    import uvicorn
    log.info("========================================")
    log.info("Voice WS Server - v1.0.0")
    log.info("========================================")
    log.info(f"ASR_EVENTS_ENDPOINT: {ASR_EVENTS_ENDPOINT}")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
