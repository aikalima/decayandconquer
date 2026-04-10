#!/bin/bash
cd "$(dirname "$0")/../frontend" || exit 1

if [ ! -d "node_modules" ]; then
    echo "Installing frontend dependencies..."
    npm install
fi

echo "Frontend starting on :6161"
npm run dev
