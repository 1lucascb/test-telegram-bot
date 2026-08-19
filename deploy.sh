#!/bin/bash
set -e # Exit immediately if a command fails

APP_NAME="telegram-bot"
IMAGE_NAME="telegram-bot-image"
PROJECT_DIR="$HOME/test-telegram-bot"

echo "Starting deployment..."

cd "$PROJECT_DIR"

echo "Pulling latest code..."
git pull origin main

echo "Building Docker image..."
docker build -t "$IMAGE_NAME" .

if [ $(docker ps -aq -f name="^${APP_NAME}$") ]; then
    echo "Stopping existing container..."
    docker stop "$APP_NAME"
    docker rm "$APP_NAME"
fi

echo "Starting new container..."
docker run -d \
  --name "$APP_NAME" \
  --restart unless-stopped \
  --env-file .env \
  "$IMAGE_NAME"

docker image prune -f

echo "Deployment finished successfully!"