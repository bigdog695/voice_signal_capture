import wave
import time
import threading
import numpy as np
import socket
import struct
import logging
import sounddevice as sd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    def __init__(self, wav_file, target_ip="127.0.0.1", target_port=5060):
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

class VoiceReceiver(threading.Thread):
    def __init__(self, listen_ip="0.0.0.0", listen_port=5061, output_device=None, sample_rate=44100):
        super().__init__()
        self.listen_ip = listen_ip
        self.listen_port = listen_port
        self.output_device = output_device
        self.sample_rate = sample_rate
        self.running = True
        self.audio_buffer = []
        
        # Create UDP socket for receiving
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((listen_ip, listen_port))
        self.socket.settimeout(1.0)  # 1 second timeout for stopping
        
        logger.info(f"VoiceReceiver initialized - Listening on {listen_ip}:{listen_port}")
        
    def process_packet(self, packet_data):
        try:
            # Unpack RTP packet
            rtp_packet, audio_data = RTPPacket.unpack(packet_data)
            
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Add to buffer
            self.audio_buffer.extend(audio_array)
            
            # If buffer is large enough, play audio
            if len(self.audio_buffer) >= self.sample_rate // 10:  # 100ms of audio
                audio_chunk = np.array(self.audio_buffer[:self.sample_rate // 10])
                sd.play(audio_chunk, self.sample_rate)
                self.audio_buffer = self.audio_buffer[self.sample_rate // 10:]
        except Exception as e:
            logger.error(f"Error processing packet: {e}")
    
    def run(self):
        logger.info("Starting packet capture")
        while self.running:
            try:
                packet_data, addr = self.socket.recvfrom(65535)
                self.process_packet(packet_data)
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error in VoiceReceiver: {e}")
    
    def stop(self):
        logger.info("Stopping VoiceReceiver")
        self.running = False
        self.socket.close()

def main():
    # Create and start sender thread
    wav_file = "/data/barryhuang/voice_model/test.wav"
    sender = VoiceSender(wav_file, target_port=5062)  # Send to port 5062 (ASR receiver)
    sender.start()
    
    # Create and start receiver thread for audio playback
    receiver = VoiceReceiver(listen_port=5061)  # Listen on different port
    receiver.start()
    
    try:
        # Keep main thread running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # Stop threads on keyboard interrupt
        logger.info("Received keyboard interrupt, stopping threads")
        sender.stop()
        receiver.stop()
        sender.join()
        receiver.join()
        logger.info("All threads stopped")

if __name__ == "__main__":
    main()
