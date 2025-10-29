# Chatico Mapper App

Instagram Webhook Proxy Router with RabbitMQ Integration

## 🎯 Overview

Chatico Mapper App is a FastAPI-based proxy application that receives Instagram webhooks, extracts media owner information, and routes webhooks to appropriate worker applications using RabbitMQ for guaranteed delivery. The application follows Clean Architecture patterns with Dependency Injection and Repository Pattern.

## 🏗️ Architecture

- **Proxy Pattern + Message Queue + Service Discovery with Dynamic Routing**
- **Clean Architecture** with layered separation
- **Dependency Injection** using dependency-injector
- **Repository Pattern** for data access abstraction
- **Protocol-based interfaces** for service abstraction
- **Async/await** throughout the application

## 🚀 Features

### Core Functionality
- ✅ Instagram webhook processing with HMAC-SHA256 signature validation
- ✅ Media owner resolution via Instagram Graph API
- ✅ Dynamic worker app management with CRUD operations
- ✅ RabbitMQ integration with guaranteed delivery
- ✅ Dead letter queues for failed messages
- ✅ Comprehensive logging and monitoring

### Security
- ✅ Webhook signature validation
- ✅ Rate limiting
- ✅ Request size validation
- ✅ Secure credential management

### Monitoring
- ✅ Health checks
- ✅ Performance metrics
- ✅ Webhook processing logs
- ✅ RabbitMQ queue monitoring

## 📋 Requirements

- Python 3.13+
- PostgreSQL 15+
- RabbitMQ 3.12+
- Redis 7+ (optional)

## 🛠️ Installation

### Using Docker Compose (Recommended)

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd chatico-mapper-app
   ```

2. **Configure environment variables**
   ```bash
   cp env.example .env
   # Edit .env with your actual values
   ```

3. **Start the application**
   ```bash
   docker-compose up -d
   ```

### Manual Installation

1. **Install dependencies**
   ```bash
   poetry install
   ```

2. **Set up database**
   ```bash
   # Start PostgreSQL
   # Create database: chatico_mapper
   ```

3. **Run migrations**
   ```bash
   alembic upgrade head
   ```

4. **Start the application**
   ```bash
   poetry run python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `INSTAGRAM_APP_ID` | Instagram App ID | Yes |
| `INSTAGRAM_APP_SECRET` | Instagram App Secret | Yes |
| `INSTAGRAM_ACCESS_TOKEN` | Instagram Access Token | Yes |
| `WEBHOOK_SECRET` | Webhook verification secret | Yes |
| `WEBHOOK_VERIFY_TOKEN` | Webhook verification token | Yes |
| `SECRET_KEY` | Application secret key | Yes |
| `DATABASE_URL` | PostgreSQL connection URL | Yes |
| `RABBITMQ_URL` | RabbitMQ connection URL | Yes |

### Instagram API Setup

1. Create a Facebook App at [Facebook Developers](https://developers.facebook.com/)
2. Add Instagram Basic Display product
3. Configure webhook URL: `https://your-domain.com/webhook/`
4. Set webhook fields: `comments`
5. Get your App ID, App Secret, and Access Token

## 📚 API Documentation

Once the application is running, visit:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Key Endpoints

#### Webhook Processing
- `POST /webhook/` - Process Instagram webhook
- `GET /webhook/` - Instagram verification challenge

#### Worker App Management
- `POST /worker-apps/` - Create worker app
- `GET /worker-apps/` - List worker apps
- `PUT /worker-apps/{id}` - Update worker app
- `DELETE /worker-apps/{id}` - Delete worker app
- `POST /worker-apps/{id}/toggle` - Toggle active status

#### Monitoring
- `GET /monitoring/health` - Health check
- `GET /monitoring/metrics` - Application metrics
- `GET /monitoring/webhook-logs` - Webhook logs

## 🔄 Processing Flow

1. **Webhook Reception**: Receive Instagram webhook POST request
2. **Signature Validation**: Validate HMAC-SHA256 signature
3. **Media Owner Resolution**: Extract media IDs and resolve owner IDs
4. **Routing Decision**: Find appropriate worker app by owner ID
5. **RabbitMQ Publishing**: Publish message to worker app queue
6. **Logging**: Record processing results and metrics

## 🐳 Docker Services

- **chatico-mapper**: FastAPI application
- **postgres**: PostgreSQL database
- **rabbitmq**: RabbitMQ message broker
- **redis**: Redis cache (optional)
- **nginx**: Reverse proxy (optional)

## 📊 Monitoring

### Health Checks
- Application health: `GET /monitoring/health`
- Database connectivity
- RabbitMQ connectivity
- Service status

### Metrics
- Webhook processing statistics
- Worker app performance
- RabbitMQ queue sizes
- Processing times

### Logs
- Structured JSON logging
- Request/response logging
- Error tracking
- Performance metrics

## 🔧 Development

### Project Structure
```
app/
├── __init__.py
├── main.py              # FastAPI application
├── api.py               # API endpoints
├── dependencies.py      # Dependency injection
├── models.py            # Database models
├── schemas.py           # Pydantic schemas
├── repositories.py      # Repository pattern
├── services.py          # Core services
├── use_cases.py         # Business logic
└── config.py            # Configuration
```

### Running Tests
```bash
# Install test dependencies
poetry install --with dev

# Run tests
poetry run pytest
```

### Database Migrations
```bash
# Create new migration
alembic revision --autogenerate -m "Description"

# Apply migrations
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

## 🚀 Deployment

### Production Considerations

1. **Environment Variables**: Set all required environment variables
2. **Database**: Use managed PostgreSQL service
3. **RabbitMQ**: Use managed RabbitMQ service or cluster
4. **SSL/TLS**: Configure HTTPS for webhook endpoints
5. **Monitoring**: Set up monitoring and alerting
6. **Logging**: Configure centralized logging
7. **Scaling**: Use load balancer for horizontal scaling

### Docker Production
```bash
# Build production image
docker build -t chatico-mapper-app .

# Run with production settings
docker run -d \
  --name chatico-mapper \
  --env-file .env \
  -p 8000:8000 \
  chatico-mapper-app
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue in the repository
- Check the documentation
- Review the API documentation at `/docs`

## 🔗 Links

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [SQLAlchemy Documentation](https://docs.sqlalchemy.org/)
- [RabbitMQ Documentation](https://www.rabbitmq.com/documentation.html)
- [Instagram Graph API](https://developers.facebook.com/docs/instagram-api/)