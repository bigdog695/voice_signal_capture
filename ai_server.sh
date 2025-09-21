#!/bin/bash

# This script is intended to be run from the project root directory.
cd "$(dirname "$0")" || exit

PID_DIR="." # PID file in the project root
PID_FILE="$PID_DIR/ai_server.pid"
LOG_FILE="ai_server.log"

# The command needs to point to the correct script location.
CMD="/home/barryhuang/miniconda3/envs/py310/bin/python daemon.py"

start() {
    if [ -f "$PID_FILE" ]; then
        pid=$(cat "$PID_FILE")
        if ps -p "$pid" > /dev/null; then
            echo "AI Server is already running with PID: $pid"
            exit 1
        else
            echo "Warning: PID file found but process is not running. Overwriting."
            rm "$PID_FILE"
        fi
    fi
    echo "Starting AI Server..."
    nohup $CMD > "$LOG_FILE" 2>&1 &
    echo $! > "$PID_FILE"
    echo "AI Server started with PID: $(cat $PID_FILE). Log: $LOG_FILE"
}

stop() {
    if [ ! -f "$PID_FILE" ]; then
        echo "AI Server is not running (no PID file)."
        exit 1
    fi
    pid=$(cat "$PID_FILE")
    echo "Stopping AI Server (PID: $pid)..."
    if ! ps -p "$pid" > /dev/null; then
        echo "Process with PID $pid not found. Removing stale PID file."
        rm "$PID_FILE"
        exit 1
    fi
    
    kill "$pid"
    sleep 2
    if ps -p "$pid" > /dev/null; then
        echo "AI Server did not stop gracefully, sending SIGKILL..."
        kill -9 "$pid"
    fi
    rm "$PID_FILE"
    echo "AI Server stopped."
}

restart() {
    echo "Restarting AI Server..."
    stop
    sleep 1
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
