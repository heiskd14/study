#!/bin/bash

# Get the project root directory
ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Start the Node.js auth backend on port 8000
cd "$ROOT_DIR/hackaton" && node server.js &
NODE_PID=$!

# Wait for the auth service to start
sleep 2

# Start Flask on port 5000 from project root
cd "$ROOT_DIR" && python app.py
