#!/usr/bin/env python3

from scapy.all import sniff, conf, get_if_list, get_if_addr
from scapy.layers.inet import IP, UDP
import wave
import time
from typing import List, Dict, Optional, Tuple
import threading
import signal
import sys
import os
import struct
import re
import audioop
import zmq
import json
from dataclasses import dataclass
from collections import defaultdict
import io

@dataclass
class CallInfo:
    call_id: str
    client_ip: str
    start_time: float
    last_packet_time: float
    is_active: bool = True

class RTPHeader:
    def __init__(self, data: bytes):
        if len(data) < 12:
            raise ValueError("RTP header must be at least 12 bytes")
        
        # Parse RTP header
        first_byte = data[0]
        second_byte = data[1]
        
        self.version = (first_byte >> 6) & 0x03
        self.padding = (first_byte >> 5) & 0x01
        self.extension = (first_byte >> 4) & 0x01
        self.csrc_count = first_byte & 0x0F
        self.marker = (second_byte >> 7) & 0x01
        self.payload_type = second_byte & 0x7F
        
        self.sequence_number = struct.unpack('!H', data[2:4])[0]
        self.timestamp = struct.unpack('!I', data[4:8])[0]
        self.ssrc = struct.unpack('!I', data[8:12])[0]

class VoiceSegment:
    def __init__(self, call_id: str, client_ip: str, sequence: int):
        self.call_id = call_id
        self.client_ip = client_ip
        self.sequence = sequence
        self.buffer = bytearray()
        self.samples_received = 0
        self.start_time = time.monotonic()
        self.last_seq = None
        self.packet_buffer = {}
        self.last_processed_seq = None
        self.silence_packets = 0
        self.non_silence_packets = 0
        self.discontinuities = 0
        self.max_seq_gap = 0

    def add_packet(self, payload: bytes, seq: int):
        # Store packet in buffer
        self.packet_buffer[seq] = payload
        
        # Process packets in sequence
        if self.last_processed_seq is None:
            self.last_processed_seq = seq - 1
        
        # Process all sequential packets we have
        next_seq = self.last_processed_seq + 1
        while next_seq in self.packet_buffer:
            payload = self.packet_buffer.pop(next_seq)
            self._process_packet(payload, next_seq)
            self.last_processed_seq = next_seq
            next_seq += 1
            
        # Clean old packets from buffer (if gap is too large)
        for old_seq in list(self.packet_buffer.keys()):
            if old_seq < self.last_processed_seq - 100:  # Remove very old packets
                del self.packet_buffer[old_seq]
                self.discontinuities += 1

    def _process_packet(self, payload: bytes, seq: int):
        """Process a single RTP packet in sequence."""
        # Check for sequence discontinuity
        if self.last_seq is not None:
            gap = (seq - self.last_seq - 1) & 0xFFFF
            if gap > 0:
                self.discontinuities += 1
                self.max_seq_gap = max(self.max_seq_gap, gap)
                # Add silence for missing packets to maintain timing
                silence_payload = bytes([0xFF] * len(payload))
                for _ in range(gap):
                    self.buffer.extend(silence_payload)
        
        # Check if packet is silence
        is_silence = all(b == 0xFF for b in payload)
        if is_silence:
            self.silence_packets += 1
        else:
            self.non_silence_packets += 1
        
        # Add payload to buffer
        self.buffer.extend(payload)
        self.samples_received += len(payload)
        self.last_seq = seq

    def get_duration(self) -> float:
        return self.samples_received / 8000.0  # 8kHz sampling rate for G.711

    def to_wav_bytes(self) -> bytes:
        """Convert the buffer to WAV format and return as bytes"""
        # Convert μ-law to 16-bit linear PCM using audioop
        pcm_data = audioop.ulaw2lin(bytes(self.buffer), 2)
        
        # Create WAV in memory
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, 'wb') as wav_file:
            wav_file.setnchannels(1)  # mono
            wav_file.setsampwidth(2)  # 16-bit
            wav_file.setframerate(8000)  # 8kHz
            wav_file.writeframes(pcm_data)
        
        # Get the complete WAV file as bytes
        wav_data = wav_buffer.getvalue()
        
        # Print some debug info about the audio
        total_packets = self.silence_packets + self.non_silence_packets
        if total_packets > 0:
            silence_percent = (self.silence_packets / total_packets) * 100
            print(f"\nAudio analysis for segment {self.sequence}:")
            print(f"  Total packets: {total_packets}")
            print(f"  Silence packets: {self.silence_packets} ({silence_percent:.1f}%)")
            print(f"  Non-silence packets: {self.non_silence_packets} ({100-silence_percent:.1f}%)")
            print(f"  Discontinuities: {self.discontinuities}")
            print(f"  Max sequence gap: {self.max_seq_gap}")
            print(f"  Buffer size: {len(self.buffer)} bytes")
            print(f"  PCM data size: {len(pcm_data)} bytes")
            
            # Show some non-silence samples if present
            if self.non_silence_packets > 0:
                non_silence_bytes = [b for b in self.buffer[:100] if b != 0xFF][:5]
                if non_silence_bytes:
                    print("  First few non-silence μ-law values:", [hex(b) for b in non_silence_bytes])
                    # Show corresponding PCM values
                    for b in non_silence_bytes:
                        pcm_val = struct.unpack('<h', audioop.ulaw2lin(bytes([b]), 2))[0]
                        print(f"    μ-law {hex(b)} -> PCM {pcm_val}")
        
        return wav_data

class VoiceStreamPublisher:
    def __init__(self, max_memory_mb: int = 2048):  # Default 2GB
        self.context = zmq.Context()
        self.socket = self.context.socket(zmq.PUB)
        self.socket.bind("tcp://*:5555")
        
        # Memory management
        self.max_memory = max_memory_mb * 1024 * 1024  # Convert MB to bytes
        self.current_memory = 0
        self.message_queue = []  # [(timestamp, size, message), ...]
        self.message_lock = threading.Lock()
        
        # Start memory monitor thread
        self.should_stop = False
        self.monitor_thread = threading.Thread(target=self._monitor_memory, daemon=True)
        self.monitor_thread.start()
        
        print(f"ZeroMQ publisher started on port 5555 (Max memory: {max_memory_mb}MB)")

    def _monitor_memory(self):
        """Monitor memory usage and expire old messages if needed"""
        while not self.should_stop:
            with self.message_lock:
                current_time = time.time()
                # Remove messages older than 1 hour regardless of memory usage
                while self.message_queue and (current_time - self.message_queue[0][0]) > 3600:
                    _, size, _ = self.message_queue.pop(0)
                    self.current_memory -= size
                
                # If still over memory limit, remove old messages until under limit
                while self.message_queue and self.current_memory > self.max_memory:
                    _, size, _ = self.message_queue.pop(0)
                    self.current_memory -= size
                    print(f"[MEMORY] Expired old message (Current: {self.current_memory/1024/1024:.1f}MB)")
            
            time.sleep(1)  # Check every second

    def _add_to_queue(self, message: dict) -> int:
        """Add message to queue and return its size"""
        # Convert message to JSON to get actual size
        message_data = json.dumps(message).encode()
        message_size = len(message_data)
        
        with self.message_lock:
            self.message_queue.append((time.time(), message_size, message))
            self.current_memory += message_size
            
            if self.current_memory > self.max_memory:
                print(f"[MEMORY] Warning: Queue size ({self.current_memory/1024/1024:.1f}MB) exceeds limit")
        
        return message_size

    def publish_segment(self, call_id: str, client_ip: str, wav_data: bytes, sequence: int):
        """Publish a voice segment"""
        message = {
            "type": "voice_segment",
            "call_id": call_id,
            "client_ip": client_ip,
            "sequence": sequence,
            "timestamp": time.time(),
            "data": wav_data.hex()  # Convert bytes to hex string for JSON
        }
        
        # Add to queue and get size
        size = self._add_to_queue(message)
        
        # Publish the message
        self.socket.send_json(message)
        
        # Log memory usage periodically
        if sequence % 10 == 0:  # Every 10th segment
            with self.message_lock:
                print(f"\n[MEMORY] Queue status:")
                print(f"  Messages: {len(self.message_queue)}")
                print(f"  Memory usage: {self.current_memory/1024/1024:.1f}MB")
                print(f"  Memory limit: {self.max_memory/1024/1024:.1f}MB")

    def publish_call_end(self, call_id: str, client_ip: str):
        """Publish call end signal"""
        message = {
            "type": "call_end",
            "call_id": call_id,
            "client_ip": client_ip,
            "timestamp": time.time()
        }
        
        # Add to queue
        self._add_to_queue(message)
        
        # Publish the message
        self.socket.send_json(message)

    def close(self):
        """Clean up resources"""
        self.should_stop = True
        if self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=2)
        self.socket.close()
        self.context.term()

class VoiceStreamCapture:
    def __init__(self, duration_threshold: float = 2.0):
        self.publisher = VoiceStreamPublisher()
        self.calls: Dict[str, CallInfo] = {}  # call_id -> CallInfo
        self.segments: Dict[str, VoiceSegment] = {}  # call_id -> current segment
        self.segment_counters: Dict[str, int] = defaultdict(int)  # call_id -> segment count
        self.lock = threading.Lock()
        self.should_stop = False
        self.duration_threshold = duration_threshold
        
        # Setup signal handler
        signal.signal(signal.SIGINT, self.signal_handler)

    def signal_handler(self, signum, frame):
        print("\nStopping capture...")
        self.should_stop = True
        # Send call end signals for all active calls
        for call_id, call_info in self.calls.items():
            if call_info.is_active:
                self.publisher.publish_call_end(call_id, call_info.client_ip)
        self.publisher.close()
        os._exit(0)

    def parse_sip_message(self, data: bytes) -> Optional[dict]:
        try:
            text = data.decode('utf-8', errors='ignore')
            lines = text.split('\r\n')
            
            if not lines:
                return None
                
            result = {
                'type': 'unknown',
                'method': '',
                'call_id': None,
                'headers': {}
            }
            
            # Parse first line
            first_line = lines[0]
            if first_line.startswith('SIP/2.0 '):
                result['type'] = 'response'
                result['status'] = first_line
            elif ' SIP/2.0' in first_line:
                result['type'] = 'request'
                result['method'] = first_line.split(' ')[0]
            
            # Parse headers
            for line in lines[1:]:
                if ': ' in line:
                    key, value = line.split(': ', 1)
                    if key.lower() == 'call-id':
                        result['call_id'] = value.strip()
                    result['headers'][key] = value
            
            return result
        except Exception as e:
            print(f"Error parsing SIP message: {e}")
            return None

    def extract_client_info(self, sip_data: dict, src_ip: str) -> tuple[str, str | None]:
        """Extract client IP and extension from SIP headers"""
        client_ip: str | None = None
        extension: str | None = None
        
        # Try to get client IP from Contact or Via header
        if 'Contact' in sip_data['headers']:
            contact = sip_data['headers']['Contact']
            ip_match = re.search(r'@([\d\.]+):', contact)
            if ip_match:
                client_ip = ip_match.group(1)
        
        if not client_ip and 'Via' in sip_data['headers']:
            via = sip_data['headers']['Via']
            ip_match = re.search(r'([\d\.]+):', via)
            if ip_match:
                client_ip = ip_match.group(1)
        
        # Get extension from From header
        if 'From' in sip_data['headers']:
            from_header = sip_data['headers']['From']
            ext_match = re.search(r'sip:(\d+)@', from_header)
            if ext_match:
                extension = ext_match.group(1)
        
        # Fallback to source IP if we couldn't extract from headers
        if not client_ip:
            client_ip = src_ip
            
        return client_ip, extension

    def process_sip_packet(self, packet, src_ip: str):
        """Process SIP packet to track calls"""
        payload = bytes(packet[UDP].payload)
        sip_data = self.parse_sip_message(payload)
        
        if not sip_data or not sip_data['call_id']:
            return
            
        call_id = sip_data['call_id']
        
        with self.lock:
            # New call
            if sip_data['type'] == 'request' and sip_data['method'] == 'INVITE':
                if call_id not in self.calls:
                    client_ip, extension = self.extract_client_info(sip_data, src_ip)
                    if not client_ip:  # This should never happen due to fallback
                        client_ip = src_ip
                        
                    print(f"New call detected - ID: {call_id}")
                    print(f"  From extension: {extension or 'unknown'}")
                    print(f"  Client IP: {client_ip}")
                    
                    self.calls[call_id] = CallInfo(
                        call_id=call_id,
                        client_ip=client_ip,  # Now guaranteed to be str
                        start_time=time.monotonic(),
                        last_packet_time=time.monotonic()
                    )
            
            # Call end
            elif sip_data['type'] == 'request' and sip_data['method'] == 'BYE':
                if call_id in self.calls:
                    call_info = self.calls[call_id]
                    call_info.is_active = False
                    # Publish any remaining segment
                    if call_id in self.segments:
                        self.publish_current_segment(call_id)
                    # Publish call end signal
                    self.publisher.publish_call_end(call_id, call_info.client_ip)
                    print(f"Call ended - ID: {call_id}")

    def is_rtp_packet(self, data: bytes) -> bool:
        """Validate if packet is RTP with voice data"""
        if len(data) < 12:
            return False
            
        try:
            rtp = RTPHeader(data)
            
            # Basic RTP validation
            if rtp.version != 2:  # RTP version should be 2
                return False
                
            # Check for G.711 μ-law payload type
            if rtp.payload_type != 0:
                return False
                
            # Check payload size (typical for 20ms G.711)
            payload_size = len(data) - 12
            if not (160 <= payload_size <= 240):
                return False
                
            return True
            
        except Exception as e:
            print(f"Error parsing RTP: {e}")
            return False

    def publish_current_segment(self, call_id: str):
        """Convert and publish current segment if duration threshold reached"""
        segment = self.segments.get(call_id)
        if not segment:
            return
            
        duration = segment.get_duration()
        if duration >= self.duration_threshold:  # Use configurable threshold
            wav_data = segment.to_wav_bytes()
            sequence = self.segment_counters[call_id]
            self.publisher.publish_segment(
                call_id=segment.call_id,
                client_ip=segment.client_ip,
                wav_data=wav_data,
                sequence=sequence
            )
            self.segment_counters[call_id] += 1
            # Start new segment
            self.segments[call_id] = VoiceSegment(
                call_id=call_id,
                client_ip=segment.client_ip,
                sequence=self.segment_counters[call_id]
            )

    def packet_callback(self, packet):
        """Process each captured packet"""
        if self.should_stop:
            return True
            
        if UDP not in packet or IP not in packet:
            return
            
        src_ip = packet[IP].src
        dst_ip = packet[IP].dst
        src_port = packet[UDP].sport
        dst_port = packet[UDP].dport
        payload = bytes(packet[UDP].payload)
        
        # Handle SIP packets
        if packet[UDP].dport == 5060 or packet[UDP].sport == 5060:
            self.process_sip_packet(packet, src_ip)
            return
            
        # Handle RTP packets
        if self.is_rtp_packet(payload):
            rtp = RTPHeader(payload)
            
            # Find corresponding call
            call_id = None
            client_ip = None
            for cid, call_info in self.calls.items():
                # We only want packets FROM the client (outgoing voice)
                if src_ip == call_info.client_ip and call_info.is_active:
                    call_id = cid
                    client_ip = call_info.client_ip
                    call_info.last_packet_time = time.monotonic()
                    break
            
            if not call_id or not client_ip:
                return
                
            # Analyze RTP payload
            rtp_payload = payload[12:]  # Skip RTP header
            
            # Skip if payload is too small or all silence
            if len(rtp_payload) < 160 or all(b == 0xFF for b in rtp_payload):
                return
            
            # Check if payload has enough non-silence
            non_silence_count = sum(1 for b in rtp_payload if b != 0xFF)
            if non_silence_count < len(rtp_payload) * 0.1:  # At least 10% non-silence
                return
                
            with self.lock:
                # Create new segment if needed
                if call_id not in self.segments:
                    print(f"\nStarting new voice segment for call {call_id}")
                    self.segments[call_id] = VoiceSegment(
                        call_id=call_id,
                        client_ip=client_ip,
                        sequence=self.segment_counters[call_id]
                    )
                
                # Add packet to segment
                self.segments[call_id].add_packet(
                    payload=rtp_payload,
                    seq=rtp.sequence_number
                )
                
                # Check if segment should be published
                self.publish_current_segment(call_id)

    def check_call_timeouts(self):
        """Check for inactive calls"""
        while not self.should_stop:
            current_time = time.monotonic()
            with self.lock:
                for call_id, call_info in list(self.calls.items()):
                    if call_info.is_active:
                        # Check for 30 seconds of inactivity
                        if current_time - call_info.last_packet_time >= 30:
                            print(f"Call {call_id} timed out")
                            call_info.is_active = False
                            # Publish any remaining segment
                            if call_id in self.segments:
                                self.publish_current_segment(call_id)
                            # Publish call end signal
                            self.publisher.publish_call_end(call_id, call_info.client_ip)
            time.sleep(1)

    def start_capture(self):
        """Start capturing packets"""
        # Start timeout checker thread
        timeout_thread = threading.Thread(target=self.check_call_timeouts, daemon=True)
        timeout_thread.start()
        
        try:
            print("Starting voice stream capture...")
            print("Listening for SIP and RTP packets...")
            
            # Capture all UDP traffic
            sniff(
                filter="udp",
                prn=self.packet_callback,
                store=0,
                stop_filter=lambda pkt: self.should_stop
            )
        except Exception as e:
            print(f"Error during capture: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self.should_stop = True
            self.publisher.close()

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Capture and stream voice segments from RTP packets')
    parser.add_argument('--duration', type=float, default=2.0,
                       help='Duration threshold in seconds for each voice segment (default: 2.0)')
    parser.add_argument('--max-memory', type=int, default=2048,
                       help='Maximum memory usage in MB for message queue (default: 2048)')
    
    args = parser.parse_args()
    
    # Check if running as root
    if os.geteuid() != 0:
        print("This script requires root privileges to capture packets.")
        print("Please run with sudo:")
        print(f"sudo python3 {' '.join(sys.argv)}")
        sys.exit(1)
    
    print(f"Starting capture with {args.duration} second segments...")
    print(f"Maximum memory usage: {args.max_memory}MB")
    
    capture = VoiceStreamCapture(duration_threshold=args.duration)
    capture.start_capture()

if __name__ == "__main__":
    main()
