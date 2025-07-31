#!/bin/bash
set -e

echo "🎭 Running Playwright E2E Tests..."

# Source environment variables if .env exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs)
fi

# Install browsers if not already installed
echo "📦 Ensuring Playwright browsers are installed..."
uv run playwright install chromium

# Run the Playwright tests
echo "🧪 Running tests..."
if [ "$1" == "--headed" ]; then
    echo "Running in headed mode..."
    PLAYWRIGHT_HEADLESS=false uv run pytest tests/e2e/playwright/ -v -m playwright
else
    echo "Running in headless mode..."
    PLAYWRIGHT_HEADLESS=true uv run pytest tests/e2e/playwright/ -v -m playwright
fi

echo "✅ Playwright tests completed!"