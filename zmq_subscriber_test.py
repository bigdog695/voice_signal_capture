#!/usr/bin/env python3

import zmq
import json
import time
from datetime import datetime
from binascii import unhexlify
import os

def save_voice_segment(message, output_dir="voice_segments"):
    """Save voice segment as WAV file"""
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate filename with timestamp and call info
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{output_dir}/call_{message['call_id']}_seq{message['sequence']}_{timestamp}.wav"
    
    # Convert hex string back to bytes
    wav_data = unhexlify(message['data'])
    
    # Save WAV file
    with open(filename, 'wb') as f:
        f.write(wav_data)
    
    print(f"  Saved to: {filename}")

def main():
    # Initialize ZMQ subscriber
    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    socket.connect("tcp://localhost:5555")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")  # Subscribe to all messages
    
    print(f"[{datetime.now()}] ZMQ Subscriber started - listening on port 5555")
    print("Waiting for messages...")
    
    try:
        while True:
            try:
                # Set timeout to 1 second so we can handle keyboard interrupt
                socket.RCVTIMEO = 1000  # milliseconds
                message = socket.recv_json()
                
                # Print message details based on type
                if message["type"] == "voice_segment":
                    print(f"\n[{datetime.now()}] Received voice segment:")
                    print(f"  Call ID: {message['call_id']}")
                    print(f"  Client IP: {message['client_ip']}")
                    print(f"  Sequence: {message['sequence']}")
                    print(f"  Data size: {len(message['data'])//2} bytes")  # Divide by 2 because it's hex encoded
                    
                    # Save the voice segment
                    save_voice_segment(message)
                    
                elif message["type"] == "call_end":
                    print(f"\n[{datetime.now()}] Call ended:")
                    print(f"  Call ID: {message['call_id']}")
                    print(f"  Client IP: {message['client_ip']}")
                
            except zmq.error.Again:
                # Timeout - just continue
                continue
                
    except KeyboardInterrupt:
        print("\nShutting down subscriber...")
    finally:
        socket.close()
        context.term()

if __name__ == "__main__":
    main() 