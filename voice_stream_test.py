import zmq
import json
import wave
import time
from binascii import unhexlify

def main():
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://localhost:5555")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")  # Subscribe to all messages
    
    print("Listening for voice stream messages...")
    
    while True:
        message = socket.recv_json()
        
        if message["type"] == "voice_segment":
            # Save voice segment
            filename = f"call_{message['call_id']}_{message['sequence']}.wav"
            wav_data = unhexlify(message["data"])
            with open(filename, "wb") as f:
                f.write(wav_data)
            print(f"Saved segment {message['sequence']} from call {message['call_id']}")
            
        elif message["type"] == "call_end":
            print(f"Call ended: {message['call_id']} from {message['client_ip']}")

if __name__ == "__main__":
    main()