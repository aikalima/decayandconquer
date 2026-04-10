#!/bin/bash
lsof -ti :6173 | xargs kill -9 2>/dev/null
echo "Backend stopped"
