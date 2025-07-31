#!/bin/bash
set -e

echo "🚀 Starting Auth Gateway and MCP Server..."

# Set environment variables
export JWT_SECRET_KEY=test-secret
export POSTGRES_DSN=postgresql://mcp_user:mcp_password@localhost:5432/mcp_retriever
export MCP_INTERNAL_API_KEY=test-internal-key
export MCP_SERVER_URL=http://localhost:8001
export AUTH_GATEWAY_URL=http://localhost:8000
export TAVILY_API_KEY=test-tavily-key
export REDIS_HOST=localhost
export QDRANT_HOST=localhost

# Start Auth Gateway
echo "Starting Auth Gateway on port 8000..."
JWT_SECRET_KEY=$JWT_SECRET_KEY \
POSTGRES_DSN=$POSTGRES_DSN \
MCP_SERVER_URL=$MCP_SERVER_URL \
MCP_INTERNAL_API_KEY=$MCP_INTERNAL_API_KEY \
uv run python -m src.auth.server &

AUTH_PID=$!
echo "Auth Gateway PID: $AUTH_PID"

# Wait for Auth Gateway to start
sleep 3

# Start MCP Server
echo "Starting MCP Server on port 8001..."
MCP_TRANSPORT=http \
JWT_SECRET_KEY=$JWT_SECRET_KEY \
MCP_INTERNAL_API_KEY=$MCP_INTERNAL_API_KEY \
AUTH_GATEWAY_URL=$AUTH_GATEWAY_URL \
TAVILY_API_KEY=$TAVILY_API_KEY \
REDIS_HOST=$REDIS_HOST \
QDRANT_HOST=$QDRANT_HOST \
uv run python -m src.server_unified &

MCP_PID=$!
echo "MCP Server PID: $MCP_PID"

echo "✅ Both servers started!"
echo "Auth Gateway: http://localhost:8000"
echo "MCP Server: http://localhost:8001"
echo ""
echo "Press Ctrl+C to stop both servers"

# Wait for interrupt
wait