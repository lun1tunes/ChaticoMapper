from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy models."""

    __abstract__ = True

    # Type annotation registry for Pydantic v2 compatibility
    type_annotation_map: dict[type, Any] = {}
