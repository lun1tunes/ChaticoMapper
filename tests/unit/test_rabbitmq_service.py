"""Unit tests for RabbitMQ service."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from aio_pika import Connection, Channel, Queue, Exchange, Message
from aio_pika.exceptions import AMQPException

from app.services import RabbitMQService
from app.config import Settings


@pytest.mark.unit
class TestRabbitMQService:
    """Test cases for RabbitMQService."""

    @pytest.fixture
    def settings(self):
        """Create test settings."""
        return Settings(
            rabbitmq_url="amqp://guest:guest@localhost:5672/",
            rabbitmq_exchange="test_exchange",
            rabbitmq_dead_letter_exchange="test_dlx",
            rabbitmq_message_ttl=86400,
            rabbitmq_max_retries=5,
        )

    @pytest.fixture
    def rabbitmq_service(self):
        """Create RabbitMQService instance."""
        return RabbitMQService()

    @pytest.fixture
    def mock_connection(self):
        """Create mock connection."""
        mock_conn = AsyncMock(spec=Connection)
        mock_channel = AsyncMock(spec=Channel)
        mock_queue = AsyncMock(spec=Queue)
        mock_exchange = AsyncMock(spec=Exchange)

        mock_conn.channel.return_value = mock_channel
        mock_channel.declare_queue.return_value = mock_queue
        mock_channel.declare_exchange.return_value = mock_exchange
        mock_queue.bind.return_value = None

        return mock_conn

    @pytest.mark.asyncio
    async def test_connect_success(self, rabbitmq_service, mock_connection):
        """Test successful connection."""
        with patch("aio_pika.connect_robust", return_value=mock_connection):
            await rabbitmq_service.connect()

            assert rabbitmq_service.connection is not None
            assert rabbitmq_service.channel is not None

    @pytest.mark.asyncio
    async def test_connect_failure(self, rabbitmq_service):
        """Test connection failure."""
        with patch(
            "aio_pika.connect_robust", side_effect=AMQPException("Connection failed")
        ):
            with pytest.raises(AMQPException):
                await rabbitmq_service.connect()

    @pytest.mark.asyncio
    async def test_disconnect_success(self, rabbitmq_service, mock_connection):
        """Test successful disconnection."""
        rabbitmq_service.connection = mock_connection

        await rabbitmq_service.disconnect()

        mock_connection.close.assert_called_once()
        assert rabbitmq_service.connection is None
        assert rabbitmq_service.channel is None

    @pytest.mark.asyncio
    async def test_disconnect_no_connection(self, rabbitmq_service):
        """Test disconnection with no connection."""
        # Should not raise an exception
        await rabbitmq_service.disconnect()

    @pytest.mark.asyncio
    async def test_create_queue_success(self, rabbitmq_service, mock_connection):
        """Test successful queue creation."""
        rabbitmq_service.connection = mock_connection
        rabbitmq_service.channel = mock_connection.channel.return_value

        result = await rabbitmq_service.create_queue("test_queue")

        assert result is True
        rabbitmq_service.channel.declare_queue.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_queue_no_connection(self, rabbitmq_service):
        """Test queue creation with no connection."""
        with pytest.raises(RuntimeError, match="Not connected to RabbitMQ"):
            await rabbitmq_service.create_queue("test_queue")

    @pytest.mark.asyncio
    async def test_publish_message_success(self, rabbitmq_service, mock_connection):
        """Test successful message publishing."""
        rabbitmq_service.connection = mock_connection
        rabbitmq_service.channel = mock_connection.channel.return_value

        message_data = {"test": "data"}
        queue_name = "test_queue"

        result = await rabbitmq_service.publish_message(message_data, queue_name)

        assert result is True
        rabbitmq_service.channel.default_exchange.publish.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_message_no_connection(self, rabbitmq_service):
        """Test message publishing with no connection."""
        message_data = {"test": "data"}
        queue_name = "test_queue"

        with pytest.raises(RuntimeError, match="Not connected to RabbitMQ"):
            await rabbitmq_service.publish_message(message_data, queue_name)

    @pytest.mark.asyncio
    async def test_publish_message_with_retry(self, rabbitmq_service, mock_connection):
        """Test message publishing with retry logic."""
        rabbitmq_service.connection = mock_connection
        rabbitmq_service.channel = mock_connection.channel.return_value

        # Mock publish to fail first time, succeed second time
        mock_publish = rabbitmq_service.channel.default_exchange.publish
        mock_publish.side_effect = [AMQPException("Publish failed"), None]

        message_data = {"test": "data"}
        queue_name = "test_queue"

        result = await rabbitmq_service.publish_message(message_data, queue_name)

        assert result is True
        assert mock_publish.call_count == 2

    @pytest.mark.asyncio
    async def test_publish_message_max_retries_exceeded(
        self, rabbitmq_service, mock_connection
    ):
        """Test message publishing with max retries exceeded."""
        rabbitmq_service.connection = mock_connection
        rabbitmq_service.channel = mock_connection.channel.return_value

        # Mock publish to always fail
        mock_publish = rabbitmq_service.channel.default_exchange.publish
        mock_publish.side_effect = AMQPException("Publish failed")

        message_data = {"test": "data"}
        queue_name = "test_queue"

        with pytest.raises(AMQPException):
            await rabbitmq_service.publish_message(message_data, queue_name)

        # Should retry max_retries + 1 times
        assert mock_publish.call_count == rabbitmq_service.max_retries + 1

    @pytest.mark.asyncio
    async def test_get_queue_info_success(self, rabbitmq_service, mock_connection):
        """Test successful queue info retrieval."""
        rabbitmq_service.connection = mock_connection
        rabbitmq_service.channel = mock_connection.channel.return_value

        mock_queue = AsyncMock()
        mock_queue.method.message_count = 10
        mock_queue.method.consumer_count = 2
        rabbitmq_service.channel.declare_queue.return_value = mock_queue

        result = await rabbitmq_service.get_queue_info("test_queue")

        expected = {
            "message_count": 10,
            "consumer_count": 2,
            "state": "running",
        }
        assert result == expected

    @pytest.mark.asyncio
    async def test_get_queue_info_no_connection(self, rabbitmq_service):
        """Test queue info retrieval with no connection."""
        with pytest.raises(RuntimeError, match="Not connected to RabbitMQ"):
            await rabbitmq_service.get_queue_info("test_queue")

    @pytest.mark.asyncio
    async def test_create_dead_letter_exchange(self, rabbitmq_service, mock_connection):
        """Test dead letter exchange creation."""
        rabbitmq_service.connection = mock_connection
        rabbitmq_service.channel = mock_connection.channel.return_value

        await rabbitmq_service._create_dead_letter_exchange()

        rabbitmq_service.channel.declare_exchange.assert_called_once()

    @pytest.mark.asyncio
    async def test_is_connected_true(self, rabbitmq_service, mock_connection):
        """Test connection status when connected."""
        rabbitmq_service.connection = mock_connection
        mock_connection.is_closed = False

        assert rabbitmq_service.is_connected() is True

    @pytest.mark.asyncio
    async def test_is_connected_false(self, rabbitmq_service):
        """Test connection status when not connected."""
        assert rabbitmq_service.is_connected() is False

    @pytest.mark.asyncio
    async def test_is_connected_closed(self, rabbitmq_service, mock_connection):
        """Test connection status when connection is closed."""
        rabbitmq_service.connection = mock_connection
        mock_connection.is_closed = True

        assert rabbitmq_service.is_connected() is False
