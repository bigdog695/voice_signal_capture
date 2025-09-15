import asyncio
import json
import random
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, WebSocket, Request
import uvicorn

app = FastAPI(title="Mock ASR Server", version="0.1.0")

@app.get('/health')
async def health():
    return {"status": "ok", "ts": datetime.utcnow().isoformat() + 'Z'}

@app.get('/whitelist/register')
async def whitelist_register(request: Request, ip: Optional[str] = None):
    client_ip = ip or (request.client.host if request.client else 'unknown')
    return {"ok": True, "ip": client_ip, "ts": datetime.utcnow().isoformat() + 'Z'}

# Predefined sample texts (simulate recognition outputs)
SAMPLE_TEXTS = [
    "你好，请问需要什么帮助？",
    "我想咨询一下医保的问题。",
    "您现在所在的地区是哪里？",
    "我在江苏。",
    "好的，我帮您查询一下。",
    "请稍等。",
    "这是一个测试句子。",
    "那我们继续。",
]

async def emit_sequence(ws: WebSocket, scenario: str):
    seq = 0
    call_ids = {"citizen": 0, "hot-line": 0}
    try:
        while True:
            await asyncio.sleep(0.8 if scenario != 'rapid' else 0.25)
            source = random.choice(["citizen", "hot-line"]) if scenario != 'single_source' else 'citizen'
            call_ids[source] += 1
            base_text = random.choice(SAMPLE_TEXTS)
            # Duplicate scenario: occasionally send the same text twice with different segmentIds
            dup = scenario in ('duplicate', 'mixed') and random.random() < 0.25
            repeats = 2 if dup else 1
            for r in range(repeats):
                seq += 1
                segment_id = f"mock-{seq}"
                text = base_text
                if scenario == 'long_text' and random.random() < 0.3:
                    text = base_text + " 这是额外的一段解释，用于测试长文本换行显示。" * random.randint(1, 2)
                msg = {
                    'type': 'asr_update',
                    'segmentId': segment_id,
                    'revision': 0,
                    'text': text,
                    'stable_len': len(text),
                    'is_final': True,
                    'peer_ip': 'mock-ip',
                    'source': source,
                    'call_id': call_ids[source],
                    'sequence': seq,
                    'start_ts': datetime.utcnow().timestamp() - 1,
                    'end_ts': datetime.utcnow().timestamp(),
                    'timestamp': datetime.utcnow().isoformat() + 'Z'
                }
                await ws.send_text(json.dumps(msg, ensure_ascii=False))
    except Exception:
        pass

@app.websocket('/listening')
async def listening(ws: WebSocket, scenario: Optional[str] = 'basic'):
    await ws.accept()
    await ws.send_text("监听服务已连接 (mock)")
    await ws.send_text(json.dumps({'type': 'listening_ready', 'scenario': scenario, 'ts': datetime.utcnow().isoformat() + 'Z'}))
    producer = asyncio.create_task(emit_sequence(ws, scenario or 'basic'))
    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
            except Exception:
                continue
            if msg.get('type') == 'ping':
                await ws.send_text(json.dumps({'type': 'pong', 'ts': datetime.utcnow().isoformat() + 'Z'}))
            if msg.get('type') == 'stop_listening':
                await ws.send_text(json.dumps({'type': 'stopped'}))
                break
    except Exception:
        pass
    finally:
        producer.cancel()

if __name__ == '__main__':
    uvicorn.run('mock_server:app', host='0.0.0.0', port=9000, reload=False)
