import time
import threading
import wave
from scapy.all import sniff, UDP

CLIENT_IP = "100.120.0.197"
SERVER_IP = "100.120.241.10"
RTP_PORT_RANGE = "udp portrange 10000-20000"

last_packet_time = time.monotonic()
rtp_buffer = bytearray()
lock = threading.Lock()

# 保存为 WAV 文件
def save_wav(data, filename="listen.wav"):
    with wave.open(filename, 'wb') as wf:
        wf.setnchannels(1)            # Mono
        wf.setsampwidth(2)            # 16-bit samples (2 bytes)
        wf.setframerate(8000)         # 8kHz
        wf.writeframes(data)
    print(f"[INFO] Saved {len(data)} bytes to {filename}")

# 每秒检查是否超时
def monitor_timeout():
    global last_packet_time, rtp_buffer
    while True:
        time.sleep(1)
        now = time.monotonic()
        with lock:
            if rtp_buffer and (now - last_packet_time > 3):
                print("[WARN] Timeout detected! Saving audio...")
                save_wav(rtp_buffer)
                rtp_buffer = bytearray()  # 清空缓存

# RTP数据抓取回调
def handle_rtp(packet):
    global last_packet_time
    if UDP in packet and len(packet[UDP].payload) >= 12:
        ip_src = packet[0][1].src
        ip_dst = packet[0][1].dst
        if ip_src == CLIENT_IP and ip_dst == SERVER_IP:
            payload = bytes(packet[UDP].payload)[12:]  # RTP header is 12 bytes
            with lock:
                rtp_buffer.extend(payload)
                last_packet_time = time.monotonic()
            print(f"[RTP] Received packet: {len(payload)} bytes")

def main():
    print("[INFO] Starting RTP auto-recorder...")
    threading.Thread(target=monitor_timeout, daemon=True).start()

    sniff(
        filter=f"{RTP_PORT_RANGE} and src host {CLIENT_IP} and dst host {SERVER_IP}",
        prn=handle_rtp,
        store=0
    )

if __name__ == "__main__":
    main()
