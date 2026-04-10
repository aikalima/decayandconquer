#!/bin/bash
DIR="$(dirname "$0")"
"$DIR/stop-backend.sh"
"$DIR/start-backend.sh"
tail -f "$(dirname "$0")/../backend/server_log.out"
