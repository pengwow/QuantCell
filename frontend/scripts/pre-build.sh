#!/bin/sh
# Pre-build script to clean up before packaging

echo "🧹 Cleaning up before build..."

# Get the absolute path to the project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
FRONTEND_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$FRONTEND_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"

echo "Project root: $PROJECT_ROOT"
echo "backend dir: $BACKEND_DIR"

# Remove ALL .venv directories recursively from python directory
echo "Searching for .venv directories..."
VENV_COUNT=$(find "$BACKEND_DIR" -type d -name ".venv" | wc -l)

if [ "$VENV_COUNT" -gt 0 ]; then
    echo "Found $VENV_COUNT .venv directories, removing..."
    find "$BACKEND_DIR" -type d -name ".venv" -exec rm -rf {} + 2>/dev/null || true
    echo "✓ Removed all .venv directories"
else
    echo "No .venv directories found (already clean)"
fi

# Remove __pycache__ directories
echo "Removing __pycache__ directories..."
find "$BACKEND_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Remove .pyc files
echo "Removing .pyc files..."
find "$BACKEND_DIR" -type f -name "*.pyc" -delete 2>/dev/null || true

# Remove .pytest_cache
if [ -d "$BACKEND_DIR/.pytest_cache" ]; then
    echo "Removing .pytest_cache..."
    rm -rf "$BACKEND_DIR/.pytest_cache"
fi

echo "✓ Cleanup complete"

