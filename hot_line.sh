#!/bin/bash

# This script is intended to be run from the project root directory.
cd "$(dirname "$0")" || exit

RTP_PID_FILE="rtp.pid"
WS_PID_FILE="websocket.pid"
RTP_LOG_FILE="rtp.log"
WS_LOG_FILE="websocket.log"

# Correcting paths to scripts based on project structure
RTP_CMD="bash RTP_start.sh"
WS_CMD="/root/miniconda3/envs/py310/bin/python3 websocket.py"

start() {
    echo "Starting hot line services..."
    
    # Start RTP
    if [ -f "$RTP_PID_FILE" ] && ps -p "$(cat $RTP_PID_FILE)" > /dev/null; then
        echo "RTP service is already running (PID: $(cat $RTP_PID_FILE))."
    else
        echo "Starting RTP service..."
        nohup $RTP_CMD > "$RTP_LOG_FILE" 2>&1 &
        echo $! > "$RTP_PID_FILE"
        echo "RTP service started with PID: $(cat $RTP_PID_FILE). Log: $RTP_LOG_FILE"
    fi

    # Start WebSocket
    if [ -f "$WS_PID_FILE" ] && ps -p "$(cat $WS_PID_FILE)" > /dev/null; then
        echo "WebSocket service is already running (PID: $(cat $WS_PID_FILE))."
    else
        echo "Starting WebSocket service..."
        nohup $WS_CMD > "$WS_LOG_FILE" 2>&1 &
        echo $! > "$WS_PID_FILE"
        echo "WebSocket service started with PID: $(cat $WS_PID_FILE). Log: $WS_LOG_FILE"
    fi
}

stop() {
    echo "Stopping hot line services..."

    # Stop RTP
    if [ -f "$RTP_PID_FILE" ]; then
        pid=$(cat "$RTP_PID_FILE")
        echo "Stopping RTP service (PID: $pid)..."
        if ps -p "$pid" > /dev/null; then
            kill "$pid"
        else
            echo "RTP process not found."
        fi
        rm "$RTP_PID_FILE"
    else
        echo "RTP service not running (no PID file)."
    fi

    # Stop WebSocket
    if [ -f "$WS_PID_FILE" ]; then
        pid=$(cat "$WS_PID_FILE")
        echo "Stopping WebSocket service (PID: $pid)..."
        if ps -p "$pid" > /dev/null; then
            kill "$pid"
        else
            echo "WebSocket process not found."
        fi
        rm "$WS_PID_FILE"
    else
        echo "WebSocket service not running (no PID file)."
    fi
    
    echo "Stop commands issued."
}

restart() {
    echo "Restarting services..."
    stop
    sleep 2
    start
}

case "$1" in
    start)
        start
        ;;
    stop)
        stop
        ;;
    restart)
        restart
        ;;
    *)
        echo "Usage: $0 {start|stop|restart}"
        exit 1
esac
