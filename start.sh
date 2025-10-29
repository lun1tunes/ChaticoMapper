#!/bin/bash

# Chatico Mapper App Startup Script

set -e

echo "🚀 Starting Chatico Mapper App..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Copying from env.example..."
    cp env.example .env
    echo "📝 Please edit .env file with your actual values before running again."
    exit 1
fi

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Check if Docker Compose is available
if ! command -v docker-compose > /dev/null 2>&1; then
    echo "❌ Docker Compose is not installed. Please install Docker Compose first."
    exit 1
fi

echo "🐳 Starting services with Docker Compose..."

# Start services
docker-compose up -d

echo "⏳ Waiting for services to be ready..."

# Wait for database
echo "📊 Waiting for PostgreSQL..."
until docker-compose exec -T postgres pg_isready -U chatico_user -d chatico_mapper; do
    sleep 2
done

# Wait for RabbitMQ
echo "🐰 Waiting for RabbitMQ..."
until docker-compose exec -T rabbitmq rabbitmq-diagnostics ping > /dev/null 2>&1; do
    sleep 2
done

# Wait for Redis
echo "🔴 Waiting for Redis..."
until docker-compose exec -T redis redis-cli ping > /dev/null 2>&1; do
    sleep 2
done

# Wait for application
echo "🚀 Waiting for Chatico Mapper App..."
until curl -f http://localhost:8000/monitoring/health > /dev/null 2>&1; do
    sleep 2
done

echo "✅ All services are ready!"
echo ""
echo "🌐 Application URLs:"
echo "   - API Documentation: http://localhost:8000/docs"
echo "   - Health Check: http://localhost:8000/monitoring/health"
echo "   - RabbitMQ Management: http://localhost:15672"
echo "   - Username: chatico_user"
echo "   - Password: chatico_password"
echo ""
echo "📊 To view logs:"
echo "   docker-compose logs -f chatico-mapper"
echo ""
echo "🛑 To stop services:"
echo "   docker-compose down"
