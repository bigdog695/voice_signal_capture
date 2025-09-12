from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import asyncio
import time
from typing import Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime
import uuid
import numpy as np
import logging
import zmq
from binascii import unhexlify
import scipy.signal
import io
import wave

# ================= Logging & Constants =================
LOG_NAME = "RealtimeListening"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
log = logging.getLogger(LOG_NAME)

IP_WHITE_LIST = ["*"]  # 可改为具体 IP 列表，例如: ["192.168.1.10", "192.168.1.11"]
PRINT_EVERY = 20

def rt_event(event: str, **fields):
    """结构化事件日志 (单行 JSON)，便于后期集中检索。
    示例: rt_event("asr_result", peer_ip="1.2.3.4", text_len=5)
    """
    payload = {"evt": event, "ts": datetime.utcnow().isoformat() + "Z", **fields}
    try:
        log.info("RT " + json.dumps(payload, ensure_ascii=False))
    except Exception:
        log.info(f"RT {{'evt':'{event}','error':'log_serialize_failed'}}")
# 立即初始化示例数据
init_sample_data()

@app.get("/")
async def root():
    """根端点"""
    return {
        "message": "Voice Chat Backend with ASR Service",
        "status": "healthy",
        "asr_model": MODEL_NAME,
        "endpoints": {
            "chat_list": "/chat/list?id=user_001",
            "chat_detail": "/chat/{chat_id}",
            "websocket_chat": "/chatting?id=chat_id",
            "websocket_realtime_listening": "/listening",
            "health": "/health",
            "asr_info": "/asr/info"
        },
        "version": "2.0.0"
    }

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "asr_available": True,  # FunASR是必选的
        "active_connections": len(active_connections),
        "total_chats": len(chat_sessions),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/asr/info")
async def asr_info():
    """ASR服务信息端点"""
    return {
        "status": "available",
        "model": MODEL_NAME,
        "model_revision": MODEL_REV,
        "device": DEVICE,
        "chunk_size": CHUNK_SIZE,
        "stride_size": STRIDE_SIZE,
        "bytes_per_frame": BYTES_PER_FRAME
    }

# 启动时初始化数据
# init_sample_data()  # 移到文件末尾

@app.get("/chat/list")
async def get_chat_list(id: str):
    """
    获取指定用户ID的所有聊天历史
    
    Args:
        id: 用户ID
        
    Returns:
        包含该用户所有chatId的列表
    """
    try:
        if id not in user_chat_history:
            return {"user_id": id, "chat_ids": []}
        
        chat_ids = user_chat_history[id]
        
        # 获取每个聊天的详细信息
        chat_list = []
        for chat_id in chat_ids:
            if chat_id in chat_sessions:
                session = chat_sessions[chat_id]
                chat_info = {
                    "chat_id": chat_id,
                    "title": session.title,
                    "status": session.status,
                    "created_at": session.created_at.isoformat(),
                    "ended_at": session.ended_at.isoformat() if session.ended_at else None,
                    "message_count": len(session.messages)
                }
                chat_list.append(chat_info)
        
        return {
            "user_id": id,
            "chat_list": chat_list
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取聊天列表失败: {str(e)}")

@app.get("/chat/{chat_id}")
async def get_chat_detail(chat_id: str):
    """
    获取指定聊天的详细信息和消息历史
    
    Args:
        chat_id: 聊天ID
        
    Returns:
        聊天的详细信息和消息列表
    """
    try:
        if chat_id not in chat_sessions:
            raise HTTPException(status_code=404, detail="聊天记录不存在")
        
        session = chat_sessions[chat_id]
        return {
            "chat_id": chat_id,
            "title": session.title,
            "status": session.status,
            "created_at": session.created_at.isoformat(),
            "ended_at": session.ended_at.isoformat() if session.ended_at else None,
            "messages": [
                {
                    "id": msg.id,
                    "speaker": msg.speaker,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat()
                }
                for msg in session.messages
            ]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取聊天详情失败: {str(e)}")

@app.websocket("/chatting")
async def chatting_websocket(websocket: WebSocket, id: str):
    """
    WebSocket端点，用于实时聊天
    
    Args:
        id: 聊天ID
    """
    # 直接接受WebSocket连接，不检查聊天状态
    await websocket.accept()
    active_connections[id] = websocket
    
    print(f"WebSocket连接已建立: 聊天ID={id}")
    
    # 发送欢迎消息
    await websocket.send_text(json.dumps({
        "type": "connection_established",
        "chat_id": id,
        "message": "已连接到聊天会话",
        "timestamp": datetime.now().isoformat()
    }))
    
    try:
        # 监听客户端消息
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data.get("type") == "ping":
                # 响应心跳
                await websocket.send_text(json.dumps({
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                }))
            elif message_data.get("type") == "end_chat":
                # 结束聊天
                await websocket.send_text(json.dumps({
                    "type": "chat_ended",
                    "chat_id": id,
                    "message": "聊天已结束",
                    "timestamp": datetime.now().isoformat()
                }))
                break
                
    except WebSocketDisconnect:
        print(f"WebSocket连接断开: 聊天ID={id}")
    except Exception as e:
        print(f"WebSocket错误: {e}")
    finally:
        # 清理连接
        if id in active_connections:
            del active_connections[id]


def _extract_asr_text(result):
    """从ModelScope pipeline结果中提取文本"""
    log.debug(f"ASR结果类型: {type(result)}, 内容: {result}")
    
    if not result:
        log.debug("ASR结果为空")
        return None
    
    # ModelScope pipeline返回格式: [{"value": "识别的文本"}]
    if isinstance(result, list) and result:
        log.debug(f"ASR结果是列表，长度: {len(result)}")
        item = result[0]
        log.debug(f"列表第一项类型: {type(item)}, 内容: {item}")
        
        if isinstance(item, dict):
            log.debug(f"字典键: {list(item.keys())}")
            # ModelScope格式主要是 "value" 键
            for key in ("value", "text", "transcript", "result", "sentence"):
                if key in item and item[key]:
                    text = item[key].strip()
                    if text:  # 确保文本不为空
                        log.debug(f"从键'{key}'提取到文本: '{text}'")
                        return text
            log.debug("字典中未找到有效文本")
        elif isinstance(item, str):
            text = item.strip()
            if text:
                log.debug(f"列表第一项是字符串: '{text}'")
                return text
    elif isinstance(result, str):
        text = result.strip()
        if text:
            log.debug(f"ASR结果是字符串: '{text}'")
            return text
    
    log.debug("未能从ASR结果中提取文本")
    return None

def _decode_audio_data(hex_data):
    """从hex字符串解码WAV文件数据并提取音频采样"""
    try:
        # 将hex字符串转换为字节（这是完整的WAV文件数据）
        wav_bytes = unhexlify(hex_data)
        
        # 使用BytesIO创建内存文件对象
        wav_io = io.BytesIO(wav_bytes)
        
        # 打开WAV文件
        with wave.open(wav_io, 'rb') as wav_file:
            # 获取WAV文件参数
            sample_rate = wav_file.getframerate()
            n_channels = wav_file.getnchannels()
            sample_width = wav_file.getsampwidth()
            n_frames = wav_file.getnframes()
            
            log.debug(f"WAV参数: 采样率={sample_rate}Hz, 声道={n_channels}, 位深={sample_width*8}bit, 帧数={n_frames}")
            
            # 读取音频数据
            audio_bytes = wav_file.readframes(n_frames)
            
            # 转换为numpy数组
            if sample_width == 1:
                audio_data = np.frombuffer(audio_bytes, dtype=np.uint8)
                audio_data = (audio_data.astype(np.float32) - 128) / 128.0
            elif sample_width == 2:
                audio_data = np.frombuffer(audio_bytes, dtype=np.int16)
                audio_data = audio_data.astype(np.float32) / 32768.0
            else:
                raise ValueError(f"不支持的位深: {sample_width*8}bit")
            
            # 如果是立体声，取平均值转为单声道
            if n_channels == 2:
                audio_data = audio_data.reshape(-1, 2).mean(axis=1)
            elif n_channels > 2:
                raise ValueError(f"不支持的声道数: {n_channels}")
            
            return audio_data, sample_rate
            
    except Exception as e:
        log.error(f"解码WAV数据失败: {e}")
        return None, None

def _resample_audio(audio_data, orig_sr, target_sr):
    """音频重采样"""
    if orig_sr == target_sr:
        return audio_data
    
    try:
        # 使用scipy进行重采样
        resampled = scipy.signal.resample_poly(audio_data, target_sr, orig_sr)
        log.debug(f"音频重采样: {orig_sr}Hz -> {target_sr}Hz, 长度: {len(audio_data)} -> {len(resampled)}")
        return resampled.astype(np.float32)
    except Exception as e:
        log.error(f"音频重采样失败: {e}")
        return None

# (去重) 下方原重复 IP_WHITE_LIST/PRINT_EVERY 定义已移除，保持顶部统一配置

async def _process_zmq_voice_data(websocket, connection_state):
    """使用 PULL + multipart (meta_json, pcm_bytes) 模式消费语音数据并调用 funasr 识别"""
    if asr_funasr_model is None:
        log.error("funasr 模型不可用，终止 ZMQ 处理")
        return

    ctx = zmq.Context.instance()
    sock = ctx.socket(zmq.PULL)
    sock.setsockopt(zmq.LINGER, 0)
    zmq_endpoint = "tcp://0.0.0.0:5555"  # 与 zmq_test.py 缺省保持一致
    try:
        sock.bind(zmq_endpoint)
        rt_event("zmq_bind", endpoint=zmq_endpoint)
    except Exception as e:
        rt_event("zmq_bind_error", error=str(e))
        return

    sessions = {}  # (peer_ip, source, call_id) -> state
    call_ids = {}   # (peer_ip, source) -> current call id

    def get_session(peer_ip, source, start_ts=None):
        key_ps = (peer_ip, source)
        call_id = call_ids.get(key_ps, 1)
        key = (peer_ip, source, call_id)
        if key not in sessions:
            sessions[key] = {
                'buffer': bytearray(),
                'chunks': 0,
                'bytes': 0,
                'first_ts': start_ts,
                'last_ts': start_ts,
            }
        return key, sessions[key]

    def rotate_call(peer_ip, source):
        key_ps = (peer_ip, source)
        call_ids[key_ps] = call_ids.get(key_ps, 1) + 1

    async def send_recog(peer_ip, source, call_id, seq, text, meta):
        """发送结构化识别结果: 兼容旧 listening_text + 新 asr_update"""
        if not text:
            return
        message_id = f"{peer_ip}-{source}-{call_id}-{seq}-{uuid.uuid4().hex[:8]}"
        base_info = {
            "peer_ip": peer_ip,
            "source": source,
            "call_id": call_id,
            "sequence": seq,
            "start_ts": meta.get('start_ts'),
            "end_ts": meta.get('end_ts'),
            "timestamp": datetime.now().isoformat(),
        }
        # 新结构 (每个ZMQ段视为最终一句)
        asr_update = {
            "type": "asr_update",
            "messageId": message_id,
            "revision": 0,
            "text": text,
            "is_final": True,
            **base_info,
        }
        # 旧结构（保留一段时间，前端迁移后可移除）
        legacy = {
            "type": "listening_text",
            "text": text,
            **base_info,
        }
        try:
            await websocket.send_text(json.dumps(asr_update, ensure_ascii=False))
            await websocket.send_text(json.dumps(legacy, ensure_ascii=False))
            rt_event("push_result", peer_ip=peer_ip, source=source, call_id=call_id, seq=seq,
                     msg_id=message_id, text_len=len(text))
        except Exception as e:
            rt_event("push_error", error=str(e))
            connection_state["is_alive"] = False

    def process_asr_chunk(pcm_bytes, meta):
        try:
            if not pcm_bytes:
                return None
            # 16-bit 8k PCM -> numpy
            audio_8k = np.frombuffer(pcm_bytes, dtype=np.int16)
            # 升采样到 16k (与脚本一致: 8k -> 16k up=2 down=1)
            audio_16k = scipy.signal.resample_poly(audio_8k, up=2, down=1)
            audio_16k = audio_16k.astype(np.float32) / 32768.0
            result = asr_funasr_model.generate(input=audio_16k)
            if result and len(result) > 0:
                candidate = result[0].get('text')
                if candidate and candidate.strip():
                    return candidate.strip()
        except Exception as e:
            log.error(f"ASR 分块识别失败: {e}")
        return None

    seq_counter = 0
    try:
        while connection_state["is_alive"]:
            try:
                meta_raw, pcm = sock.recv_multipart(flags=zmq.NOBLOCK)
            except zmq.Again:
                await asyncio.sleep(0.01)
                continue
            except Exception as e:
                log.error(f"ZMQ 收包错误: {e}")
                await asyncio.sleep(0.1)
                continue

            try:
                meta = json.loads(meta_raw.decode('utf-8'))
            except Exception as e:
                rt_event("meta_parse_error", error=str(e))
                continue

            peer_ip = meta.get('peer_ip', 'unknown')
            if IP_WHITE_LIST and IP_WHITE_LIST != ["*"] and peer_ip not in IP_WHITE_LIST:
                # 白名单过滤
                continue
            source = meta.get('source', 'unknown')
            start_ts = meta.get('start_ts')
            end_ts = meta.get('end_ts')
            is_finished = bool(meta.get('IsFinished', False))

            key, sess = get_session(peer_ip, source, start_ts)

            if pcm:
                sess['buffer'].extend(pcm)
                sess['bytes'] += len(pcm)
                sess['chunks'] += 1
                if sess['first_ts'] is None:
                    sess['first_ts'] = start_ts
                if end_ts is not None:
                    sess['last_ts'] = end_ts

                # 逐块识别 (模仿脚本实时)
                seq_counter += 1
                text = process_asr_chunk(pcm, meta)
                if text:
                    rt_event("asr_result", peer_ip=peer_ip, source=source, call_id=key[2],
                             seq=seq_counter, text=text)
                    await send_recog(peer_ip, source, key[2], seq_counter, text, meta)

            if sess['chunks'] % PRINT_EVERY == 0:
                rt_event("chunk_progress", peer_ip=peer_ip, source=source, call_id=key[2],
                         chunks=sess['chunks'], bytes=sess['bytes'])

            if is_finished:
                dur_sec = (len(sess['buffer']) / 2) / 8000.0
                rt_event("call_finished", peer_ip=peer_ip, source=source, call_id=key[2],
                         chunks=sess['chunks'], bytes=sess['bytes'], duration_sec=round(dur_sec,2))
                del sessions[key]
                rotate_call(peer_ip, source)
                # 通知前端通话结束
                try:
                    await websocket.send_text(json.dumps({
                        "type": "call_finished",
                        "peer_ip": peer_ip,
                        "source": source,
                        "call_id": key[2],
                        "timestamp": datetime.now().isoformat(),
                    }))
                except Exception:
                    pass
                # 结束一次后退出（与脚本行为保持：收到结束后可停止）
                break

            if asyncio.current_task().cancelled():
                rt_event("zmq_task_cancel_requested")
                break

    except asyncio.CancelledError:
        rt_event("zmq_task_cancelled")
    finally:
        try:
            sock.close(0)
            ctx.term()
        except Exception as e:
            rt_event("zmq_close_error", error=str(e))
        rt_event("zmq_task_stopped")

@app.websocket("/listening")
async def websocket_listening_endpoint(websocket: WebSocket):
    """本机通话监听WebSocket端点 - 真实ZMQ数据源 + ASR识别"""
    await websocket.accept()
    client_id = uuid.uuid4().hex[:8]
    rt_event("client_connect", client_id=client_id, path="/listening")
    
    # 创建共享的连接状态对象
    connection_state = {
        "is_alive": True,
        "connected_at": time.time()
    }
    
    zmq_task = None
    
    try:
        await websocket.send_text("监听服务已连接，正在等待通话数据...")
        rt_event("client_ready", client_id=client_id)

        task = asyncio.create_task(_process_zmq_voice_data(websocket, connection_state))
        while connection_state["is_alive"]:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                message_data = json.loads(data)
                
                if message_data.get("type") == "ping":
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    }))
                    rt_event("client_heartbeat", client_id=client_id)
                elif message_data.get("type") == "stop_listening":
                    connection_state["is_alive"] = False
                    if zmq_task and not zmq_task.done():
                        zmq_task.cancel()
                    await websocket.send_text("监听服务已停止")
                    rt_event("client_stop_request", client_id=client_id)
                    break
                
        except asyncio.TimeoutError:
            # 超时是正常的，继续循环
            # 检查ZMQ任务是否还在运行
            if zmq_task and zmq_task.done():
                # ZMQ任务已结束，检查是否有异常
                try:
                    await zmq_task  # 获取可能的异常
                except asyncio.CancelledError:
                    log.info("ZMQ任务已被取消")
                except Exception as e:
                    log.error(f"ZMQ任务异常结束: {e}")
                # ZMQ任务结束，退出监听循环
                connection_state["is_alive"] = False
                break
            continue
        except json.JSONDecodeError:
            # 如果不是JSON消息，忽略
            continue
        except WebSocketDisconnect:
            # WebSocket断开，立即通知ZMQ任务
            rt_event("client_ws_disconnect", client_id=client_id)
            connection_state["is_alive"] = False
            break

        except WebSocketDisconnect:
            rt_event("client_disconnect", client_id=client_id)
            connection_state["is_alive"] = False
        except Exception as e:
            rt_event("client_error", client_id=client_id, error=str(e))
            connection_state["is_alive"] = False
            try:
                await websocket.close(code=1011, reason="Listening service error")
            except Exception as close_e:
                rt_event("client_close_error", client_id=client_id, error=str(close_e))
        finally:
            # 确保连接状态被标记为断开
            connection_state["is_alive"] = False

            # 确保ZMQ任务被取消
            if zmq_task and not zmq_task.done():
                rt_event("zmq_task_cancelling", client_id=client_id)
                zmq_task.cancel()
                try:
                    await asyncio.wait_for(zmq_task, timeout=2.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    rt_event("zmq_task_cancel_wait_done")
                except Exception as e:
                    rt_event("zmq_task_cancel_error", error=str(e))

            connection_duration = time.time() - connection_state["connected_at"]
            rt_event("client_session_end", client_id=client_id, duration_sec=round(connection_duration,2))

if __name__ == "__main__":
    log.info("========================================")
    log.info("Voice Chat Backend with ASR - v2.0.0")
    log.info("调试模式 - 详细日志已启用")
    log.info("========================================")
    log.info("ASR模型状态: 已加载并可用")
    log.info(f"ASR模型: {MODEL_NAME} (rev: {MODEL_REV})")
    log.info(f"设备: {DEVICE}")
    log.info(f"音频参数: CHUNK_SIZE={CHUNK_SIZE}, ENC_LB={ENC_LB}, DEC_LB={DEC_LB}")
    log.info(f"帧大小: {STRIDE_SIZE} samples ({BYTES_PER_FRAME} bytes)")
    log.info("服务端点:")
    log.info("  - API文档: http://localhost:8000/docs")
    log.info("  - 健康检查: http://localhost:8000/health")
    log.info("  - ASR信息: http://localhost:8000/asr/info")
    log.info("  - 聊天API示例: http://localhost:8000/chat/list?id=user_001")
    log.info("WebSocket端点:")
    log.info("  - 聊天: ws://localhost:8000/chatting?id=chat_active_001")
    log.info("  - 本机监听 (ZMQ+ASR): ws://localhost:8000/listening")
    log.info("========================================")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="debug"  # 设置为debug级别
    )
