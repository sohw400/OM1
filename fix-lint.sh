#!/bin/bash
# Lint fix script for OM1 project
# Run this script to fix all linting issues automatically

set -e  # Exit on any error

echo "🔧 Fixing lint issues in OM1 project..."

# Change to project directory
cd "$(dirname "$0")"

# Make sure we're using the virtual environment
export PATH=".venv/bin:$PATH"

echo "📋 Running Ruff (code quality + import sorting)..."
python -m ruff check --fix

echo "🎨 Running Black (code formatting)..."
python -m black .

echo "📦 Running isort (import sorting)..."
python -m isort .

echo "✅ Verifying fixes..."
echo "  - Checking Ruff..."
python -m ruff check

echo "  - Checking Black..."
python -m black --check .

echo "  - Checking isort..."
python -m isort --check-only .

echo "🎉 All lint issues fixed successfully!"
echo ""
echo "Optional: Run type checking with:"
echo "  python -m pyright"