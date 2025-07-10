import psutil
import time
import threading
import queue
from scapy.all import sniff, UDP
import pyaudio
import os

audio_queue = queue.Queue()

# 音频播放线程
def audio_player():
    p = pyaudio.PyAudio()
    stream = p.open(format=pyaudio.paInt16, channels=1, rate=8000, output=True)
    while True:
        payload = audio_queue.get()
        if payload is None:
            break
        pcm_data = bytearray()
        for b in payload:
            val = mulaw2linear(b)
            pcm_data += int(val).to_bytes(2, byteorder='little', signed=True)
        stream.write(bytes(pcm_data))
    stream.stop_stream()
    stream.close()
    p.terminate()

# μ-law 解码
def mulaw2linear(u_val):
    u_val = ~u_val & 0xFF
    t = ((u_val & 0x0F) << 3) + 33
    t <<= (u_val & 0x70) >> 4
    return -t if (u_val & 0x80) else t

# 抓包回调
def packet_callback(pkt):
    if UDP in pkt and pkt[UDP].sport >= 16384:
        data = bytes(pkt[UDP].payload)
        if len(data) > 12:
            payload = data[12:]
            audio_queue.put(payload)

# CPU/内存监控线程
def monitor():
    process = psutil.Process(os.getpid())
    while True:
        cpu = psutil.cpu_percent(interval=1)
        mem = process.memory_info().rss / 1024 / 1024  # 转为 MB
        print(f"[Monitor] CPU: {cpu:.1f}%, Memory: {mem:.1f} MB")
        time.sleep(2)

# 启动线程
threading.Thread(target=audio_player, daemon=True).start()
threading.Thread(target=monitor, daemon=True).start()

# 启动抓包
print("开始抓取 RTP 包...")
sniff(iface="enp2s0", filter="udp portrange 16384-32767", prn=packet_callback)

