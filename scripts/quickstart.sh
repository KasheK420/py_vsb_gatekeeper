#!/bin/bash

# Gatekeeper Quick Start Script
# This script helps you set up and deploy Gatekeeper bot quickly

set -e

echo "🔐 Gatekeeper Bot - Quick Start"
echo "================================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  No .env file found!"
    echo ""
    echo "Copying .env.example to .env..."
    cp .env.example .env
    echo "✅ Done!"
    echo ""
    echo "📝 Please edit .env with your configuration:"
    echo "   - DISCORD_TOKEN"
    echo "   - DISCORD_GUILD_ID"
    echo "   - CAS configuration (CAS_SERVER_URL, etc.)"
    echo "   - Channel and role IDs"
    echo "   - Secret keys (generate with: openssl rand -hex 32)"
    echo ""
    echo "After configuring .env, run this script again."
    exit 1
fi

echo "✅ .env file found"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed!"
    echo "   Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

echo "✅ Docker is installed"
echo ""

# Check if Docker Compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ Docker Compose is not installed!"
    echo "   Please install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

echo "✅ Docker Compose is installed"
echo ""

# Build and start services
echo "🏗️  Building Docker images..."
docker-compose build

echo ""
echo "🚀 Starting services..."
docker-compose up -d

echo ""
echo "⏳ Waiting for services to be ready..."
sleep 5

# Check if services are running
echo ""
echo "📊 Service Status:"
docker-compose ps

echo ""
echo "✅ Gatekeeper is starting!"
echo ""
echo "📝 Next steps:"
echo "   1. Check logs: docker-compose logs -f bot"
echo "   2. Verify bot is online in Discord"
echo "   3. Check verification message in your verification channel"
echo "   4. Test verification flow with a test account"
echo ""
echo "🛠️  Useful commands:"
echo "   - View logs: make logs"
echo "   - Restart: make restart"
echo "   - Stop: make down"
echo "   - Database shell: make db-shell"
echo ""
echo "📖 For more information, see README.md"
echo ""
echo "🎉 Setup complete!"