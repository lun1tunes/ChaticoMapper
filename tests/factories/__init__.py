"""Factory classes for generating test data."""

import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from factory import Factory, Faker, LazyFunction, SubFactory
from factory.alchemy import SQLAlchemyModelFactory

from app.models import WorkerApp, WebhookLog


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
    created_at = LazyFunction(lambda: datetime.now(timezone.utc))
    updated_at = LazyFunction(lambda: datetime.now(timezone.utc))


class WebhookLogFactory(SQLAlchemyModelFactory):
    """Factory for creating WebhookLog instances."""

    class Meta:
        model = WebhookLog
        sqlalchemy_session_persistence = "commit"

    id = LazyFunction(lambda: str(uuid.uuid4()))
    webhook_id = LazyFunction(lambda: str(uuid.uuid4()))
    owner_id = Faker("user_name")
    worker_app_id = LazyFunction(lambda: str(uuid.uuid4()))
    target_app_name = Faker("company")
    processing_status = Faker(
        "random_element", elements=["success", "failed", "routed"]
    )
    error_message = Faker("sentence")
    processing_time_ms = Faker("random_int", min=10, max=1000)
    created_at = LazyFunction(lambda: datetime.now(timezone.utc))


class WebhookPayloadFactory(Factory):
    """Factory for creating webhook payload data."""

    class Meta:
        model = dict

    object = "instagram"
    entry = LazyFunction(
        lambda: [
            {
                "id": str(uuid.uuid4()),
                "time": int(datetime.now(timezone.utc).timestamp()),
                "changes": [
                    {
                        "field": "comments",
                        "value": {
                            "id": str(uuid.uuid4()),
                            "text": Faker("sentence").generate(),
                            "media_id": str(uuid.uuid4()),
                            "from": {
                                "id": str(uuid.uuid4()),
                                "username": Faker("user_name").generate(),
                            },
                            "created_time": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                ],
            }
        ]
    )


class InstagramMediaInfoFactory(Factory):
    """Factory for creating Instagram media info data."""

    class Meta:
        model = dict

    id = LazyFunction(lambda: str(uuid.uuid4()))
    owner = {
        "id": LazyFunction(lambda: str(uuid.uuid4())),
    }
    media_type = Faker("random_element", elements=["IMAGE", "VIDEO", "CAROUSEL_ALBUM"])
    media_url = Faker("url")
    timestamp = LazyFunction(lambda: datetime.now(timezone.utc).isoformat())


class RoutingRequestFactory(Factory):
    """Factory for creating routing request data."""

    class Meta:
        model = dict

    webhook_payload = SubFactory(WebhookPayloadFactory)
    owner_id = LazyFunction(lambda: str(uuid.uuid4()))
    target_app_url = Faker("url")
    target_queue_name = Faker("word")


class RoutingResponseFactory(Factory):
    """Factory for creating routing response data."""

    class Meta:
        model = dict

    status = Faker("random_element", elements=["success", "failed", "error"])
    message = Faker("sentence")
    routed_to = Faker("word")
    processing_time_ms = Faker("random_int", min=10, max=1000)
    error_details = None


class WorkerAppCreateFactory(Factory):
    """Factory for creating worker app creation data."""

    class Meta:
        model = dict

    owner_id = LazyFunction(lambda: str(uuid.uuid4()))
    app_name = Faker("company")
    base_url = Faker("url")
    webhook_path = "/webhook"
    queue_name = Faker("word")
    is_active = True


class WorkerAppUpdateFactory(Factory):
    """Factory for creating worker app update data."""

    class Meta:
        model = dict

    app_name = Faker("company")
    base_url = Faker("url")
    webhook_path = "/webhook"
    queue_name = Faker("word")
    is_active = True


class HealthResponseFactory(Factory):
    """Factory for creating health response data."""

    class Meta:
        model = dict

    status = Faker("random_element", elements=["healthy", "unhealthy"])
    timestamp = LazyFunction(lambda: datetime.now(timezone.utc).isoformat())
    services = {
        "database": "healthy",
        "rabbitmq": "healthy",
        "redis": "healthy",
    }


class MetricsResponseFactory(Factory):
    """Factory for creating metrics response data."""

    class Meta:
        model = dict

    webhook_total = Faker("random_int", min=0, max=10000)
    webhook_success = Faker("random_int", min=0, max=10000)
    webhook_failed = Faker("random_int", min=0, max=1000)
    webhook_routed = Faker("random_int", min=0, max=10000)
    worker_apps_total = Faker("random_int", min=0, max=100)
    worker_apps_active = Faker("random_int", min=0, max=100)
    rabbitmq_queues = {
        "test_queue": {
            "message_count": Faker("random_int", min=0, max=1000),
            "consumer_count": Faker("random_int", min=0, max=10),
        }
    }
