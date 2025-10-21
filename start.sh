#!/bin/bash

VENV_DIR="venv"

# Check if the virtual environment directory exists
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "Virtual environment created."

    echo "Activating virtual environment..."
    source $VENV_DIR/bin/activate
    echo "Virtual environment activated."

    echo "Installing dependencies..."
    pip install -r requirements.txt
    echo "Dependencies installed."
else
    echo "Activating virtual environment..."
    source $VENV_DIR/bin/activate
    echo "Virtual environment activated."
fi

# Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 > server.log 2>&1 &
echo $! > server.pid
echo "Server started with PID $(cat server.pid)"