#!/bin/bash

if [ -f server.pid ]; then
    PID=$(cat server.pid)
    if ps -p $PID > /dev/null; then
        echo "Stopping server with PID $PID..."
        kill $PID
        rm server.pid
        echo "Server stopped."
    else
        echo "Process with PID $PID not found. Maybe it's already stopped."
        rm server.pid
    fi
else
    echo "server.pid not found. Is the server running?"
fi