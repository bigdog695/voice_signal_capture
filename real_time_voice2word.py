import wave
import time
import threading
import numpy as np
import socket
import struct
import logging
from funasr import AutoModel
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

class VoiceToTextReceiver(threading.Thread):
    def __init__(self, listen_ip="0.0.0.0", listen_port=5062, sample_rate=16000):
        super().__init__()
        self.listen_ip = listen_ip
        self.listen_port = listen_port
        self.sample_rate = sample_rate
        self.running = True
        self.audio_buffer = []
        
        # Initialize ASR model
        self.model = AutoModel(
            model="/home/bigdog695/.cache/modelscope/hub/models/iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online"
        )
        
        # Create UDP socket for receiving
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.socket.bind((listen_ip, listen_port))
        self.socket.settimeout(1.0)  # 1 second timeout for stopping
        
        # Buffer for accumulating audio data for ASR
        self.asr_buffer = []
        self.asr_buffer_duration = 2.0  # Process 2 seconds of audio at a time
        self.samples_per_buffer = int(self.sample_rate * self.asr_buffer_duration)
        
        logger.info(f"VoiceToTextReceiver initialized - Listening on {listen_ip}:{listen_port}")
    
    def process_audio_for_asr(self, audio_data):
        """Process accumulated audio data with ASR"""
        try:
            # Convert audio data to proper format for ASR
            audio_array = np.array(audio_data, dtype=np.float32)
            
            # Normalize audio
            if audio_array.max() > 1.0 or audio_array.min() < -1.0:
                audio_array = audio_array / 32768.0  # Normalize 16-bit audio
            
            # Save audio to temporary WAV file (FunASR requires wav file input)
            temp_wav = "/tmp/temp_audio.wav"
            with wave.open(temp_wav, 'wb') as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self.sample_rate)
                wf.writeframes((audio_array * 32768).astype(np.int16).tobytes())
            
            # Perform ASR
            result = self.model.generate(input=temp_wav)
            
            # Print result if not empty
            if result and result[0] and result[0].get('text', '').strip():
                print(f"识别结果: {result[0]['text']}")
            
        except Exception as e:
            logger.error(f"Error in ASR processing: {e}")
    
    def process_packet(self, packet_data):
        try:
            # Unpack RTP packet
            rtp_packet, audio_data = RTPPacket.unpack(packet_data)
            
            # Convert bytes to numpy array
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Add to ASR buffer
            self.asr_buffer.extend(audio_array)
            
            # If we have enough data, process it
            if len(self.asr_buffer) >= self.samples_per_buffer:
                # Process the buffer
                self.process_audio_for_asr(self.asr_buffer[:self.samples_per_buffer])
                # Keep the remainder
                self.asr_buffer = self.asr_buffer[self.samples_per_buffer:]
                
        except Exception as e:
            logger.error(f"Error processing packet: {e}")
    
    def run(self):
        logger.info("Starting packet capture and ASR")
        while self.running:
            try:
                packet_data, addr = self.socket.recvfrom(65535)
                self.process_packet(packet_data)
            except socket.timeout:
                continue
            except Exception as e:
                logger.error(f"Error in VoiceToTextReceiver: {e}")
    
    def stop(self):
        logger.info("Stopping VoiceToTextReceiver")
        self.running = False
        self.socket.close()

def main():
    # Create and start receiver thread
    receiver = VoiceToTextReceiver()
    receiver.start()
    
    try:
        # Keep main thread running
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        # Stop thread on keyboard interrupt
        logger.info("Received keyboard interrupt, stopping thread")
        receiver.stop()
        receiver.join()
        logger.info("Thread stopped")

if __name__ == "__main__":
    main()
