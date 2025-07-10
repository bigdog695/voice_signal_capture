import wave
import time
import threading
import numpy as np
import socket
import struct
import logging
import sounddevice as sd
from flask import Flask, Response, stream_with_context
from queue import Queue
import json
from scapy.all import sniff, UDP, IP, Raw
import threading

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app for streaming API
app = Flask(__name__)

# Global queue for packet data
packet_queue = Queue(maxsize=1000)  # Limit queue size to prevent memory issues

class RTPPacket:
    HEADER_SIZE = 12

    def __init__(self, payload_type=0, sequence_number=0, timestamp=0, ssrc=0):
        self.version = 2
        self.padding = 0
        self.extension = 0
        self.csrc_count = 0
        self.marker = 0
        self.payload_type = payload_type
        self.sequence_number = sequence_number
        self.timestamp = timestamp
        self.ssrc = ssrc

    def pack(self, payload):
        """Pack RTP packet into bytes"""
        header = struct.pack(
            '!BBHII',
            (self.version << 6) | (self.padding << 5) | (self.extension << 4) | self.csrc_count,
            (self.marker << 7) | self.payload_type,
            self.sequence_number,
            self.timestamp,
            self.ssrc
        )
        return header + payload

    @staticmethod
    def unpack(packet_data):
        """Unpack RTP packet from bytes"""
        header = packet_data[:RTPPacket.HEADER_SIZE]
        payload = packet_data[RTPPacket.HEADER_SIZE:]
        
        first_byte, payload_type, seq, timestamp, ssrc = struct.unpack('!BBHII', header)
        
        version = (first_byte >> 6) & 0x3
        padding = (first_byte >> 5) & 0x1
        extension = (first_byte >> 4) & 0x1
        csrc_count = first_byte & 0xF
        marker = (payload_type >> 7) & 0x1
        payload_type = payload_type & 0x7F
        
        packet = RTPPacket(payload_type, seq, timestamp, ssrc)
        packet.version = version
        packet.padding = padding
        packet.extension = extension
        packet.csrc_count = csrc_count
        packet.marker = marker
        
        return packet, payload

class VoiceSender(threading.Thread):
    def __init__(self, wav_file, target_ip="127.0.0.1", target_port=5062):
        super().__init__()
        self.wav_file = wav_file
        self.target_ip = target_ip
        self.target_port = target_port
        self.running = True
        self.sequence_number = 0
        self.timestamp = 0
        
        # Create UDP socket
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        logger.info(f"VoiceSender initialized - Target: {target_ip}:{target_port}")
        
    def stream_audio(self):
        with wave.open(self.wav_file, 'rb') as wav:
            # Get WAV file properties
            channels = wav.getnchannels()
            sample_width = wav.getsampwidth()
            framerate = wav.getframerate()
            
            # Calculate chunk size (20ms of audio)
            chunk_size = framerate // 50
            samples_per_chunk = chunk_size * channels
            
            logger.info(f"Audio properties - Channels: {channels}, Sample width: {sample_width}, Framerate: {framerate}")
            
            while self.running:
                # Read chunk of audio data
                audio_data = wav.readframes(chunk_size)
                
                if not audio_data:
                    # If reached end of file, seek to beginning
                    wav.rewind()
                    logger.debug("Reached end of file, rewinding")
                    continue
                
                # Create and send RTP packet
                packet = RTPPacket(
                    payload_type=0,  # PCM audio
                    sequence_number=self.sequence_number,
                    timestamp=self.timestamp,
                    ssrc=0x12345678
                )
                
                rtp_packet = packet.pack(audio_data)
                self.socket.sendto(rtp_packet, (self.target_ip, self.target_port))
                
                # Update sequence number and timestamp
                self.sequence_number = (self.sequence_number + 1) & 0xFFFF
                self.timestamp += samples_per_chunk
                
                # Sleep for chunk duration
                time.sleep(chunk_size / framerate)
    
    def run(self):
        try:
            logger.info("Starting audio streaming")
            self.stream_audio()
        except Exception as e:
            logger.error(f"Error in VoiceSender: {e}")
        finally:
            self.socket.close()
    
    def stop(self):
        logger.info("Stopping VoiceSender")
        self.running = False

class PacketCapturer(threading.Thread):
    def __init__(self, target_ports=[5062]):
        super().__init__()
        self.target_ports = target_ports
        self.running = True
        logger.info(f"PacketCapturer initialized - Capturing ports: {target_ports}")

    def process_packet(self, packet):
        """Process captured packet and add to queue if it's RTP"""
        try:
            if UDP in packet and packet[UDP].dport in self.target_ports:
                # Extract RTP payload
                payload = bytes(packet[Raw].load) if Raw in packet else None
                if payload and len(payload) > RTPPacket.HEADER_SIZE:
                    try:
                        # Try to parse as RTP
                        rtp_packet, audio_data = RTPPacket.unpack(payload)
                        
                        # Create packet info dictionary
                        packet_info = {
                            'timestamp': time.time(),
                            'sequence_number': rtp_packet.sequence_number,
                            'rtp_timestamp': rtp_packet.timestamp,
                            'payload_type': rtp_packet.payload_type,
                            'audio_data': audio_data.hex()  # Convert to hex for JSON serialization
                        }
                        
                        # Add to queue, non-blocking
                        if not packet_queue.full():
                            packet_queue.put_nowait(packet_info)
                        
                    except Exception as e:
                        logger.debug(f"Not a valid RTP packet: {e}")
                        
        except Exception as e:
            logger.error(f"Error processing packet: {e}")

    def run(self):
        logger.info("Starting packet capture")
        # Set up packet capture filter
        filter_str = f"udp and (port {' or port '.join(map(str, self.target_ports))})"
        try:
            # Start capturing packets
            sniff(
                filter=filter_str,
                prn=self.process_packet,
                store=0,
                stop_filter=lambda _: not self.running
            )
        except Exception as e:
            logger.error(f"Error in packet capture: {e}")

    def stop(self):
        logger.info("Stopping PacketCapturer")
        self.running = False

# Flask routes
@app.route('/stream')
def stream():
    """Stream captured packets as Server-Sent Events"""
    def generate():
        while True:
            try:
                # Get packet from queue, timeout after 1 second
                packet_info = packet_queue.get(timeout=1)
                yield f"data: {json.dumps(packet_info)}\n\n"
            except Exception:
                # Send keepalive
                yield ": keepalive\n\n"
    
    return Response(
        stream_with_context(generate()),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Access-Control-Allow-Origin': '*'
        }
    )

def main():
    # Create and start sender thread
    wav_file = "/data/barryhuang/voice_model/test.wav"
    sender = VoiceSender(wav_file)
    sender.start()
    
    # Create and start packet capturer
    capturer = PacketCapturer()
    capturer.start()
    
    # Start Flask server in a separate thread
    flask_thread = threading.Thread(target=lambda: app.run(host='0.0.0.0', port=5000))
    flask_thread.daemon = True
    flask_thread.start()
    
    try:
        # Keep main thread running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # Stop threads on keyboard interrupt
        logger.info("Received keyboard interrupt, stopping threads")
        sender.stop()
        capturer.stop()
        sender.join()
        capturer.join()
        logger.info("All threads stopped")

if __name__ == "__main__":
    main()
