# Testing Guide for Chatico Mapper App

This document provides comprehensive information about testing the Chatico Mapper App.

## 🧪 Test Structure

The test suite is organized into several categories:

```
tests/
├── conftest.py                    # Shared fixtures and configuration
├── factories/                     # Test data factories
│   └── __init__.py
├── unit/                          # Unit tests
│   ├── test_instagram_service.py
│   ├── test_rabbitmq_service.py
│   ├── test_routing_service.py
│   ├── test_webhook_logging_service.py
│   ├── test_process_webhook_use_case.py
│   └── test_manage_worker_apps_use_case.py
├── integration/                   # Integration tests
│   ├── test_webhook_endpoints.py
│   ├── test_worker_app_endpoints.py
│   └── test_monitoring_endpoints.py
└── fixtures/                      # Additional test fixtures
```

## 🚀 Running Tests

### Quick Start

```bash
# Run all tests with coverage
./run_tests.sh

# Run only unit tests
./run_tests.sh --unit-only

# Run only integration tests
./run_tests.sh --integration-only

# Run tests in parallel
./run_tests.sh --parallel

# Run with verbose output
./run_tests.sh --verbose
```

### Using Poetry Directly

```bash
# Install test dependencies
poetry install --with dev

# Run all tests
poetry run pytest

# Run specific test file
poetry run pytest tests/unit/test_instagram_service.py

# Run tests with specific markers
poetry run pytest -m "unit"
poetry run pytest -m "integration"
poetry run pytest -m "slow"

# Run tests with coverage
poetry run pytest --cov=app --cov-report=html

# Run tests in parallel
poetry run pytest -n auto
```

### Using pytest directly

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=term-missing

# Run specific tests
pytest -k "test_webhook"

# Run with verbose output
pytest -v

# Run and stop on first failure
pytest -x
```

## 📊 Test Categories

### Unit Tests (`tests/unit/`)

Unit tests focus on testing individual components in isolation:

- **Services**: InstagramService, RabbitMQService, RoutingService, WebhookLoggingService
- **Use Cases**: ProcessWebhookUseCase, ManageWorkerAppsUseCase
- **Models**: Database models and validation
- **Utilities**: Helper functions and utilities

**Markers**: `@pytest.mark.unit`

### Integration Tests (`tests/integration/`)

Integration tests verify that different components work together:

- **API Endpoints**: Webhook processing, worker app management, monitoring
- **Database Integration**: Repository pattern with real database
- **External Services**: Instagram API, RabbitMQ, Redis
- **End-to-End Flows**: Complete webhook processing workflows

**Markers**: `@pytest.mark.integration`

### Performance Tests

Tests that measure performance and scalability:

- **Load Testing**: High-volume webhook processing
- **Stress Testing**: System behavior under extreme load
- **Memory Testing**: Memory usage patterns
- **Response Time Testing**: API response times

**Markers**: `@pytest.mark.slow`, `@pytest.mark.performance`

## 🔧 Test Configuration

### pytest.ini

The main pytest configuration file:

```ini
[tool.pytest.ini_options]
minversion = "8.0"
addopts = [
    "-ra",
    "-q",
    "--strict-markers",
    "--strict-config",
    "--cov=app",
    "--cov-report=term-missing",
    "--cov-report=html:htmlcov",
    "--cov-report=xml",
    "--cov-fail-under=80",
]
testpaths = ["tests"]
asyncio_mode = "auto"
log_cli = true
log_cli_level = "INFO"
```

### Environment Variables

Test environment variables are set in `conftest.py`:

```python
os.environ.update({
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "RABBITMQ_URL": "amqp://guest:guest@localhost:5672/",
    "REDIS_URL": "redis://localhost:6379/0",
    "INSTAGRAM_APP_ID": "test_app_id",
    "INSTAGRAM_APP_SECRET": "test_app_secret",
    "INSTAGRAM_ACCESS_TOKEN": "test_access_token",
    "WEBHOOK_SECRET": "test_webhook_secret",
    "WEBHOOK_VERIFY_TOKEN": "test_verify_token",
    "SECRET_KEY": "test_secret_key",
    "DEBUG": "true",
    "LOG_LEVEL": "DEBUG",
})
```

## 🏗️ Test Fixtures

### Database Fixtures

```python
@pytest.fixture(scope="session")
async def test_engine():
    """Create a test database engine."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()

@pytest.fixture
async def db_session(test_engine):
    """Create a test database session."""
    async_session = sessionmaker(test_engine, class_=AsyncSession)
    async with async_session() as session:
        yield session
        await session.rollback()
```

### Service Fixtures

```python
@pytest.fixture
def mock_instagram_service():
    """Create a mock Instagram service."""
    mock = AsyncMock()
    mock.get_media_info.return_value = {
        "id": "test_media_id",
        "owner": {"id": "test_owner_id"},
        "media_type": "IMAGE",
        "media_url": "https://example.com/image.jpg",
        "timestamp": "2024-01-01T00:00:00Z",
    }
    return mock
```

### Data Fixtures

```python
@pytest.fixture
def sample_webhook_payload():
    """Create a sample Instagram webhook payload."""
    return {
        "object": "instagram",
        "entry": [
            {
                "id": "test_entry_id",
                "time": 1640995200,
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": "test_comment_id",
                            "text": "Test comment",
                            "media_id": "test_media_id",
                            "from": {
                                "id": "test_user_id",
                                "username": "test_user",
                            },
                            "created_time": "2024-01-01T00:00:00Z",
                        },
                    }
                ],
            }
        ],
    }
```

## 🏭 Test Factories

Test factories generate realistic test data:

```python
class WorkerAppFactory(SQLAlchemyModelFactory):
    """Factory for creating WorkerApp instances."""
    
    class Meta:
        model = WorkerApp
        sqlalchemy_session_persistence = "commit"
    
    id = LazyFunction(lambda: str(uuid.uuid4()))
    owner_id = Faker("user_name")
    app_name = Faker("company")
    base_url = Faker("url")
    webhook_path = "/webhook"
    queue_name = Faker("word")
    is_active = True
```

## 📈 Coverage Reports

### HTML Coverage Report

```bash
poetry run pytest --cov=app --cov-report=html
```

The HTML report is generated in `htmlcov/index.html` and provides:
- Line-by-line coverage analysis
- Branch coverage information
- Coverage trends over time
- Interactive coverage exploration

### Terminal Coverage Report

```bash
poetry run pytest --cov=app --cov-report=term-missing
```

Shows coverage summary in the terminal with missing lines highlighted.

### XML Coverage Report

```bash
poetry run pytest --cov=app --cov-report=xml
```

Generates `coverage.xml` for CI/CD integration.

## 🎯 Test Markers

### Built-in Markers

- `@pytest.mark.unit`: Unit tests
- `@pytest.mark.integration`: Integration tests
- `@pytest.mark.slow`: Slow-running tests
- `@pytest.mark.external`: Tests requiring external services

### Custom Markers

```python
@pytest.mark.parametrize("status", ["success", "failed", "routed"])
def test_webhook_processing_status(status):
    """Test webhook processing with different statuses."""
    pass
```

## 🔍 Debugging Tests

### Running Specific Tests

```bash
# Run specific test function
poetry run pytest tests/unit/test_instagram_service.py::TestInstagramService::test_get_media_info_success

# Run tests matching a pattern
poetry run pytest -k "test_webhook"

# Run tests in a specific file
poetry run pytest tests/unit/test_instagram_service.py
```

### Debugging with pdb

```bash
# Drop into debugger on failure
poetry run pytest --pdb

# Drop into debugger at start of each test
poetry run pytest --trace
```

### Verbose Output

```bash
# Show test names and results
poetry run pytest -v

# Show local variables on failure
poetry run pytest -l

# Show captured output
poetry run pytest -s
```

## 🚨 Common Test Issues

### Async Test Issues

```python
# Correct async test
@pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()
    assert result is not None

# Incorrect - missing @pytest.mark.asyncio
async def test_async_function():
    result = await some_async_function()  # This will fail
```

### Mock Issues

```python
# Correct mock usage
@pytest.fixture
def mock_service():
    mock = AsyncMock()
    mock.method.return_value = "expected_value"
    return mock

# Incorrect - not using AsyncMock for async methods
@pytest.fixture
def mock_service():
    mock = MagicMock()  # This won't work for async methods
    return mock
```

### Database Session Issues

```python
# Correct session handling
@pytest.fixture
async def db_session(test_engine):
    async_session = sessionmaker(test_engine, class_=AsyncSession)
    async with async_session() as session:
        yield session
        await session.rollback()  # Always rollback after test
```

## 📊 Test Metrics

### Coverage Targets

- **Overall Coverage**: ≥ 80%
- **Critical Paths**: ≥ 90%
- **New Code**: ≥ 95%

### Performance Targets

- **Unit Tests**: < 1 second per test
- **Integration Tests**: < 5 seconds per test
- **API Tests**: < 2 seconds per endpoint

## 🔄 Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: [3.13]
    
    steps:
    - uses: actions/checkout@v3
    - name: Set up Python
      uses: actions/setup-python@v3
      with:
        python-version: ${{ matrix.python-version }}
    
    - name: Install Poetry
      uses: snok/install-poetry@v1
    
    - name: Install dependencies
      run: poetry install --with dev
    
    - name: Run tests
      run: poetry run pytest --cov=app --cov-report=xml
    
    - name: Upload coverage
      uses: codecov/codecov-action@v3
```

## 📚 Best Practices

### Test Organization

1. **One test per behavior**: Each test should verify one specific behavior
2. **Descriptive names**: Test names should clearly describe what they test
3. **Arrange-Act-Assert**: Structure tests with clear sections
4. **Independent tests**: Tests should not depend on each other

### Test Data

1. **Use factories**: Generate realistic test data
2. **Minimal data**: Use only the data necessary for the test
3. **Isolated data**: Each test should use its own data
4. **Cleanup**: Always clean up test data

### Mocking

1. **Mock external dependencies**: Don't make real API calls in tests
2. **Mock at boundaries**: Mock external services, not internal logic
3. **Verify interactions**: Assert that mocks were called correctly
4. **Use AsyncMock**: For async methods, always use AsyncMock

### Error Testing

1. **Test error conditions**: Verify error handling works correctly
2. **Test edge cases**: Include boundary conditions and edge cases
3. **Test timeouts**: Verify timeout handling
4. **Test retries**: Verify retry logic works

## 🎉 Conclusion

This comprehensive test suite ensures the reliability and maintainability of the Chatico Mapper App. The combination of unit tests, integration tests, and comprehensive coverage reporting provides confidence in the application's functionality and helps catch issues early in the development process.

For questions or issues with testing, please refer to the pytest documentation or create an issue in the project repository.
