#!/bin/bash
set -e

# Start the MCP server in the background (SSE mode).
# If it crashes, the container keeps running (NiceGUI is the main process).
MCP_TRANSPORT=sse python -m app.mcp_server &

# Start the NiceGUI app in the foreground.
# `exec` replaces the shell process with Python, so Docker signals
# (stop, restart) reach the app directly instead of being swallowed by bash.
exec python -m app.main
