import zmq
import json

def subscribe_to_stream(port=5555, topics=None):
    """订阅实时流
    
    Args:
        port: ZMQ端口
        topics: 要订阅的主题列表，例如 ["session.*", "transcription.*"]
               如果为None，订阅所有消息
    """
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(f"tcp://localhost:{port}")
    
    # 设置订阅主题
    if topics:
        for topic in topics:
            socket.setsockopt_string(zmq.SUBSCRIBE, topic)
    else:
        socket.setsockopt_string(zmq.SUBSCRIBE, "")
    
    print("开始接收消息...")
    while True:
        try:
            # 接收消息
            message = socket.recv_string()
            topic, data = message.split(" ", 1)
            data = json.loads(data)
            
            # 处理不同类型的消息
            if data['type'] == 'session_info':
                print(f"\n新会话信息 - Call-ID: {data['data']['call_id']}")
                print(f"From: {data['data']['from_uri']}")
                print(f"Source IP: {data['data']['source_ip']}")
            
            elif data['type'] == 'transcription':
                print(f"\n识别结果 - Call-ID: {data['data']['call_id']}")
                print(f"文字: {data['data']['text']}")
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Error: {e}")
    
    socket.close()
    context.term()

# 使用示例
if __name__ == "__main__":
    # 只订阅识别结果
    subscribe_to_stream(topics=["transcription.*"])