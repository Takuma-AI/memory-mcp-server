#!/bin/bash
# MCP Server wrapper script for memory
# This ensures environment variables are loaded from .env

# Get the directory of this script
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

# Load environment from .env file if it exists
if [ -f "$PROJECT_ROOT/.env" ]; then
    export $(grep -v '^#' "$PROJECT_ROOT/.env" | xargs)
fi

# Special handling for pdf-generator libraries on macOS
if [ "claude-history" = "pdf-generator" ] && command -v brew &> /dev/null; then
    export DYLD_LIBRARY_PATH="/opt/homebrew/lib:/usr/local/lib:$DYLD_LIBRARY_PATH"
fi

# Run the server with the virtual environment
exec "$SCRIPT_DIR/venv/bin/python" "$SCRIPT_DIR/server.py"