#!/usr/bin/env python3
"""
RTP to WebSocket ASR Bridge
将 RTP 音频流转换为 WebSocket ASR 服务可接受的格式
"""

import asyncio
import websockets
import socket
import struct
import threading
import logging
import numpy as np
from collections import deque
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RTPPacket:
    HEADER_SIZE = 12

    @staticmethod
    def unpack(packet_data):
        """解包 RTP 数据包"""
        if len(packet_data) < RTPPacket.HEADER_SIZE:
            return None, None
            
        header = packet_data[:RTPPacket.HEADER_SIZE]
        payload = packet_data[RTPPacket.HEADER_SIZE:]
        
        first_byte, payload_type, seq, timestamp, ssrc = struct.unpack('!BBHII', header)
        
        version = (first_byte >> 6) & 0x3
        padding = (first_byte >> 5) & 0x1
        extension = (first_byte >> 4) & 0x1
        csrc_count = first_byte & 0xF
        marker = (payload_type >> 7) & 0x1
        payload_type = payload_type & 0x7F
        
        # 创建包信息字典
        packet_info = {
            'version': version,
            'padding': padding,
            'extension': extension,
            'csrc_count': csrc_count,
            'marker': marker,
            'payload_type': payload_type,
            'sequence_number': seq,
            'timestamp': timestamp,
            'ssrc': ssrc
        }
        
        return packet_info, payload

class RTPToWebSocketBridge:
    def __init__(self, 
                 rtp_listen_ip="0.0.0.0", 
                 rtp_listen_port=5062,
                 websocket_url="ws://localhost:8001/ws",
                 sample_rate=16000):
        
        self.rtp_listen_ip = rtp_listen_ip
        self.rtp_listen_port = rtp_listen_port
        self.websocket_url = websocket_url
        self.sample_rate = sample_rate
        self.running = False
        
        # 音频缓冲区
        self.audio_buffer = deque()
        self.buffer_lock = threading.Lock()
        
        # RTP 接收统计
        self.packets_received = 0
        self.last_sequence = None
        self.packets_lost = 0
        
        # WebSocket ASR 帧配置（基于 ws.py）
        self.chunk_duration_ms = 600  # 600ms 每帧
        self.samples_per_frame = int(self.sample_rate * self.chunk_duration_ms / 1000)  # 9600
        self.bytes_per_frame = self.samples_per_frame * 2  # 19200 bytes
        
        logger.info(f"Bridge initialized:")
        logger.info(f"  RTP: {rtp_listen_ip}:{rtp_listen_port}")
        logger.info(f"  WebSocket: {websocket_url}")
        logger.info(f"  Frame size: {self.bytes_per_frame} bytes ({self.chunk_duration_ms}ms)")

    def start_rtp_receiver(self):
        """启动 RTP 接收线程"""
        def rtp_receiver():
            # 创建 UDP socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind((self.rtp_listen_ip, self.rtp_listen_port))
            sock.settimeout(1.0)
            
            logger.info(f"RTP receiver listening on {self.rtp_listen_ip}:{self.rtp_listen_port}")
            
            while self.running:
                try:
                    packet_data, addr = sock.recvfrom(65535)
                    self.process_rtp_packet(packet_data)
                    
                except socket.timeout:
                    continue
                except Exception as e:
                    logger.error(f"RTP receiver error: {e}")
            
            sock.close()
            logger.info("RTP receiver stopped")
        
        self.rtp_thread = threading.Thread(target=rtp_receiver)
        self.rtp_thread.start()

    def process_rtp_packet(self, packet_data):
        """处理 RTP 数据包"""
        try:
            # 解包 RTP
            packet_info, audio_payload = RTPPacket.unpack(packet_data)
            
            if packet_info is None or audio_payload is None:
                return
            
            # 统计信息
            self.packets_received += 1
            if self.last_sequence is not None:
                expected_seq = (self.last_sequence + 1) % 65536
                if packet_info['sequence_number'] != expected_seq:
                    lost = (packet_info['sequence_number'] - expected_seq) % 65536
                    self.packets_lost += lost
                    logger.warning(f"Packet loss detected: expected {expected_seq}, got {packet_info['sequence_number']}")
            
            self.last_sequence = packet_info['sequence_number']
            
            # 将音频数据添加到缓冲区
            with self.buffer_lock:
                self.audio_buffer.extend(audio_payload)
            
            # 日志输出（每100个包输出一次统计）
            if self.packets_received % 100 == 0:
                logger.info(f"RTP Stats: received={self.packets_received}, lost={self.packets_lost}, "
                           f"buffer_size={len(self.audio_buffer)} bytes")
                
        except Exception as e:
            logger.error(f"Error processing RTP packet: {e}")

    async def websocket_sender(self):
        """WebSocket 发送协程"""
        while self.running:
            try:
                async with websockets.connect(self.websocket_url) as websocket:
                    logger.info(f"Connected to WebSocket ASR: {self.websocket_url}")
                    
                    while self.running:
                        # 检查是否有足够的数据组成一帧
                        with self.buffer_lock:
                            if len(self.audio_buffer) >= self.bytes_per_frame:
                                # 提取一帧数据
                                frame_data = bytes(self.audio_buffer)[:self.bytes_per_frame]
                                # 从缓冲区移除已使用的数据
                                for _ in range(self.bytes_per_frame):
                                    self.audio_buffer.popleft()
                            else:
                                frame_data = None
                        
                        if frame_data:
                            # 发送到 WebSocket ASR
                            await websocket.send(frame_data)
                            logger.debug(f"Sent {len(frame_data)} bytes to ASR")
                            
                            # 尝试接收 ASR 结果
                            try:
                                result = await asyncio.wait_for(websocket.recv(), timeout=0.1)
                                logger.info(f"ASR Result: {result}")
                            except asyncio.TimeoutError:
                                pass  # 没有结果，继续
                        else:
                            # 缓冲区数据不足，等待
                            await asyncio.sleep(0.01)
                            
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if self.running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)

    async def start_async(self):
        """启动异步服务"""
        self.running = True
        
        # 启动 RTP 接收线程
        self.start_rtp_receiver()
        
        # 启动 WebSocket 发送协程
        await self.websocket_sender()

    def stop(self):
        """停止服务"""
        logger.info("Stopping RTP to WebSocket bridge...")
        self.running = False
        
        if hasattr(self, 'rtp_thread'):
            self.rtp_thread.join()
        
        logger.info("Bridge stopped")

    def get_stats(self):
        """获取统计信息"""
        return {
            'packets_received': self.packets_received,
            'packets_lost': self.packets_lost,
            'buffer_size': len(self.audio_buffer),
            'loss_rate': self.packets_lost / max(self.packets_received, 1) * 100
        }

# 使用示例
async def main():
    # 创建桥接器
    bridge = RTPToWebSocketBridge(
        rtp_listen_ip="0.0.0.0",
        rtp_listen_port=5062,
        websocket_url="ws://localhost:8001/ws",  # 指向 ws.py 的服务
        sample_rate=16000
    )
    
    try:
        # 启动桥接服务
        await bridge.start_async()
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    finally:
        bridge.stop()

if __name__ == "__main__":
    asyncio.run(main())
