#!/bin/bash
# Script to start the webhook server for GitHub App integration
# 
# Usage:
#   ./scripts/start_webhook_server.sh
#
# Prerequisites:
#   1. Install ngrok: brew install ngrok
#   2. Set up ngrok auth: ngrok config add-authtoken YOUR_TOKEN
#   3. Set environment variables in .env file:
#      - GITHUB_WEBHOOK_SECRET: Secret for webhook signature verification
#      - GITHUB_TOKEN: Personal access token for GitHub API
#      - OPENAI_API_KEY or BYTEZ_API_KEY: For LLM access

set -e

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT"

# Load environment variables
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Default port
PORT=${PORT:-8000}

echo "=========================================="
echo "Multi-Agent Code Review - Webhook Server"
echo "=========================================="
echo ""
echo "Starting server on port $PORT..."
echo ""

# Check if ngrok is installed
if command -v ngrok &> /dev/null; then
    echo "To expose your webhook to the internet, run in another terminal:"
    echo "  ngrok http $PORT"
    echo ""
    echo "Then use the ngrok URL + /webhooks/github as your webhook URL."
    echo "Example: https://abc123.ngrok.io/webhooks/github"
    echo ""
fi

echo "Local webhook endpoint: http://localhost:$PORT/webhooks/github"
echo "API documentation: http://localhost:$PORT/docs"
echo ""
echo "=========================================="
echo ""

# Activate virtual environment
source venv/bin/activate

# Start the server
python -m src.cli server --port $PORT
