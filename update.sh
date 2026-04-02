#!/bin/bash
set -e

echo "=== EDQ Update ==="

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  echo "ERROR: .env not found. Run setup.sh first."
  exit 1
fi

echo "Fetching latest changes from GitHub..."
git fetch origin

echo "Switching to main..."
git switch main

echo "Pulling latest official release..."
git pull --ff-only origin main

echo "Rebuilding EDQ containers..."
docker compose up --build -d

echo ""
echo "Current container status:"
docker compose ps

echo ""
echo "=== EDQ update complete ==="
echo "Open http://localhost"
