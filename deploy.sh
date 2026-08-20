#!/bin/bash
set -e # Exit immediately if a command fails

APP_NAME="telegram-bot"

# Dynamically set project directory based on the repository name
# If REPO_NAME is not set, it falls back to the folder where deploy.sh lives
PROJECT_DIR="${HOME}/${REPO_NAME:-$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")}"
REGISTRY_IMAGE="ghcr.io/${REPO_FULL_NAME}:latest"

echo "Starting deployment..."
echo "Project Directory: $PROJECT_DIR"
echo "Target Image: $REGISTRY_IMAGE"

cd "$PROJECT_DIR"

# Ensure .env file exists
if [ ! -f .env ]; then
    echo "Error: .env file missing in $PROJECT_DIR" >&2
    exit 1
fi

# Log in to GitHub Container Registry
if [ -n "$GHCR_TOKEN" ] && [ -n "$REPO_OWNER" ]; then
    echo "Authenticating with GHCR..."
    echo "$GHCR_TOKEN" | docker login ghcr.io -u "$REPO_OWNER" --password-stdin
fi

echo "Pulling latest Docker image from GHCR..."
docker pull "$REGISTRY_IMAGE"

echo "Replacing existing container..."
docker rm -f "$APP_NAME" 2>/dev/null || true

echo "Starting new container..."
docker run -d \
  --name "$APP_NAME" \
  --restart unless-stopped \
  --env-file .env \
  "$REGISTRY_IMAGE"

echo "Cleaning up dangling images..."
docker image prune -f

echo "Deployment finished successfully!"