import os
import sys
import json
import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional, Set, Tuple, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

script_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(script_dir, ".."))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from common.logging_utils import log_event

"""
Mock WebSocket Server
---------------------
目的：为前端开发/联调提供一个无需 ASR 后端与 ZMQ 的可替代服务。
功能：
  - /health 端点
  - /listening WebSocket：
      * 接受客户端连接，维护心跳（server_heartbeat，每秒）
      * 接收 {"type":"ping"} -> 返回 {"type":"pong"}
      * 接收 {"type":"stop_listening"} -> 返回 {"type":"stopped"} 并断开
  - 周期性模拟 ASR 事件推送给匹配 IP 的客户端（或广播模式）
  - 可配置：事件间隔、事件文本、是否广播、端口
环境变量：
  MOCK_EVENT_INTERVAL   (float, 默认 2.5 秒)
  MOCK_EVENT_BROADCAST  ("1" 广播 / "0" 按 IP 匹配，默认 "1")
  MOCK_EVENT_TEXTS      (逗号分隔文本列表，轮询发送)
  MOCK_SERVER_PORT      (默认 18000，避免与真实 8000 冲突)
  MOCK_HEARTBEAT_SEC    (服务器心跳发送间隔，默认 1 秒)
  MOCK_LOG_LEVEL        (默认 INFO)
  MOCK_CLIENT_IDLE_TIMEOUT (秒，客户端无消息超时仅用于日志，默认 30)
  MOCK_CYCLES_PER_CALL  (完成多少“全文本列表循环”后发送一次 call_finished，默认 1；设置为 3 表示 发送 3 * len(EVENT_TEXTS) 条 asr_update 后再结束)

与 main.py 的差异：
  - 移除了 ZMQ 订阅逻辑，替换为内部 _mock_event_loop
  - 函数命名保持相似，以方便今后替换或对比
"""

LOG_NAME = "MockWSServer"
logging.basicConfig(level=os.getenv('MOCK_LOG_LEVEL', 'INFO').upper(),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger(LOG_NAME)

# ================= Config =================
EVENT_INTERVAL = float(os.getenv("MOCK_EVENT_INTERVAL", "2.5"))
EVENT_BROADCAST = os.getenv("MOCK_EVENT_BROADCAST", "1") == "1"
EVENT_TEXTS = [t.strip() for t in os.getenv("MOCK_EVENT_TEXTS", "语音片段一,语音片段二,语音片段三, 语音片段四").split(",") if t.strip()] or ["示例文本"]
SERVER_PORT = int(os.getenv("MOCK_SERVER_PORT", "18000"))
HEARTBEAT_SEC = float(os.getenv("MOCK_HEARTBEAT_SEC", "1.0"))
CLIENT_IDLE_TIMEOUT = float(os.getenv("MOCK_CLIENT_IDLE_TIMEOUT", "30"))
CYCLES_PER_CALL = max(1, int(os.getenv("MOCK_CYCLES_PER_CALL", "1")))  # 防止 0 或负数
MOCK_ALLOWED_ORIGINS_RAW = os.getenv("MOCK_ALLOWED_ORIGINS", "*")
MOCK_ALLOWED_ORIGINS = [origin.strip() for origin in MOCK_ALLOWED_ORIGINS_RAW.split(",") if origin.strip()] or ["*"]
MOCK_ALLOW_CREDENTIALS_RAW = os.getenv("MOCK_ALLOW_CREDENTIALS", "false")
MOCK_ALLOW_CREDENTIALS = MOCK_ALLOW_CREDENTIALS_RAW.strip().lower() in {"1", "true", "yes", "on"}

app = FastAPI(title="Voice Mock WS Server", version="1.0.0")
allow_all_origins = any(origin == "*" for origin in MOCK_ALLOWED_ORIGINS)
if allow_all_origins and MOCK_ALLOW_CREDENTIALS:
    log_event(log, 'mock_cors_credentials_disabled', reason='wildcard_origin')
    MOCK_ALLOW_CREDENTIALS = False

cors_allow_origins = ["*"] if allow_all_origins else MOCK_ALLOWED_ORIGINS
cors_allow_origin_regex = ".*" if allow_all_origins else None

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_allow_origins,
    allow_origin_regex=cors_allow_origin_regex,
    allow_credentials=MOCK_ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# client_id -> websocket
LISTENING_CLIENTS: Dict[str, WebSocket] = {}
# client_id -> ip
CLIENT_IP_MAPPING: Dict[str, str] = {}

MOCK_TASK: Optional[asyncio.Task] = None


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
        log_event(log, 'ip_extraction_error', error=str(e))
    return ip


async def _send_finish_messages():
    """发送 citizen 和 hot-line 各自的 is_finished = true 消息"""
    if not LISTENING_CLIENTS:
        return
    
    # 准备两个 source 的 finish 消息
    sources = ['citizen', 'hot-line']
    
    for source in sources:
        finish_evt_template = {
            'type': 'asr_update',
            'text': f'[{source} finished]',
            'source': source,
            'is_finished': True
        }
        
        if EVENT_BROADCAST:
            # 广播模式：发送给所有客户端
            tasks: List[asyncio.Task] = []
            for cid, ws in list(LISTENING_CLIENTS.items()):
                peer_ip = CLIENT_IP_MAPPING.get(cid, 'unknown')
                evt = {**finish_evt_template, 'peer_ip': peer_ip}
                log_event(log, 'mock_finish_broadcast', client_id=cid, peer_ip=peer_ip, source=source)
                tasks.append(asyncio.create_task(ws.send_text(json.dumps(evt, ensure_ascii=False))))
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        else:
            # 单播模式：随机选择一个客户端
            import random
            cid, ws = random.choice(list(LISTENING_CLIENTS.items()))
            peer_ip = CLIENT_IP_MAPPING.get(cid, 'unknown')
            evt = {**finish_evt_template, 'peer_ip': peer_ip}
            log_event(log, 'mock_finish_unicast', client_id=cid, peer_ip=peer_ip, source=source)
            try:
                await ws.send_text(json.dumps(evt, ensure_ascii=False))
            except Exception as e:
                log_event(log, 'mock_finish_unicast_error', client_id=cid, source=source, error=str(e))
        
        # 两个 source 之间稍微间隔一下
        await asyncio.sleep(0.5)


async def _mock_event_loop():
    """周期性构造模拟 ASR 事件并分发。"""
    idx = 0
    cycle_count = 0  # how many full text cycles completed
    log_event(log, 'mock_loop_start', interval=EVENT_INTERVAL, broadcast=EVENT_BROADCAST, cycles_per_call=CYCLES_PER_CALL)
    try:
        while True:
            await asyncio.sleep(EVENT_INTERVAL)
            if not LISTENING_CLIENTS:
                continue
            text = EVENT_TEXTS[idx % len(EVENT_TEXTS)]
            # 交替 source: 偶数 -> citizen, 奇数 -> other
            current_source = 'citizen' if (idx % 2) == 0 else 'other'
            idx += 1
            # 事件结构尽量贴近真实 main.py 中 dispatcher 预期
            base_evt = {
                'type': 'asr_update',
                'text': text,
                'peer_ip': None,  # 发送前填充
                'source': current_source
            }
            if EVENT_BROADCAST:
                # 广播：复制并针对每个 client IP 设置 peer_ip
                tasks: List[asyncio.Task] = []
                for cid, ws in list(LISTENING_CLIENTS.items()):
                    peer_ip = CLIENT_IP_MAPPING.get(cid, 'unknown')
                    evt = {**base_evt, 'peer_ip': peer_ip}
                    log_event(log, 'mock_evt_broadcast', client_id=cid, peer_ip=peer_ip)
                    tasks.append(asyncio.create_task(ws.send_text(json.dumps(evt, ensure_ascii=False))))
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
            else:
                # 非广播：随机挑一个 client 发送
                import random
                cid, ws = random.choice(list(LISTENING_CLIENTS.items()))
                peer_ip = CLIENT_IP_MAPPING.get(cid, 'unknown')
                evt = {**base_evt, 'peer_ip': peer_ip}
                log_event(log, 'mock_evt_unicast', client_id=cid, peer_ip=peer_ip)
                try:
                    await ws.send_text(json.dumps(evt, ensure_ascii=False))
                except Exception as e:
                    log_event(log, 'mock_unicast_error', client_id=cid, error=str(e))

            # 当完成一个完整文本列表循环后，判断是否需要发送 call_finished
            if idx % len(EVENT_TEXTS) == 0:
                cycle_count += 1
                log_event(log, 'mock_cycle_complete', cycle_count=cycle_count, cycles_per_call=CYCLES_PER_CALL)
                if cycle_count >= CYCLES_PER_CALL:
                    # 发送两个 source 各自的 is_finished = true 消息
                    await _send_finish_messages()
                    # reset for next call
                    cycle_count = 0
                    # 发完 is_finished 消息后等待 10 秒再开始下一轮
                    log_event(log, 'mock_waiting_next_round', wait_seconds=10)
                    await asyncio.sleep(10)
    except asyncio.CancelledError:
        log_event(log, 'mock_loop_cancel')
    finally:
        log_event(log, 'mock_loop_exit')


@app.on_event("startup")
async def startup_event():
    # Self-check for websockets library presence (similar to real server)
    try:
        import websockets  # noqa: F401
        log_event(log, 'websockets_lib_detected', version=getattr(__import__('websockets'), '__version__', 'unknown'))
    except Exception as e:
        log_event(log, 'websockets_lib_missing', error=str(e))
    global MOCK_TASK
    if MOCK_TASK is None or MOCK_TASK.done():
        MOCK_TASK = asyncio.create_task(_mock_event_loop())
        log_event(log, 'mock_loop_started')


@app.on_event("shutdown")
async def shutdown_event():
    global MOCK_TASK
    if MOCK_TASK and not MOCK_TASK.done():
        MOCK_TASK.cancel()


@app.get("/health")
async def health():
    return {
        'status': 'ok',
        'clients': len(LISTENING_CLIENTS),
        'mock': True,
        'broadcast': EVENT_BROADCAST,
        'interval': EVENT_INTERVAL,
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
    log_event(log, 'client_connect', client_id=client_id, client_ip=client_ip, total_clients=len(LISTENING_CLIENTS))

    last_activity = datetime.utcnow()

    async def server_heartbeat():
        while True:
            try:
                await websocket.send_text(json.dumps({'type': 'server_heartbeat', 'ts': datetime.utcnow().isoformat() + 'Z'}))
                await asyncio.sleep(HEARTBEAT_SEC)
            except Exception:
                break
    hb_task = asyncio.create_task(server_heartbeat())

    try:
        while True:
            try:
                msg = await asyncio.wait_for(websocket.receive_text(), timeout=2.0)
                last_activity = datetime.utcnow()
            except asyncio.TimeoutError:
                # 空闲检测（仅记录日志，不强制断开）
                if (datetime.utcnow() - last_activity).total_seconds() > CLIENT_IDLE_TIMEOUT:
                    log_event(log, 'client_idle', client_id=client_id, idle_sec=(datetime.utcnow() - last_activity).total_seconds())
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
            msg_type = data.get('type')
            if msg_type == 'ping':
                await websocket.send_text(json.dumps({'type': 'pong', 'ts': datetime.utcnow().isoformat() + 'Z'}))
                log_event(log, 'client_ping', client_id=client_id)
            elif msg_type == 'stop_listening':
                await websocket.send_text(json.dumps({'type': 'stopped', 'ts': datetime.utcnow().isoformat() + 'Z'}))
                break
            else:
                log_event(log, 'client_msg_unknown', client_id=client_id, raw=msg_type)
    finally:
        hb_task.cancel()
        LISTENING_CLIENTS.pop(client_id, None)
        CLIENT_IP_MAPPING.pop(client_id, None)
    log_event(log, 'client_disconnect', client_id=client_id, client_ip=client_ip, remaining=len(LISTENING_CLIENTS))


if __name__ == "__main__":
    import uvicorn
    log.info("========================================")
    log.info("Voice Mock WS Server - v1.0.0")
    log.info("========================================")
    log.info(f"PORT: {SERVER_PORT}")
    log.info(f"EVENT_INTERVAL: {EVENT_INTERVAL}s | BROADCAST: {EVENT_BROADCAST}")
    try:
        log_event(log, 'server_starting', port=SERVER_PORT, host='0.0.0.0')
    except Exception:
        pass
    uvicorn.run("mock_server:app", host="0.0.0.0", port=SERVER_PORT, reload=True, log_level="info")
