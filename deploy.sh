#!/bin/bash
set -e

APP_NAME="telegram-bot"

# Read target tag from first argument, or default to "latest"
IMAGE_TAG="${1:-latest}"

PROJECT_DIR="${HOME}/${REPO_NAME:-$(basename "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)")}"
REGISTRY_IMAGE="ghcr.io/${REPO_FULL_NAME}:${IMAGE_TAG}"

echo "Starting deployment..."
echo "Project Directory: $PROJECT_DIR"
echo "Target Image: $REGISTRY_IMAGE"

cd "$PROJECT_DIR"

if [ ! -f .env ]; then
    echo "Error: .env file missing in $PROJECT_DIR" >&2
    exit 1
fi

if [ -n "$GHCR_TOKEN" ] && [ -n "$REPO_OWNER" ]; then
    echo "Authenticating with GHCR..."
    echo "$GHCR_TOKEN" | docker login ghcr.io -u "$REPO_OWNER" --password-stdin
fi

echo "Pulling Docker image ($IMAGE_TAG) from GHCR..."
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

echo "Deployment finished successfully for tag: $IMAGE_TAG"