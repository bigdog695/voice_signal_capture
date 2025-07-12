from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import asyncio
from typing import Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime
import uuid
import numpy as np
import logging

# ASR相关配置
MODEL_NAME: str = "paraformer-zh-streaming"
MODEL_REV: str = "v2.0.4"
DEVICE: str = "cpu"

# 音频参数配置
CHUNK_SIZE = [0, 10, 5]  # 600ms frame
ENC_LB = 4  # encoder look-back (chunks)
DEC_LB = 1  # decoder look-back (chunks)
SAMPLES_PER_FRAME = CHUNK_SIZE[1] * 960  # 9600
BYTES_PER_FRAME = SAMPLES_PER_FRAME * 2   # 19200 (16-bit PCM)

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
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

# ASR模型初始化 - FunASR是必选项
asr_model = None
try:
    log.info(f"加载FunASR模型 '{MODEL_NAME}' (streaming)...")
    from funasr import AutoModel
    asr_model = AutoModel(
        model=MODEL_NAME,
        model_revision=MODEL_REV,
        mode="online",
        device=DEVICE,
        hub="hf",  # 使用Hugging Face hub
    )
    log.info("ASR模型加载成功")
except ImportError as e:
    log.error("FunASR未安装！这是必选依赖，请安装FunASR")
    log.error("安装命令: pip install funasr modelscope torch torchaudio")
    raise RuntimeError("FunASR是必选依赖，请先安装") from e
except Exception as exc:
    log.error(f"ASR模型加载失败: {exc}")
    log.error("请检查网络连接和模型下载")
    raise RuntimeError(f"ASR模型加载失败: {exc}") from exc

# 模拟数据库
chat_sessions: Dict[str, ChatSession] = {}
active_connections: Dict[str, WebSocket] = {}
user_chat_history: Dict[str, List[str]] = {}  # user_id -> [chat_id, ...]

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
        "samples_per_frame": SAMPLES_PER_FRAME,
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
    log.info("ASR WebSocket连接已建立")
    
    # 初始化ASR状态
    cache: dict = {}
    buf = bytearray()
    
    try:
        while True:
            # 接收音频字节数据
            chunk = await websocket.receive_bytes()
            buf.extend(chunk)
            
            # 处理完整音频帧
            while len(buf) >= BYTES_PER_FRAME:
                frame = bytes(buf[:BYTES_PER_FRAME])
                del buf[:BYTES_PER_FRAME]
                
                # 转换为浮点音频数据
                audio = (np.frombuffer(frame, dtype=np.int16)
                           .astype(np.float32) / 32768.0)
                
                # 使用FunASR进行识别
                result = asr_model.generate(
                    input=audio,
                    cache=cache,
                    is_final=False,
                    chunk_size=CHUNK_SIZE,
                    encoder_chunk_look_back=ENC_LB,
                    decoder_chunk_look_back=DEC_LB,
                )
                
                # 提取识别文本
                text = _extract_asr_text(result)
                if text:
                    await websocket.send_text(text)
                    log.info(f"ASR识别: {text}")
                    
    except WebSocketDisconnect:
        log.info("ASR客户端断开连接 - 处理最终音频")
        # 处理剩余的音频缓冲区
        if buf:
            audio = (np.frombuffer(buf, dtype=np.int16)
                       .astype(np.float32) / 32768.0)
            result = asr_model.generate(
                input=audio,
                cache=cache,
                is_final=True,
                chunk_size=CHUNK_SIZE,
                encoder_chunk_look_back=ENC_LB,
                decoder_chunk_look_back=DEC_LB,
            )
            text = _extract_asr_text(result)
            if text:
                await websocket.send_text(text)
                log.info(f"ASR最终识别: {text}")
    except Exception as e:
        log.error(f"ASR WebSocket错误: {e}")
        await websocket.close(code=1011, reason="ASR processing error")
    finally:
        log.info("ASR WebSocket连接已关闭")

def _extract_asr_text(result):
    """从FunASR结果中提取文本 - 模仿asr folder的实现"""
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

# 初始化示例数据函数
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

if __name__ == "__main__":
    # 启动时初始化示例数据
    init_sample_data()
    
    log.info("========================================")
    log.info("Voice Chat Backend with ASR - v2.0.0")
    log.info("========================================")
    log.info("ASR模型状态: 已加载并可用")
    log.info(f"ASR模型: {MODEL_NAME} (rev: {MODEL_REV})")
    log.info(f"设备: {DEVICE}")
    log.info("服务端点:")
    log.info("  - API文档: http://localhost:8000/docs")
    log.info("  - 健康检查: http://localhost:8000/health")
    log.info("  - ASR信息: http://localhost:8000/asr/info")
    log.info("  - 聊天API示例: http://localhost:8000/chat/list?id=user_001")
    log.info("WebSocket端点:")
    log.info("  - 聊天: ws://localhost:8000/chatting?id=chat_active_001")
    log.info("  - ASR: ws://localhost:8000/ws")
    log.info("========================================")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
