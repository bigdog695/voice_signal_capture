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

# ASR相关配置
MODEL_NAME: str = "iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online"
MODEL_REV: str = "v2.0.4"
DEVICE: str = "cuda"  # 改为使用GPU

# 音频参数配置
CHUNK_SIZE = [0, 10, 5]  # 600ms frame
ENC_LB = 4  # encoder look-back (chunks) 
DEC_LB = 1  # decoder look-back (chunks)
STRIDE_SIZE = CHUNK_SIZE[1] * 960  # 9600
BYTES_PER_FRAME = STRIDE_SIZE * 2   # 19200 (16-bit PCM)

# 设置日志
logging.basicConfig(
    level=logging.DEBUG,  # 改为DEBUG级别以获取更详细的日志
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
log = logging.getLogger("VoiceChatBackend")

# 数据模型
class ChatMessage(BaseModel):
    id: str
    chat_id: str
    speaker: str  # "user" or "assistant"
    content: str
    timestamp: datetime

class ChatSession(BaseModel):
    id: str
    user_id: str
    title: str
    status: str  # "active" or "ended"
    created_at: datetime
    ended_at: Optional[datetime] = None
    messages: List[ChatMessage] = []

# 创建FastAPI应用
app = FastAPI(title="Voice Chat Backend with ASR", version="2.0.0")

# CORS设置 - 模仿asr folder的配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://localhost:5173", 
        "http://localhost:5174", "http://localhost:5175",
        "http://127.0.0.1:3000", "http://127.0.0.1:5173", 
        "http://127.0.0.1:5174", "http://127.0.0.1:5175",
        "*"  # 开发阶段允许所有域
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

"""说明: 
/ws 端点仍保留旧的 ModelScope streaming 方案 (inference_pipeline)
/listening 端点改为使用 funasr AutoModel + ZMQ PULL + 分块实时识别 (仿照 zmq_test.py)
"""

# 原 streaming 模型 (保留，以兼容 /ws)
inference_pipeline = None
try:
    import os
    import torch
    from modelscope.pipelines import pipeline
    from modelscope.utils.constant import Tasks
    log.info(f"加载流式ASR模型(ModelScope) '{MODEL_NAME}' ...")
    if not torch.cuda.is_available():
        log.warning("GPU不可用，流式模型使用CPU")
        DEVICE = "cpu"
    else:
        log.info(f"使用GPU: {torch.cuda.get_device_name(0)}")
    os.environ.setdefault("MODELSCOPE_CACHE", "./model_cache")
    inference_pipeline = pipeline(
        task=Tasks.auto_speech_recognition,
        model=MODEL_NAME,
        model_revision=MODEL_REV,
        device=DEVICE,
        cache_dir=os.environ["MODELSCOPE_CACHE"],
    )
    log.info("流式ASR模型加载完成 (用于 /ws)")
except Exception as e:
    log.warning(f"流式ASR模型加载失败，将只使用 funasr: {e}")
    inference_pipeline = None

# funasr 模型 (用于 /listening) -------------------------------------------------
FUNASR_MODEL_NAME = "paraformer-zh-streaming"
asr_funasr_model = None
try:
    from funasr import AutoModel as _FunASRAutoModel
    log.info(f"加载 funasr 模型 '{FUNASR_MODEL_NAME}' (GPU 优先) ...")
    device_name = "cuda:0" if ('torch' in globals() and torch.cuda.is_available()) else "cpu"
    asr_funasr_model = _FunASRAutoModel(
        model=FUNASR_MODEL_NAME,
        model_revision="v2.0.4",
        vad_model="fsmn-vad",
        vad_model_revision="v2.0.4",
        punc_model="ct-punc",
        punc_model_revision="v2.0.4",
        device=device_name,
    )
    log.info(f"funasr 模型加载成功 (device={device_name}) 用于 /listening")
except Exception as e:
    log.error(f"funasr 模型加载失败: {e}")
    asr_funasr_model = None

# 模拟数据库
chat_sessions: Dict[str, ChatSession] = {}
active_connections: Dict[str, WebSocket] = {}
user_chat_history: Dict[str, List[str]] = {}  # user_id -> [chat_id, ...]

# 启动时初始化示例数据
def init_sample_data():
    """初始化示例数据"""
    user_id = "user_001"
    
    # 创建几个示例聊天记录
    for i in range(3):
        chat_id = f"chat_{i+1:03d}"
        session = ChatSession(
            id=chat_id,
            user_id=user_id,
            title=f"Call Session {i+1}",
            status="ended",
            created_at=datetime.now(),
            ended_at=datetime.now(),
            messages=[
                ChatMessage(
                    id=f"msg_{chat_id}_001",
                    chat_id=chat_id,
                    speaker="user",
                    content=f"你好，这是第{i+1}次通话的用户消息。",
                    timestamp=datetime.now()
                ),
                ChatMessage(
                    id=f"msg_{chat_id}_002",
                    chat_id=chat_id,
                    speaker="assistant",
                    content=f"您好！这是第{i+1}次通话的AI回复。很高兴为您服务。",
                    timestamp=datetime.now()
                )
            ]
        )
        chat_sessions[chat_id] = session
        
        # 添加到用户聊天历史
        if user_id not in user_chat_history:
            user_chat_history[user_id] = []
        user_chat_history[user_id].append(chat_id)
    
    # 创建一个活跃的聊天会话
    active_chat_id = "chat_active_001"
    active_session = ChatSession(
        id=active_chat_id,
        user_id=user_id,
        title="Active Call Session",
        status="active",
        created_at=datetime.now(),
        messages=[
            ChatMessage(
                id=f"msg_{active_chat_id}_001",
                chat_id=active_chat_id,
                speaker="user",
                content="这是一个正在进行的通话...",
                timestamp=datetime.now()
            )
        ]
    )
    chat_sessions[active_chat_id] = active_session
    user_chat_history[user_id].append(active_chat_id)
    
    log.info(f"示例数据初始化完成: {len(chat_sessions)} 个聊天会话")

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
            "websocket_asr": "/ws",
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

# ASR WebSocket端点 - 只使用真实FunASR
@app.websocket("/ws")
async def asr_websocket_endpoint(websocket: WebSocket):
    """ASR WebSocket端点 - 实时语音识别"""
    await websocket.accept()
    connection_start = time.time()
    log.info(f"ASR WebSocket连接已建立 - 时间戳: {connection_start}")
    
    # 初始化ASR状态
    cache: dict = {}
    buf = bytearray()
    sample_offset = 0  # ModelScope pipeline需要的偏移量
    
    # 性能统计
    frame_count = 0
    total_audio_received = 0
    total_processing_time = 0
    last_log_time = time.time()
    
    # 句子增量跟踪 (同一 messageId 多次修正)
    current_message_id = str(uuid.uuid4())
    current_revision = 0
    last_sent_text = ""
    last_progress_time = time.time()
    sentence_finalized = False
    PUNCT_END = tuple("。！？!?;；.…")
    STABILITY_WAIT = 0.8  # 秒: 若末尾含句末标点且超过此时间无增长则判定完成

    def build_payload(text: str, is_final: bool, rev: int):
        return json.dumps({
            "type": "asr_update",
            "messageId": current_message_id,
            "revision": rev,
            "text": text,
            "is_final": is_final,
            "timestamp": datetime.now().isoformat()
        }, ensure_ascii=False)

    try:
        while True:
            # 接收音频字节数据
            receive_start = time.time()
            chunk = await websocket.receive_bytes()
            receive_time = time.time() - receive_start
            
            chunk_size = len(chunk)
            total_audio_received += chunk_size
            buf.extend(chunk)
            
            log.debug(f"收到音频块: {chunk_size} 字节, 接收耗时: {receive_time*1000:.2f}ms, 缓冲区长度: {len(buf)}")
            
            # 处理完整音频帧
            frames_processed = 0
            while len(buf) >= BYTES_PER_FRAME:
                frame_start = time.time()
                frame = bytes(buf[:BYTES_PER_FRAME])
                del buf[:BYTES_PER_FRAME]
                
                # 转换为浮点音频数据
                conversion_start = time.time()
                audio = (np.frombuffer(frame, dtype=np.int16)
                           .astype(np.float32) / 32768.0)
                conversion_time = time.time() - conversion_start
                
                # 使用ModelScope pipeline进行流式识别
                asr_start = time.time()
                
                result = inference_pipeline(
                    audio,
                    cache=cache,
                    is_final=False,
                    encoder_chunk_look_back=ENC_LB,
                    decoder_chunk_look_back=DEC_LB
                )
                asr_time = time.time() - asr_start
                
                # 提取识别文本
                extract_start = time.time()
                text = _extract_asr_text(result)
                extract_time = time.time() - extract_start
                
                frame_total_time = time.time() - frame_start
                total_processing_time += frame_total_time
                frame_count += 1
                frames_processed += 1
                
                # 发送结果
                if text:
                    # 增量判定
                    send_payload = None
                    finalized_now = False
                    if not last_sent_text:
                        # 初次
                        last_sent_text = text
                        current_revision = 0
                        sentence_finalized = False
                        send_payload = build_payload(last_sent_text, False, current_revision)
                        last_progress_time = time.time()
                    elif text == last_sent_text:
                        # 无新内容，检查是否需要 finalize (标点 + 稳定时间)
                        if (not sentence_finalized and last_sent_text.endswith(PUNCT_END)
                                and time.time() - last_progress_time >= STABILITY_WAIT):
                            sentence_finalized = True
                            finalized_now = True
                            send_payload = build_payload(last_sent_text, True, current_revision)
                    else:
                        # 是否延续 (前缀扩展)
                        if text.startswith(last_sent_text):
                            # 修正 / 追加
                            last_sent_text = text
                            current_revision += 1
                            sentence_finalized = False
                            send_payload = build_payload(last_sent_text, False, current_revision)
                            last_progress_time = time.time()
                        else:
                            # 新句子开始 -> 先 finalize 旧句子 (若未 final)
                            finalize_payload = None
                            if not sentence_finalized and last_sent_text:
                                finalize_payload = build_payload(last_sent_text, True, current_revision)
                            # 新句子
                            current_message_id = str(uuid.uuid4())
                            current_revision = 0
                            last_sent_text = text
                            sentence_finalized = False
                            new_payload = build_payload(last_sent_text, False, current_revision)
                            last_progress_time = time.time()
                            # 发送顺序: finalize 旧 -> 新增量
                            if finalize_payload:
                                await websocket.send_text(finalize_payload)
                            send_payload = new_payload

                    if send_payload:
                        send_start = time.time()
                        await websocket.send_text(send_payload)
                        send_time = time.time() - send_start
                        log.info(
                            f"ASR识别[帧{frame_count}] rev={current_revision} final={sentence_finalized and finalized_now}: '{last_sent_text}' | 处理: {frame_total_time*1000:.2f}ms "
                            f"(转换:{conversion_time*1000:.2f}ms + ASR:{asr_time*1000:.2f}ms + 提取:{extract_time*1000:.2f}ms + 发送:{send_time*1000:.2f}ms)"
                        )
                else:
                    log.debug(
                        f"ASR无输出[帧{frame_count}] | 处理: {frame_total_time*1000:.2f}ms (转换:{conversion_time*1000:.2f}ms + ASR:{asr_time*1000:.2f}ms + 提取:{extract_time*1000:.2f}ms)"
                    )
            
            # 每5秒输出一次统计信息
            current_time = time.time()
            if current_time - last_log_time >= 5.0:
                avg_processing_time = (total_processing_time / frame_count * 1000) if frame_count > 0 else 0
                connection_duration = current_time - connection_start
                audio_rate = total_audio_received / connection_duration if connection_duration > 0 else 0
                frame_rate = frame_count / connection_duration if connection_duration > 0 else 0
                
                log.info(f"=== ASR性能统计 ===")
                log.info(f"连接时长: {connection_duration:.1f}s")
                log.info(f"总音频数据: {total_audio_received} 字节 ({audio_rate:.1f} 字节/秒)")
                log.info(f"处理帧数: {frame_count} ({frame_rate:.2f} 帧/秒)")
                log.info(f"平均处理时间: {avg_processing_time:.2f}ms/帧")
                log.info(f"缓冲区状态: {len(buf)} 字节")
                
                last_log_time = current_time
                    
    except WebSocketDisconnect:
        disconnect_time = time.time()
        log.info(f"ASR客户端断开连接 - 处理最终音频 | 连接时长: {disconnect_time - connection_start:.2f}s")
        
        # 处理剩余的音频缓冲区
        if buf:
            final_start = time.time()
            audio = (np.frombuffer(buf, dtype=np.int16)
                       .astype(np.float32) / 32768.0)
            result = inference_pipeline(
                audio,
                cache=cache,
                is_final=True,
                encoder_chunk_look_back=ENC_LB,
                decoder_chunk_look_back=DEC_LB,
            )
            final_time = time.time() - final_start
            text = _extract_asr_text(result)
            if text:
                # 若当前句子未 finalize 先 finalize 旧的
                if last_sent_text and last_sent_text != text and not sentence_finalized:
                    await websocket.send_text(json.dumps({
                        "type": "asr_update",
                        "messageId": current_message_id,
                        "revision": current_revision,
                        "text": last_sent_text,
                        "is_final": True,
                        "timestamp": datetime.now().isoformat()
                    }, ensure_ascii=False))
                # 最终帧文本（可能是最后增量或新句）
                await websocket.send_text(json.dumps({
                    "type": "asr_update",
                    "messageId": current_message_id,
                    "revision": current_revision + (0 if text == last_sent_text else 1),
                    "text": text,
                    "is_final": True,
                    "timestamp": datetime.now().isoformat()
                }, ensure_ascii=False))
                log.info(f"ASR最终识别: '{text}' | 处理: {final_time*1000:.2f}ms")
            else:
                # 若没有新文本但存在未 finalize 的句子
                if last_sent_text and not sentence_finalized:
                    await websocket.send_text(json.dumps({
                        "type": "asr_update",
                        "messageId": current_message_id,
                        "revision": current_revision,
                        "text": last_sent_text,
                        "is_final": True,
                        "timestamp": datetime.now().isoformat()
                    }, ensure_ascii=False))
                    log.info(f"ASR最终补发 finalize: '{last_sent_text}'")
                else:
                    log.info(f"ASR最终处理无输出 | 处理: {final_time*1000:.2f}ms")
    except Exception as e:
        error_time = time.time()
        log.error(f"ASR WebSocket错误: {e} | 连接时长: {error_time - connection_start:.2f}s")
        await websocket.close(code=1011, reason="ASR processing error")
    finally:
        final_time = time.time()
        total_duration = final_time - connection_start
        avg_processing = (total_processing_time / frame_count * 1000) if frame_count > 0 else 0
        log.info(f"ASR WebSocket连接已关闭 | 总时长: {total_duration:.2f}s | 总帧数: {frame_count} | 平均处理: {avg_processing:.2f}ms/帧")

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

IP_WHITE_LIST = ["192.168.10.19"]  # 与 zmq_test.py 一致，可按需修改
PRINT_EVERY = 20

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
        log.info(f"ZMQ PULL 绑定 {zmq_endpoint}")
    except Exception as e:
        log.error(f"ZMQ 绑定失败: {e}")
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
        if not text:
            return
        payload = {
            "type": "listening_text",
            "peer_ip": peer_ip,
            "source": source,
            "call_id": call_id,
            "sequence": seq,
            "text": text,
            "start_ts": meta.get('start_ts'),
            "end_ts": meta.get('end_ts'),
            "timestamp": datetime.now().isoformat(),
        }
        try:
            await websocket.send_text(json.dumps(payload))
        except Exception as e:
            log.warning(f"发送识别结果失败: {e}")
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
                log.warning(f"解析 meta JSON 失败: {e}")
                continue

            peer_ip = meta.get('peer_ip', 'unknown')
            if peer_ip not in IP_WHITE_LIST:
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
                    await send_recog(peer_ip, source, key[2], seq_counter, text, meta)

            if sess['chunks'] % PRINT_EVERY == 0:
                log.debug(f"[CHUNK] {peer_ip} {source} call#{key[2]} chunks={sess['chunks']} bytes={sess['bytes']}")

            if is_finished:
                dur_sec = (len(sess['buffer']) / 2) / 8000.0
                log.info(f"[CALL DONE] {peer_ip} {source} call#{key[2]} chunks={sess['chunks']} bytes={sess['bytes']} dur≈{dur_sec:.2f}s")
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
                log.info("ZMQ任务取消")
                break

    except asyncio.CancelledError:
        log.info("ZMQ处理任务被取消 (外部)" )
    finally:
        try:
            sock.close(0)
            ctx.term()
        except Exception as e:
            log.warning(f"关闭ZMQ资源异常: {e}")
        log.info("ZMQ语音数据处理器已关闭")

@app.websocket("/listening")
async def websocket_listening_endpoint(websocket: WebSocket):
    """本机通话监听WebSocket端点 - 真实ZMQ数据源 + ASR识别"""
    await websocket.accept()
    log.info("本机监听客户端已连接")
    
    # 创建共享的连接状态对象
    connection_state = {
        "is_alive": True,
        "connected_at": time.time()
    }
    
    zmq_task = None
    
    try:
        # 发送连接确认
        await websocket.send_text("监听服务已连接，正在等待通话数据...")
        
        # 启动ZMQ语音数据处理任务，传入共享状态
        zmq_task = asyncio.create_task(_process_zmq_voice_data(websocket, connection_state))
        
        # 监听客户端消息
        while connection_state["is_alive"]:
            try:
                # 设置短超时，避免阻塞ZMQ处理
                data = await asyncio.wait_for(websocket.receive_text(), timeout=1.0)
                message_data = json.loads(data)
                
                if message_data.get("type") == "ping":
                    # 响应心跳
                    await websocket.send_text(json.dumps({
                        "type": "pong",
                        "timestamp": datetime.now().isoformat()
                    }))
                elif message_data.get("type") == "stop_listening":
                    # 停止监听
                    connection_state["is_alive"] = False
                    if zmq_task and not zmq_task.done():
                        zmq_task.cancel()
                    await websocket.send_text("监听服务已停止")
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
                log.info("监听WebSocket连接断开")
                connection_state["is_alive"] = False
                break
                
    except WebSocketDisconnect:
        log.info("监听客户端断开连接")
        connection_state["is_alive"] = False
    except Exception as e:
        log.error(f"监听WebSocket错误: {e}")
        connection_state["is_alive"] = False
        try:
            await websocket.close(code=1011, reason="Listening service error")
        except Exception as close_e:
            log.error(f"关闭WebSocket时出错: {close_e}")
    finally:
        # 确保连接状态被标记为断开
        connection_state["is_alive"] = False
        
        # 确保ZMQ任务被取消
        if zmq_task and not zmq_task.done():
            log.info("正在取消ZMQ处理任务...")
            zmq_task.cancel()
            try:
                await asyncio.wait_for(zmq_task, timeout=2.0)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                log.info("ZMQ任务已取消")
            except Exception as e:
                log.error(f"取消ZMQ任务时出错: {e}")
        
        connection_duration = time.time() - connection_state["connected_at"]
        log.info(f"监听服务已关闭，连接时长: {connection_duration:.2f}s")

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
    log.info("  - ASR: ws://localhost:8000/ws")
    log.info("  - 本机监听 (ZMQ+ASR): ws://localhost:8000/listening")
    log.info("========================================")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="debug"  # 设置为debug级别
    )
