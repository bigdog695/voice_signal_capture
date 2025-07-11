#!/usr/bin/env python3

from scapy.all import sniff, conf, get_if_list, get_if_addr
from scapy.layers.inet import IP, UDP
import wave
import time
from typing import List
import threading
import signal
import sys
import os
import struct
import re

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

def ulaw2linear(u):
    """
    Convert a μ-law byte to 16-bit PCM sample.
    Following ITU-T G.711 specification with proper scaling.
    """
    # Remove the sign bit and invert (u-law is stored inverted)
    u = ~u & 0xFF
    
    # Extract sign, exponent, and mantissa
    sign = (u & 0x80)
    exponent = (u >> 4) & 0x07
    mantissa = u & 0x0F
    
    # Convert to 16-bit linear
    # Start with mantissa as magnitude
    magnitude = mantissa + 16.0
    # Apply exponent scaling
    magnitude = magnitude * (2.0 ** exponent)
    # Scale to 16-bit range (approximately -32768 to 32767)
    magnitude = magnitude * 8.0
    # Convert to integer
    sample = int(magnitude)
    # Apply sign
    if sign:
        sample = -sample
    # Ensure we stay within 16-bit signed range
    sample = max(-32768, min(32767, sample))
    return sample

def ulaw_to_pcm(ulaw_data: bytes) -> bytes:
    """
    Convert μ-law encoded audio data to 16-bit PCM.
    G.711 μ-law uses inverted bits and bias, following ITU-T G.711 specification.
    """
    pcm_data = bytearray()
    silence_count = 0
    non_silence_count = 0
    max_sample = float('-inf')
    min_sample = float('inf')
    
    for byte in ulaw_data:
        if byte == 0xFF:  # Silence in μ-law
            silence_count += 1
        else:
            non_silence_count += 1
            if non_silence_count <= 5:  # Print first few non-silence samples
                print(f"Non-silence byte: {hex(byte)} ({byte})")
        
        sample = ulaw2linear(byte)
        max_sample = max(max_sample, sample)
        min_sample = min(min_sample, sample)
        pcm_data.extend(sample.to_bytes(2, byteorder='little', signed=True))
    
    total_samples = silence_count + non_silence_count
    if total_samples > 0:
        silence_percentage = (silence_count / total_samples) * 100
        print(f"\nAudio analysis:")
        print(f"  Total samples: {total_samples}")
        print(f"  Silence samples: {silence_count} ({silence_percentage:.1f}%)")
        print(f"  Non-silence samples: {non_silence_count} ({100-silence_percentage:.1f}%)")
        print(f"  Sample value range: {min_sample} to {max_sample}")
        if non_silence_count > 0:
            print("  First few non-silence samples converted to PCM values:")
            test_bytes = [b for b in ulaw_data if b != 0xFF][:5]
            print("  ", [f"{b}({hex(b)}) -> {ulaw2linear(b)}" for b in test_bytes])
    
    return bytes(pcm_data)

def parse_sip_message(data: bytes) -> dict | None:
    """Parse SIP message and return key information"""
    try:
        text = data.decode('utf-8', errors='ignore')
        lines = text.split('\r\n')
        
        # Parse first line
        if not lines:
            return None
            
        result = {
            'type': 'unknown',
            'method': '',
            'headers': {},
            'sdp': {}
        }
        
        # Parse request/response line
        first_line = lines[0]
        if first_line.startswith('SIP/2.0 '):
            result['type'] = 'response'
            result['status'] = first_line
            # Extract response code
            try:
                result['code'] = int(first_line.split()[1])
            except:
                result['code'] = 0
        elif ' SIP/2.0' in first_line:
            result['type'] = 'request'
            result['method'] = first_line.split(' ')[0]
        
        # Parse headers and SDP
        current_section = 'headers'
        sdp_lines = []
        
        for line in lines[1:]:
            if not line.strip():
                current_section = 'sdp'
                continue
                
            if current_section == 'headers':
                if ': ' in line:
                    key, value = line.split(': ', 1)
                    result['headers'][key] = value
            elif current_section == 'sdp':
                sdp_lines.append(line)
        
        # Parse SDP if present
        if sdp_lines:
            result['sdp'] = {}
            for line in sdp_lines:
                if '=' in line:
                    key, value = line.split('=', 1)
                    result['sdp'][key] = value.strip()
                    # Special handling for media line
                    if key == 'm':
                        parts = value.strip().split()
                        if len(parts) >= 3 and parts[0] == 'audio':
                            try:
                                result['sdp']['audio_port'] = int(parts[1])
                                print(f"[DEBUG] Found audio port in SDP: {parts[1]}")
                            except ValueError:
                                pass
        
        return result
    except Exception as e:
        print(f"Error parsing SIP message: {e}")
        return None

class RTPStream:
    def __init__(self, ssrc: int, direction: str):
        self.ssrc = ssrc
        self.direction = direction
        self.buffer = bytearray()
        self.packet_count = 0
        self.last_seq = None
        self.first_timestamp = None
        self.last_timestamp = None
        self.start_time = time.monotonic()
        self.samples_received = 0
        self.last_save_samples = 0
        self.expected_seq = None
        self.silence_packets = 0
        self.non_silence_packets = 0

    def add_packet(self, payload: bytes, seq: int, timestamp: int):
        # Check for sequence number continuity
        if self.expected_seq is not None and seq != self.expected_seq:
            print(f"[WARN] Sequence discontinuity: expected {self.expected_seq}, got {seq}")
        
        # Update expected sequence number
        self.expected_seq = (seq + 1) & 0xFFFF
        
        # Check if packet is silence
        is_silence = all(b == 0xFF for b in payload)
        if is_silence:
            self.silence_packets += 1
        else:
            self.non_silence_packets += 1
            print(f"Non-silence packet received! First 5 bytes: {[hex(b) for b in payload[:5]]}")
        
        # In G.711, each byte represents one sample
        num_samples = len(payload)
        self.samples_received += num_samples
        self.buffer.extend(payload)
        self.packet_count += 1
        self.last_seq = seq
        if self.first_timestamp is None:
            self.first_timestamp = timestamp
        self.last_timestamp = timestamp

    def get_duration(self) -> float:
        """Get duration in seconds based on samples received"""
        return self.samples_received / 8000.0  # 8kHz sampling rate for G.711

    def get_unsaved_duration(self) -> float:
        """Get duration of unsaved samples in seconds"""
        unsaved_samples = self.samples_received - self.last_save_samples
        return unsaved_samples / 8000.0

    def mark_saved(self):
        """Mark current samples as saved"""
        self.last_save_samples = self.samples_received

    def get_info(self) -> str:
        duration = self.get_duration()
        total_packets = self.silence_packets + self.non_silence_packets
        silence_percent = (self.silence_packets / total_packets * 100) if total_packets > 0 else 0
        
        return (f"RTP Stream {hex(self.ssrc)} ({self.direction}):\n"
                f"  Packets: {self.packet_count}\n"
                f"  Duration: {duration:.2f} seconds\n"
                f"  Data size: {len(self.buffer)} bytes\n"
                f"  Samples: {self.samples_received}\n"
                f"  Silence packets: {self.silence_packets} ({silence_percent:.1f}%)\n"
                f"  Non-silence packets: {self.non_silence_packets} ({100-silence_percent:.1f}%)\n"
                f"  Sample rate check: {self.samples_received/duration:.1f} Hz" if duration > 0 else "N/A")

def debug_wav_file(filename: str):
    """Print detailed information about a WAV file"""
    try:
        with wave.open(filename, 'rb') as wav:
            print(f"\nWAV File Analysis: {filename}")
            print(f"Number of channels: {wav.getnchannels()}")
            print(f"Sample width: {wav.getsampwidth()} bytes")
            print(f"Frame rate: {wav.getframerate()} Hz")
            print(f"Number of frames: {wav.getnframes()}")
            print(f"Duration: {wav.getnframes() / wav.getframerate():.2f} seconds")
            print(f"Total file size: {os.path.getsize(filename)} bytes")
    except Exception as e:
        print(f"Error analyzing WAV file: {e}")

class RTPAudioCapture:
    def __init__(self, server_ip: str, client_ip: str):
        self.server_ip = server_ip
        self.client_ip = client_ip
        self.streams = {}  # Dict[int, RTPStream]
        self.last_packet_time = time.monotonic()
        self.should_stop = False
        self.lock = threading.Lock()
        self.seen_ports = set()
        self.potential_rtp_ports = set()
        self.start_time = time.monotonic()
        self.recording_count = 0  # Counter for saved recordings
        self.target_extension = "1001"  # We only want to record from extension 1001
        self.ignored_ssrcs = set()  # Track SSRCs we've already logged about
        
        # WAV file parameters matching person_1.wav
        self.sample_width = 2      # 16-bit PCM
        self.channels = 1          # Mono
        self.framerate = 8000      # 8kHz
        
        # Setup signal handler for graceful shutdown
        signal.signal(signal.SIGINT, self.signal_handler)
    
    def signal_handler(self, signum, frame):
        print("\nStopping capture...")
        self.print_summary()
        self.should_stop = True
        self.save_audio()
        threading.Timer(2.0, lambda: os._exit(0)).start()
    
    def print_summary(self):
        print("\nCapture Summary:")
        print(f"Total duration: {time.monotonic() - self.start_time:.2f} seconds")
        print(f"\nRTP Streams:")
        for ssrc, stream in self.streams.items():
            print(stream.get_info())
        
        print("\nPort Summary:")
        print("All UDP ports seen:")
        for port in sorted(self.seen_ports):
            print(f"  Port {port}")
        print("\nPotential RTP ports:")
        for port in sorted(self.potential_rtp_ports):
            print(f"  Port {port}")
    
    def save_audio(self):
        # Save each stream separately
        for ssrc, stream in self.streams.items():
            if stream.buffer and stream.get_unsaved_duration() > 0:
                # Include timestamp and recording number in filename
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                duration = stream.get_unsaved_duration()
                
                # Debug info before saving
                print(f"\nPreparing to save audio:")
                print(f"Buffer size: {len(stream.buffer)} bytes")
                print(f"First few bytes: {[hex(b) for b in stream.buffer[:10]]}")
                
                filename = f"rtp_stream_{hex(ssrc)}_{stream.direction}_{timestamp}_{self.recording_count}_{duration:.1f}s.wav"
                
                with wave.open(filename, 'wb') as wav_file:
                    wav_file.setnchannels(self.channels)
                    wav_file.setsampwidth(self.sample_width)
                    wav_file.setframerate(self.framerate)
                    
                    with self.lock:
                        pcm_data = ulaw_to_pcm(bytes(stream.buffer))
                        wav_file.writeframes(pcm_data)
                        print(f"\nSaved stream {hex(ssrc)} ({stream.direction}):")
                        print(f"  Duration: {duration:.2f} seconds")
                        print(f"  Samples: {stream.samples_received}")
                        print(f"  Sample rate: {stream.samples_received/duration:.1f} Hz")
                        print(f"  Buffer size: {len(stream.buffer)} bytes")
                        print(f"  PCM data size: {len(pcm_data)} bytes")
                        
                        # Clear the buffer and mark samples as saved
                        stream.buffer = bytearray()
                        stream.mark_saved()
                
                debug_wav_file(filename)
                self.recording_count += 1
    
    def is_potential_rtp(self, data: bytes, src_ip: str, dst_ip: str, src_port: int, dst_port: int) -> bool:
        """Enhanced RTP packet detection with SSRC tracking"""
        if len(data) < 12:
            return False
        
        try:
            rtp = RTPHeader(data)
            
            # Basic RTP validation
            if rtp.version != 2:  # RTP version should be 2
                return False
            
            # We only want RTP packets from client 1001 (outgoing from client_ip)
            if src_ip != self.client_ip:
                return False

            # We only want packets going to the server
            if dst_ip != self.server_ip:
                return False
                
            # Payload type should be 0 for G.711 μ-law
            if rtp.payload_type != 0:
                return False
            
            # Payload size checks for G.711 (160 bytes is typical for 20ms)
            payload_size = len(data) - 12
            if not (160 <= payload_size <= 240):  # Allow some variation
                return False

            # If we already have a stream, make sure it's the same one
            if self.streams and rtp.ssrc not in self.streams:
                if rtp.ssrc not in self.ignored_ssrcs:
                    print(f"[INFO] Ignoring additional RTP stream {hex(rtp.ssrc)} - already tracking stream {hex(list(self.streams.keys())[0])}")
                    self.ignored_ssrcs.add(rtp.ssrc)
                return False
            
            # Get or create stream for this SSRC
            if not self.streams:  # Only create a stream if we don't have one yet
                print(f"[INFO] New RTP stream detected from client 1001: {hex(rtp.ssrc)}")
                self.streams[rtp.ssrc] = RTPStream(rtp.ssrc, "out")
            
            stream = self.streams[rtp.ssrc]
            
            # Add RTP payload to stream
            stream.add_packet(data[12:], rtp.sequence_number, rtp.timestamp)
            
            return True
            
        except Exception as e:
            print(f"[ERROR] RTP analysis failed: {e}")
            return False

    def packet_callback(self, packet):
        if self.should_stop:
            return True
            
        if UDP not in packet or IP not in packet:
            return
        
        src_port = packet[UDP].sport
        dst_port = packet[UDP].dport
        src_ip = packet[IP].src
        dst_ip = packet[IP].dst
        
        payload_data = bytes(packet[UDP].payload)
        
        # Skip SIP packets
        if src_port == 5060 or dst_port == 5060:
            return
        
        # Check for RTP
        if self.is_potential_rtp(payload_data, src_ip, dst_ip, src_port, dst_port):
            self.last_packet_time = time.monotonic()
    
    def check_timeouts(self):
        while not self.should_stop:
            # Check each stream for 10 seconds of unsaved audio
            for ssrc, stream in self.streams.items():
                unsaved_duration = stream.get_unsaved_duration()
                if unsaved_duration >= 10.0:
                    print(f"\nStream {hex(ssrc)} has {unsaved_duration:.1f} seconds of unsaved audio, saving...")
                    self.save_audio()
            
            # Check for inactivity
            current_time = time.monotonic()
            time_since_last_packet = current_time - self.last_packet_time
            if time_since_last_packet >= 30:
                print("30 seconds without new packets, stopping program...")
                # Save any remaining audio before stopping
                for ssrc, stream in self.streams.items():
                    if stream.get_unsaved_duration() > 0:
                        print(f"Saving final {stream.get_unsaved_duration():.1f} seconds of audio before stopping...")
                        self.save_audio()
                self.should_stop = True
                break
            
            time.sleep(0.1)
    
    def start_capture(self):
        timeout_thread = threading.Thread(target=self.check_timeouts, daemon=True)
        timeout_thread.start()
        
        try:
            print(f"Starting capture between server {self.server_ip} and client {self.client_ip}...")
            print("Listening for UDP packets...")
            
            # Capture all UDP traffic between server and client
            filter_str = f"udp and host {self.server_ip} and host {self.client_ip}"
            print(f"Filter: {filter_str}")
            
            sniff(
                filter=filter_str,
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
            self.save_audio()
            print("\nCapture completed")

def main():
    if len(sys.argv) != 3:
        print("Usage: python listen_and_record.py <server_ip> <client_ip>")
        print("Example: python listen_and_record.py 100.120.241.10 100.120.0.197")
        sys.exit(1)
        
    # Check if running as root
    if os.geteuid() != 0:
        print("This script requires root privileges to capture packets.")
        print("Please run with sudo:")
        print(f"sudo python3 {' '.join(sys.argv)}")
        sys.exit(1)
    
    server_ip = sys.argv[1]
    client_ip = sys.argv[2]
    
    capture = RTPAudioCapture(server_ip, client_ip)
    capture.start_capture()

if __name__ == "__main__":
    main()
