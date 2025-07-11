from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import json
import asyncio
from typing import Dict, List, Optional
from pydantic import BaseModel
from datetime import datetime
import uuid

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
app = FastAPI(title="Voice Chat Backend", version="1.0.0")

# CORS设置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 模拟数据库
chat_sessions: Dict[str, ChatSession] = {}
active_connections: Dict[str, WebSocket] = {}
user_chat_history: Dict[str, List[str]] = {}  # user_id -> [chat_id, ...]

# 初始化一些示例数据
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

# 启动时初始化数据
init_sample_data()

@app.get("/")
async def root():
    return {"message": "Voice Chat Backend API", "version": "1.0.0"}

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
        {"speaker": "user", "content": "你好，我想咨询一些问题。"},
        {"speaker": "assistant", "content": "您好！我很乐意为您提供帮助。请告诉我您想了解什么？"},
        {"speaker": "user", "content": "我想了解关于人工智能的发展趋势。"},
        {"speaker": "assistant", "content": "人工智能确实是一个非常热门的领域。目前主要的发展趋势包括大语言模型、多模态AI、自动驾驶等方向。"}
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
    模拟实时语音识别对话，快速密集推送消息
    """
    try:
        # 模拟实时语音识别 - 超快速推送
        conversation_segments = [
            # 第一阶段：问候和介绍 - 用户第一句话
            {"speaker": "user", "content": "你", "delay": 0.3, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好", "delay": 0.2, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，", "delay": 0.15, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我", "delay": 0.2, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我想", "delay": 0.3, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我想了", "delay": 0.2, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我想了解", "delay": 0.25, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我想了解一下", "delay": 0.3, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我想了解一下人工", "delay": 0.2, "message_group": "user_msg_1"},
            {"speaker": "user", "content": "你好，我想了解一下人工智能", "delay": 0.4, "message_group": "user_msg_1"},
            
            # AI回复
            {"speaker": "assistant", "content": "您", "delay": 0.6, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好", "delay": 0.2, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！", "delay": 0.15, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我", "delay": 0.2, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我很", "delay": 0.2, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我很乐意", "delay": 0.25, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我很乐意为", "delay": 0.2, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我很乐意为您", "delay": 0.2, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我很乐意为您介绍", "delay": 0.3, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我很乐意为您介绍人工", "delay": 0.2, "message_group": "assistant_msg_1"},
            {"speaker": "assistant", "content": "您好！我很乐意为您介绍人工智能", "delay": 0.4, "message_group": "assistant_msg_1"},
            
            # 第二阶段：深入讨论 - 用户第二句话
            {"speaker": "user", "content": "什", "delay": 0.8, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "什么", "delay": 0.2, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "什么是", "delay": 0.2, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "什么是大", "delay": 0.2, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "什么是大语", "delay": 0.2, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "什么是大语言", "delay": 0.25, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "什么是大语言模", "delay": 0.2, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "什么是大语言模型", "delay": 0.3, "message_group": "user_msg_2"},
            {"speaker": "user", "content": "什么是大语言模型？", "delay": 0.4, "message_group": "user_msg_2"},
            
            # AI第二次回复
            {"speaker": "assistant", "content": "大", "delay": 0.5, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "大语", "delay": 0.15, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "大语言", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "大语言模", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "大语言模型", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "大语言模型是", "delay": 0.25, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "大语言模型是一种", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "大语言模型是一种基于", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "大语言模型是一种基于深度", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "大语言模型是一种基于深度学习", "delay": 0.25, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "大语言模型是一种基于深度学习的", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "大语言模型是一种基于深度学习的AI", "delay": 0.2, "message_group": "assistant_msg_2"},
            {"speaker": "assistant", "content": "大语言模型是一种基于深度学习的AI系统", "delay": 0.4, "message_group": "assistant_msg_2"},
            
            # 第三阶段：技术细节 - 用户第三句话
            {"speaker": "user", "content": "它", "delay": 0.7, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "它们", "delay": 0.2, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "它们是", "delay": 0.2, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "它们是怎", "delay": 0.2, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "它们是怎么", "delay": 0.2, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "它们是怎么训", "delay": 0.25, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "它们是怎么训练", "delay": 0.2, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "它们是怎么训练的", "delay": 0.3, "message_group": "user_msg_3"},
            {"speaker": "user", "content": "它们是怎么训练的？", "delay": 0.4, "message_group": "user_msg_3"},
            
            # AI第三次回复
            {"speaker": "assistant", "content": "训", "delay": 0.6, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过", "delay": 0.15, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要包", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要包括", "delay": 0.25, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要包括数", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要包括数据", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要包括数据预", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要包括数据预处理", "delay": 0.25, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要包括数据预处理、模", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要包括数据预处理、模型", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要包括数据预处理、模型架", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要包括数据预处理、模型架构", "delay": 0.25, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要包括数据预处理、模型架构设计", "delay": 0.3, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要包括数据预处理、模型架构设计和", "delay": 0.2, "message_group": "assistant_msg_3"},
            {"speaker": "assistant", "content": "训练过程主要包括数据预处理、模型架构设计和优化", "delay": 0.4, "message_group": "assistant_msg_3"},
            
            # 第四阶段：应用场景 - 用户第四句话
            {"speaker": "user", "content": "有", "delay": 0.8, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "有什", "delay": 0.2, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "有什么", "delay": 0.2, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "有什么实", "delay": 0.2, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "有什么实际", "delay": 0.25, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "有什么实际应", "delay": 0.2, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "有什么实际应用", "delay": 0.3, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "有什么实际应用场", "delay": 0.2, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "有什么实际应用场景", "delay": 0.3, "message_group": "user_msg_4"},
            {"speaker": "user", "content": "有什么实际应用场景？", "delay": 0.4, "message_group": "user_msg_4"},
            
            # AI第四次回复
            {"speaker": "assistant", "content": "应", "delay": 0.5, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用", "delay": 0.15, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广", "delay": 0.25, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括", "delay": 0.25, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊天", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊天机", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊天机器", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊天机器人", "delay": 0.25, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊天机器人、文", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊天机器人、文本", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊天机器人、文本生", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊天机器人、文本生成", "delay": 0.25, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊天机器人、文本生成、代", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊天机器人、文本生成、代码", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊天机器人、文本生成、代码编", "delay": 0.2, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊天机器人、文本生成、代码编写", "delay": 0.3, "message_group": "assistant_msg_4"},
            {"speaker": "assistant", "content": "应用场景非常广泛，包括聊天机器人、文本生成、代码编写等", "delay": 0.4, "message_group": "assistant_msg_4"},
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
            
            print(f"实时推送: {segment['speaker']} - {segment['content']}")
        
        # 继续循环推送更多实时内容
        await asyncio.sleep(1)
        
        # 第二轮：技术深度讨论
        technical_segments = [
            {"speaker": "user", "content": "机", "delay": 0.8, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器学", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器学习", "delay": 0.25, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器学习和", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器学习和深", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器学习和深度", "delay": 0.25, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器学习和深度学", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器学习和深度学习", "delay": 0.3, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器学习和深度学习有", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器学习和深度学习有什", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器学习和深度学习有什么", "delay": 0.25, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器学习和深度学习有什么区", "delay": 0.2, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器学习和深度学习有什么区别", "delay": 0.3, "message_group": "user_msg_5"},
            {"speaker": "user", "content": "机器学习和深度学习有什么区别？", "delay": 0.4, "message_group": "user_msg_5"},
            
            {"speaker": "assistant", "content": "深", "delay": 0.6, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度", "delay": 0.15, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习", "delay": 0.25, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一个", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一个子", "delay": 0.25, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一个子集", "delay": 0.3, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一个子集，主", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一个子集，主要", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一个子集，主要使", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一个子集，主要使用", "delay": 0.25, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一个子集，主要使用多", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一个子集，主要使用多层", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一个子集，主要使用多层神", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一个子集，主要使用多层神经", "delay": 0.25, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一个子集，主要使用多层神经网", "delay": 0.2, "message_group": "assistant_msg_5"},
            {"speaker": "assistant", "content": "深度学习是机器学习的一个子集，主要使用多层神经网络", "delay": 0.4, "message_group": "assistant_msg_5"},
        ]
        
        # 快速推送技术讨论
        for segment in technical_segments:
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
            
            print(f"技术讨论: {segment['speaker']} - {segment['content']}")
        
        # 发送对话结束标记
        await asyncio.sleep(1)
        await websocket.send_text(json.dumps({
            "type": "conversation_complete",
            "chat_id": chat_id,
            "message": "实时语音识别演示完成",
            "timestamp": datetime.now().isoformat()
        }))
        
    except Exception as e:
        print(f"模拟对话错误: {e}")

@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {
        "status": "healthy",
        "active_connections": len(active_connections),
        "total_chats": len(chat_sessions),
        "timestamp": datetime.now().isoformat()
    }

if __name__ == "__main__":
    print("启动Voice Chat Backend服务器...")
    print("API文档地址: http://localhost:8000/docs")
    print("健康检查: http://localhost:8000/health")
    print("示例API: http://localhost:8000/chat/list?id=user_001")
    print("WebSocket: ws://localhost:8000/chatting?id=chat_active_001")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
