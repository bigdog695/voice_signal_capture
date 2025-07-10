import requests
import json
import threading
import logging
import numpy as np
import wave
import tempfile
import os
from datetime import datetime
from sseclient import SSEClient
from funasr import AutoModel
import zmq
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SIPSession:
    def __init__(self):
        self.call_id = None
        self.from_uri = None
        self.to_uri = None
        self.user_agent = None
        self.rtp_port = None
        self.source_ip = None
        self.audio_buffer = []
        self.sequence_numbers = set()
        self.last_sequence = None
        
    def __str__(self):
        return (f"Call-ID: {self.call_id}\n"
                f"From: {self.from_uri}\n"
                f"To: {self.to_uri}\n"
                f"User-Agent: {self.user_agent}\n"
                f"RTP Port: {self.rtp_port}\n"
                f"Source IP: {self.source_ip}")

class RTPStreamProcessor:
    def __init__(self, stream_url="http://localhost:5000/stream", zmq_pub_port=5555):
        self.stream_url = stream_url
        self.sessions = {}  # key: call_id, value: SIPSession
        self.running = True
        
        # Initialize ASR model
        self.asr_model = AutoModel(
            model="/home/bigdog695/.cache/modelscope/hub/models/iic/speech_paraformer-large_asr_nat-zh-cn-16k-common-vocab8404-online"
        )
        
        # Audio buffer settings
        self.sample_rate = 16000
        self.buffer_duration = 2.0  # seconds
        self.buffer_size = int(self.sample_rate * self.buffer_duration)
        
        # Initialize ZMQ publisher
        self.zmq_context = zmq.Context()
        self.publisher = self.zmq_context.socket(zmq.PUB)
        self.publisher.bind(f"tcp://*:{zmq_pub_port}")
        logger.info(f"ZMQ publisher started on port {zmq_pub_port}")

    def publish_session_info(self, session):
        """Publish session information"""
        try:
            message = {
                'type': 'session_info',
                'timestamp': datetime.now().isoformat(),
                'data': {
                    'call_id': session.call_id,
                    'from_uri': session.from_uri,
                    'to_uri': session.to_uri,
                    'user_agent': session.user_agent,
                    'rtp_port': session.rtp_port,
                    'source_ip': session.source_ip
                }
            }
            self.publisher.send_string(f"session.{session.call_id} {json.dumps(message)}")
            logger.debug(f"Published session info for {session.call_id}")
        except Exception as e:
            logger.error(f"Error publishing session info: {e}")

    def publish_transcription(self, session_id, text):
        """Publish transcription result"""
        try:
            message = {
                'type': 'transcription',
                'timestamp': datetime.now().isoformat(),
                'data': {
                    'call_id': session_id,
                    'text': text
                }
            }
            self.publisher.send_string(f"transcription.{session_id} {json.dumps(message)}")
            logger.debug(f"Published transcription for {session_id}")
        except Exception as e:
            logger.error(f"Error publishing transcription: {e}")

    def process_sip_packet(self, packet_data):
        """Process SIP packet and extract session information"""
        try:
            # Extract SIP headers
            headers = packet_data.get('sip_headers', {})
            call_id = headers.get('Call-ID')
            if not call_id:
                return None
            
            # Create or get session
            if call_id not in self.sessions:
                self.sessions[call_id] = SIPSession()
                self.sessions[call_id].call_id = call_id
            
            session = self.sessions[call_id]
            
            # Update session information
            if 'From' in headers:
                session.from_uri = headers['From']
            if 'User-Agent' in headers:
                session.user_agent = headers['User-Agent']
            if 'source_ip' in packet_data:
                session.source_ip = packet_data['source_ip']
            
            # Extract RTP port from SDP
            sdp = packet_data.get('sdp', {})
            if 'media' in sdp and sdp['media']:
                for media in sdp['media']:
                    if media.get('type') == 'audio':
                        session.rtp_port = media.get('port')
            
            # Publish updated session information
            self.publish_session_info(session)
            logger.info(f"Updated session information:\n{session}")
            return session
            
        except Exception as e:
            logger.error(f"Error processing SIP packet: {e}")
            return None

    def process_audio_buffer(self, session):
        """Process accumulated audio buffer for ASR"""
        try:
            if len(session.audio_buffer) >= self.buffer_size:
                # Convert to numpy array
                audio_array = np.array(session.audio_buffer[:self.buffer_size], dtype=np.float32)
                session.audio_buffer = session.audio_buffer[self.buffer_size:]
                
                # Save to temporary WAV file
                with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as temp_wav:
                    with wave.open(temp_wav.name, 'wb') as wf:
                        wf.setnchannels(1)
                        wf.setsampwidth(2)
                        wf.setframerate(self.sample_rate)
                        wf.writeframes((audio_array * 32768).astype(np.int16).tobytes())
                    
                    # Perform ASR
                    result = self.asr_model.generate(input=temp_wav.name)
                    
                    if result and result[0] and result[0].get('text', '').strip():
                        text = result[0]['text']
                        # Publish transcription result
                        self.publish_transcription(session.call_id, text)
                        logger.info(f"Session {session.call_id} - Transcription: {text}")
                
                # Clean up temporary file
                os.unlink(temp_wav.name)
                
        except Exception as e:
            logger.error(f"Error processing audio buffer: {e}")

    def process_rtp_packet(self, packet_data):
        """Process RTP packet and accumulate audio data"""
        try:
            # Extract session information from RTP packet
            call_id = packet_data.get('call_id')
            if not call_id or call_id not in self.sessions:
                logger.warning(f"Received RTP packet for unknown session: {call_id}")
                return
            
            session = self.sessions[call_id]
            
            # Check sequence number for packet loss
            seq_num = packet_data.get('sequence_number')
            if seq_num in session.sequence_numbers:
                return  # Duplicate packet
            
            session.sequence_numbers.add(seq_num)
            
            if session.last_sequence is not None:
                expected_seq = (session.last_sequence + 1) & 0xFFFF
                if seq_num != expected_seq:
                    logger.warning(f"Packet loss detected in session {call_id}: "
                                 f"expected {expected_seq}, got {seq_num}")
            
            session.last_sequence = seq_num
            
            # Process audio data
            audio_data = bytes.fromhex(packet_data['audio_data'])
            audio_array = np.frombuffer(audio_data, dtype=np.int16).astype(np.float32) / 32768.0
            session.audio_buffer.extend(audio_array)
            
            # Process buffer if enough data accumulated
            self.process_audio_buffer(session)
            
        except Exception as e:
            logger.error(f"Error processing RTP packet: {e}")

    def start(self):
        """Start receiving and processing stream"""
        try:
            logger.info(f"Connecting to stream at {self.stream_url}")
            client = SSEClient(self.stream_url)
            
            for event in client.events():
                if not self.running:
                    break
                
                try:
                    data = json.loads(event.data)
                    
                    # Process based on packet type
                    if data.get('type') == 'sip':
                        self.process_sip_packet(data)
                    elif data.get('type') == 'rtp':
                        self.process_rtp_packet(data)
                    
                except json.JSONDecodeError:
                    logger.error("Failed to decode JSON data from stream")
                except Exception as e:
                    logger.error(f"Error processing stream event: {e}")
            
        except Exception as e:
            logger.error(f"Stream connection error: {e}")
        finally:
            logger.info("Stream processor stopped")
            self.cleanup()

    def cleanup(self):
        """Cleanup resources"""
        self.publisher.close()
        self.zmq_context.term()

    def stop(self):
        """Stop the processor"""
        self.running = False
        logger.info("Stopping stream processor...")

def main():
    processor = RTPStreamProcessor()
    try:
        processor.start()
    except KeyboardInterrupt:
        processor.stop()

if __name__ == "__main__":
    main()
