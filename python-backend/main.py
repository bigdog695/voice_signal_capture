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
DEVICE: str = "cpu"

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

# ASR模型初始化 - 最小化ModelScope使用
inference_pipeline = None
try:
    log.info(f"加载ASR模型 '{MODEL_NAME}' ...")
    
    import os
    from modelscope.pipelines import pipeline
    from modelscope.utils.constant import Tasks
    
    # 设置模型缓存目录
    os.environ["MODELSCOPE_CACHE"] = "./model_cache"
    
    # 创建推理pipeline (优先使用本地缓存)
    inference_pipeline = pipeline(
        task=Tasks.auto_speech_recognition,
        model=MODEL_NAME,
        model_revision=MODEL_REV,
        cache_dir=os.environ.get("MODELSCOPE_CACHE", "./model_cache")
    )
    
    log.info("ASR模型加载成功")
except ImportError as e:
    log.error("ModelScope未正确安装")
    raise RuntimeError("ModelScope依赖缺失") from e
except Exception as exc:
    log.error(f"ASR模型加载失败: {exc}")
    raise RuntimeError(f"ASR模型加载失败: {exc}") from exc

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
    
    # 发送一些模拟的历史消息
    mock_messages = [
        {"speaker": "user", "content": "你好，我想反映一个冰箱维修的问题。"},
        {"speaker": "assistant", "content": "您好！我是客服人员，很高兴为您服务。请详细描述一下具体情况。"},
        {"speaker": "user", "content": "我在2020年购买的冰箱现在出现故障，商家不予维修。"},
        {"speaker": "assistant", "content": "这种情况确实需要核查。请提供商家的详细信息，我们会尽快处理。"}
    ]
    
    for i, msg in enumerate(mock_messages):
        await websocket.send_text(json.dumps({
            "type": "message_history",
            "chat_id": id,
            "message_id": f"mock_msg_{i+1}",
            "speaker": msg["speaker"],
            "content": msg["content"],
            "timestamp": datetime.now().isoformat()
        }))
    
    try:
        # 启动定期发送模拟消息的任务
        asyncio.create_task(simulate_conversation(websocket, id))
        
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

async def simulate_conversation(websocket: WebSocket, chat_id: str):
    """
    模拟实时语音识别对话，快速密集推送消息 - 客服投诉场景
    """
    try:
        # 模拟实时语音识别 - 客服投诉场景
        conversation_segments = [
            # 第一阶段：问候和开场 - 用户第一句话
            {"speaker": "user", "content": "你", "delay": 0.3, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好", "delay": 0.2, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，", "delay": 0.15, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我", "delay": 0.2, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我想", "delay": 0.3, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我想投", "delay": 0.2, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我想投诉", "delay": 0.25, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我想投诉一个", "delay": 0.3, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我想投诉一个电器", "delay": 0.2, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我想投诉一个电器商家", "delay": 0.4, "message_group": "user_msg_1"},
            
            # 客服回复
            {"speaker": "assistant", "content": "您", "delay": 0.6, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好", "delay": 0.2, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！", "delay": 0.15, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我", "delay": 0.2, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我是", "delay": 0.2, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我是客服", "delay": 0.25, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我是客服人员", "delay": 0.2, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我是客服人员，请", "delay": 0.2, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我是客服人员，请详细", "delay": 0.3, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我是客服人员，请详细说明", "delay": 0.2, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我是客服人员，请详细说明您的投诉情况", "delay": 0.4, "message_group": "assistant_msg_1"},
            
            # 第二阶段：详细描述问题 - 用户第二句话
            {"speaker": "user", "content": "我", "delay": 0.8, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "我在", "delay": 0.2, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "我在2020年", "delay": 0.2, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "我在2020年在", "delay": 0.2, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "我在2020年在六安", "delay": 0.2, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "我在2020年在六安索伊", "delay": 0.25, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "我在2020年在六安索伊电器", "delay": 0.2, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "我在2020年在六安索伊电器制造", "delay": 0.3, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "我在2020年在六安索伊电器制造有限公司", "delay": 0.4, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "我在2020年在六安索伊电器制造有限公司买了", "delay": 0.3, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "我在2020年在六安索伊电器制造有限公司买了一台", "delay": 0.25, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "我在2020年在六安索伊电器制造有限公司买了一台双开门", "delay": 0.3, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "我在2020年在六安索伊电器制造有限公司买了一台双开门冰箱", "delay": 0.4, "message_group": "user_msg_2"},
            
            # 客服第二次回复
            {"speaker": "assistant", "content": "好", "delay": 0.5, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "好的", "delay": 0.15, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "好的，我", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "好的，我记录", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "好的，我记录一下", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "好的，我记录一下您的", "delay": 0.25, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "好的，我记录一下您的情况", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "好的，我记录一下您的情况。请问", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "好的，我记录一下您的情况。请问冰箱", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "好的，我记录一下您的情况。请问冰箱现在", "delay": 0.25, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "好的，我记录一下您的情况。请问冰箱现在出现", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "好的，我记录一下您的情况。请问冰箱现在出现什么", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "好的，我记录一下您的情况。请问冰箱现在出现什么问题", "delay": 0.4, "message_group": "assistant_msg_2"},
            
            # 第三阶段：具体问题描述 - 用户第三句话
            {"speaker": "user", "content": "冰", "delay": 0.7, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "冰箱", "delay": 0.2, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "冰箱现在", "delay": 0.2, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "冰箱现在完全", "delay": 0.2, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "冰箱现在完全不", "delay": 0.2, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "冰箱现在完全不制冷", "delay": 0.25, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "冰箱现在完全不制冷了", "delay": 0.2, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "冰箱现在完全不制冷了，花了", "delay": 0.3, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "冰箱现在完全不制冷了，花了2850元", "delay": 0.4, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "冰箱现在完全不制冷了，花了2850元买的", "delay": 0.3, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "冰箱现在完全不制冷了，花了2850元买的，说是", "delay": 0.25, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "冰箱现在完全不制冷了，花了2850元买的，说是保修", "delay": 0.3, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "冰箱现在完全不制冷了，花了2850元买的，说是保修6年", "delay": 0.4, "message_group": "user_msg_3"},
            
            # 客服第三次回复
            {"speaker": "assistant", "content": "明", "delay": 0.6, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "明白", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "明白了", "delay": 0.15, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "明白了，那", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "明白了，那现在", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "明白了，那现在还在", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "明白了，那现在还在保修期", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "明白了，那现在还在保修期内", "delay": 0.25, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "明白了，那现在还在保修期内。您有", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "明白了，那现在还在保修期内。您有联系", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "明白了，那现在还在保修期内。您有联系过", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "明白了，那现在还在保修期内。您有联系过商家", "delay": 0.25, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "明白了，那现在还在保修期内。您有联系过商家维修吗", "delay": 0.4, "message_group": "assistant_msg_3"},
            
            # 第四阶段：投诉重点 - 用户第四句话
            {"speaker": "user", "content": "联", "delay": 0.8, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "联系", "delay": 0.2, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "联系过", "delay": 0.2, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "联系过了", "delay": 0.2, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "联系过了，但是", "delay": 0.25, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "联系过了，但是他们", "delay": 0.2, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "联系过了，但是他们一直", "delay": 0.3, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "联系过了，但是他们一直拖延", "delay": 0.2, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "联系过了，但是他们一直拖延不来", "delay": 0.3, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "联系过了，但是他们一直拖延不来维修", "delay": 0.4, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "联系过了，但是他们一直拖延不来维修，而且", "delay": 0.3, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "联系过了，但是他们一直拖延不来维修，而且态度", "delay": 0.25, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "联系过了，但是他们一直拖延不来维修，而且态度特别", "delay": 0.3, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "联系过了，但是他们一直拖延不来维修，而且态度特别恶劣", "delay": 0.4, "message_group": "user_msg_4"},
            
            # 客服第四次回复
            {"speaker": "assistant", "content": "这", "delay": 0.5, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种", "delay": 0.15, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该发生", "delay": 0.25, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该发生。我", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该发生。我会", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该发生。我会立即", "delay": 0.25, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该发生。我会立即联系", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该发生。我会立即联系相关", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该发生。我会立即联系相关部门", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该发生。我会立即联系相关部门核查", "delay": 0.25, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该发生。我会立即联系相关部门核查此事", "delay": 0.3, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该发生。我会立即联系相关部门核查此事，督促", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该发生。我会立即联系相关部门核查此事，督促商家", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该发生。我会立即联系相关部门核查此事，督促商家尽快", "delay": 0.25, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "这种情况确实不应该发生。我会立即联系相关部门核查此事，督促商家尽快维修", "delay": 0.4, "message_group": "assistant_msg_4"},
        ]
        
        # 快速推送所有消息段
        for segment in conversation_segments:
            await asyncio.sleep(segment["delay"])
            
            # 使用message_group作为message_id，确保同一组消息使用相同ID
            message_id = segment["message_group"]
            
            # 发送消息段
            await websocket.send_text(json.dumps({
                "type": "new_message",
                "chat_id": chat_id,
                "message_id": message_id,
                "speaker": segment["speaker"],
                "content": segment["content"],
                "timestamp": datetime.now().isoformat(),
                "is_partial": True  # 大部分消息都是部分消息
            }))
            
            print(f"客服实时推送: {segment['speaker']} - {segment['content']}")
        
        # 继续循环推送更多实时内容
        await asyncio.sleep(1)
        
        # 第二轮：详细信息确认
        followup_segments = [
            {"speaker": "user", "content": "那", "delay": 0.8, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "那公司", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "那公司地址", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "那公司地址是", "delay": 0.25, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "那公司地址是在", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "那公司地址是在六安市", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "那公司地址是在六安市经济", "delay": 0.25, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "那公司地址是在六安市经济技术", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "那公司地址是在六安市经济技术开发区", "delay": 0.3, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "那公司地址是在六安市经济技术开发区皋城路", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "那公司地址是在六安市经济技术开发区皋城路364号", "delay": 0.3, "message_group": "user_msg_5"},
            
            {"speaker": "assistant", "content": "好", "delay": 0.6, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的", "delay": 0.15, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我已经", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我已经记录", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我已经记录了", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我已经记录了详细", "delay": 0.25, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我已经记录了详细地址", "delay": 0.3, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我已经记录了详细地址。我们", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我已经记录了详细地址。我们会在", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我已经记录了详细地址。我们会在48小时", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我已经记录了详细地址。我们会在48小时内", "delay": 0.25, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我已经记录了详细地址。我们会在48小时内给您", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我已经记录了详细地址。我们会在48小时内给您回复", "delay": 0.3, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我已经记录了详细地址。我们会在48小时内给您回复处理", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "好的，我已经记录了详细地址。我们会在48小时内给您回复处理结果", "delay": 0.4, "message_group": "assistant_msg_5"},
        ]
        
        # 快速推送后续对话
        for segment in followup_segments:
            await asyncio.sleep(segment["delay"])
            
            message_id = segment["message_group"]
            await websocket.send_text(json.dumps({
                "type": "new_message",
                "chat_id": chat_id,
                "message_id": message_id,
                "speaker": segment["speaker"],
                "content": segment["content"],
                "timestamp": datetime.now().isoformat(),
                "is_partial": True
            }))
            
            print(f"详细确认: {segment['speaker']} - {segment['content']}")
        
        # 发送对话结束标记
        await asyncio.sleep(1)
        await websocket.send_text(json.dumps({
            "type": "conversation_complete",
            "chat_id": chat_id,
            "message": "客服投诉处理演示完成",
            "timestamp": datetime.now().isoformat()
        }))
        
    except Exception as e:
        print(f"模拟对话错误: {e}")

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
                    send_start = time.time()
                    await websocket.send_text(text)
                    send_time = time.time() - send_start
                    log.info(f"ASR识别[帧{frame_count}]: '{text}' | 处理: {frame_total_time*1000:.2f}ms (转换:{conversion_time*1000:.2f}ms + ASR:{asr_time*1000:.2f}ms + 提取:{extract_time*1000:.2f}ms + 发送:{send_time*1000:.2f}ms)")
                else:
                    log.debug(f"ASR无输出[帧{frame_count}] | 处理: {frame_total_time*1000:.2f}ms (转换:{conversion_time*1000:.2f}ms + ASR:{asr_time*1000:.2f}ms + 提取:{extract_time*1000:.2f}ms)")
            
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
                await websocket.send_text(text)
                log.info(f"ASR最终识别: '{text}' | 处理: {final_time*1000:.2f}ms")
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

async def _process_zmq_voice_data(websocket, connection_state):
    """处理ZMQ语音数据的异步函数"""
    # 初始化ZMQ订阅者
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://localhost:5555")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")  # 订阅所有消息
    socket.RCVTIMEO = 100  # 100ms超时
    
    # 初始化ASR状态
    cache: dict = {}
    last_sent_text = ""  # 上次发送的文本
    current_full_text = ""  # 当前完整文本
    current_message_id = str(uuid.uuid4())  # 当前消息ID
    
    # 滑动窗口参数
    max_cache_chunks = 100  # 最大缓存音频块数
    chunk_counter = 0  # 音频块计数器
    cache_reset_interval = 5  # 每5个块重置一次缓存 (降低间隔)
    last_message_reset = 0  # 上次重置消息ID的块计数
    
    log.info("ZMQ语音数据处理器已启动，监听端口5555")
    
    try:
        while connection_state["is_alive"]:
            try:
                # 检查任务是否被取消
                if asyncio.current_task().cancelled():
                    log.info("ZMQ处理任务收到取消信号")
                    break
                
                # 检查共享连接状态，无需单独的心跳检测
                if not connection_state["is_alive"]:
                    log.info("检测到WebSocket连接已断开，退出ZMQ处理循环")
                    break
                
                # 接收ZMQ消息
                message = socket.recv_json(zmq.NOBLOCK)
                
                if message["type"] == "voice_segment":
                    log.debug(f"收到语音段: 呼叫ID={message['call_id']}, 序列={message['sequence']}, 数据大小={len(message['data'])//2}字节")
                    
                    chunk_counter += 1
                    
                    # 定期重置缓存以防止内存泄漏
                    should_reset_cache = chunk_counter % cache_reset_interval == 0
                    
                    if should_reset_cache:
                        log.info(f"重置ASR缓存 (处理了 {chunk_counter} 个音频块)")
                        # 保留最近的识别结果作为上下文
                        if current_full_text:
                            # 只保留最近的部分文本作为上下文
                            words = current_full_text.split()
                            if len(words) > 50:  # 只保留最近50个词
                                current_full_text = " ".join(words[-50:])
                        cache.clear()
                        # 生成新的消息ID，表示开始新的语音句子
                        current_message_id = str(uuid.uuid4())
                        last_message_reset = chunk_counter
                        log.info(f"生成新消息ID: {current_message_id} (重置间隔: {chunk_counter - last_message_reset})")
                        last_sent_text = ""  # 重置已发送文本
                    
                    # 解码WAV文件数据并提取音频采样
                    audio_data, orig_sr = _decode_audio_data(message['data'])
                    if audio_data is None:
                        continue
                    
                    # 升采样到16kHz (FunASR要求)
                    target_sr = 16000
                    if orig_sr != target_sr:
                        audio_data = _resample_audio(audio_data, orig_sr, target_sr)
                        if audio_data is None:
                            continue
                    
                    # 使用ASR识别
                    try:
                        result = inference_pipeline(
                            audio_data,
                            cache=cache,
                            is_final=False,
                            encoder_chunk_look_back=ENC_LB,
                            decoder_chunk_look_back=DEC_LB
                        )
                        
                        # 提取识别文本
                        text = _extract_asr_text(result)
                        if text:
                            current_full_text = text
                            
                            # 只发送新增的文本部分
                            if text != last_sent_text:
                                # 计算新增的文本
                                if last_sent_text and text.startswith(last_sent_text):
                                    # 提取新增部分
                                    new_text = text[len(last_sent_text):].strip()
                                    if new_text:
                                        send_text = text  # 发送完整文本，让前端处理增量显示
                                    else:
                                        send_text = None  # 没有新内容
                                else:
                                    # 文本完全不同，发送完整文本
                                    send_text = text
                                
                                if send_text and connection_state["is_alive"]:
                                    try:
                                        # 发送带有消息ID的文本
                                        message_data = {
                                            "type": "listening_text",
                                            "messageId": current_message_id,
                                            "text": send_text,
                                            "timestamp": datetime.now().isoformat(),
                                            "chunk_number": chunk_counter
                                        }
                                        await asyncio.wait_for(websocket.send_text(json.dumps(message_data)), timeout=1.0)
                                        log.info(f"发送ASR结果 - 块#{chunk_counter}, 消息ID: {current_message_id}, 文本: '{send_text}'")
                                        last_sent_text = text
                                        log.debug(f"发送结构体: {json.dumps(message_data)}")
                                    except (asyncio.TimeoutError, Exception) as e:
                                        log.warning(f"发送ASR结果失败，WebSocket可能已断开: {e}")
                                        connection_state["is_alive"] = False
                                        break
                                else:
                                    log.debug(f"无新内容或连接已断开 (块#{chunk_counter})")
                            else:
                                log.debug(f"文本无变化，跳过发送 (块#{chunk_counter})")
                    
                    except Exception as e:
                        log.error(f"ASR识别失败 (块#{chunk_counter}): {e}")
                        # ASR失败时考虑重置缓存
                        if "memory" in str(e).lower() or "timeout" in str(e).lower():
                            log.warning("检测到内存或超时错误，重置ASR缓存")
                            cache.clear()
                            current_message_id = str(uuid.uuid4())  # 生成新消息ID
                            log.info(f"错误重置后生成新消息ID: {current_message_id}")
                            last_message_reset = chunk_counter
                            chunk_counter = 0
                            last_sent_text = ""
                
                elif message["type"] == "call_end":
                    log.info(f"通话结束: 呼叫ID={message['call_id']}")
                    # 发送最终结果
                    if current_full_text:
                        try:
                            # 最终识别
                            result = inference_pipeline(
                                np.array([]),  # 空数组表示结束
                                cache=cache,
                                is_final=True,
                                encoder_chunk_look_back=ENC_LB,
                                decoder_chunk_look_back=DEC_LB
                            )
                            final_text = _extract_asr_text(result)
                            final_result = final_text if final_text else current_full_text
                            if connection_state["is_alive"]:
                                try:
                                    await asyncio.wait_for(websocket.send_text(f"[通话结束] {final_result}"), timeout=1.0)
                                    log.info(f"发送最终识别结果: 总块数={chunk_counter}, 最终文本='{final_result}'")
                                except (asyncio.TimeoutError, Exception) as e:
                                    log.warning(f"发送最终结果失败: {e}")
                                    connection_state["is_alive"] = False
                            else:
                                log.info("连接已断开，跳过发送最终结果")
                        except Exception as e:
                            log.error(f"最终ASR识别失败: {e}")
                            if connection_state["is_alive"]:
                                try:
                                    await asyncio.wait_for(websocket.send_text(f"[通话结束] {current_full_text}"), timeout=1.0)
                                except:
                                    connection_state["is_alive"] = False
                    else:
                        if connection_state["is_alive"]:
                            try:
                                await asyncio.wait_for(websocket.send_text("[通话结束] 无识别内容"), timeout=1.0)
                            except:
                                connection_state["is_alive"] = False
                    
                    # 重置所有状态
                    cache.clear()
                    last_sent_text = ""
                    current_full_text = ""
                    current_message_id = str(uuid.uuid4())  # 为下一次通话生成新的消息ID
                    chunk_counter = 0
                    last_message_reset = 0
                    log.info(f"通话结束，已重置所有ASR状态，新消息ID: {current_message_id}")
            
            except zmq.error.Again:
                # 超时，没有新消息 - 释放控制权并继续
                await asyncio.sleep(0.01)
                continue
            except zmq.error.ZMQError as e:
                log.error(f"ZMQ错误: {e}")
                await asyncio.sleep(0.1)
                # ZMQ连接问题，可能需要退出
                if "Connection refused" in str(e) or "No such device" in str(e):
                    log.error("ZMQ连接失败，退出处理循环")
                    break
                continue
            except asyncio.CancelledError:
                log.info("ZMQ处理任务被取消")
                break
                
    except asyncio.CancelledError:
        log.info("ZMQ处理任务被取消")
    except Exception as e:
        log.error(f"ZMQ语音数据处理异常: {e}")
    finally:
        try:
            socket.close()
            context.term()
        except Exception as e:
            log.error(f"关闭ZMQ连接时出错: {e}")
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
