import inspect

from asyncio import current_task
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, async_scoped_session

from core.config import settings


class DatabaseHelper:
    def __init__(self, url: str, echo: bool = False):
        self.engine = create_async_engine(
            url=url,
            echo=echo,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            autoflush=False,
            autocommit=False,
            expire_on_commit=False,
        )

    async def session_dependency(self) -> AsyncSession:  # type: ignore
        async with self.session_factory() as session:
            yield session

    async def scoped_session_dependency(self) -> AsyncSession:  # type: ignore
        scoped_session = self.get_scoped_session()
        session = scoped_session()
        try:
            yield session
        finally:
            await session.close()
            remove_result = scoped_session.remove()
            if inspect.isawaitable(remove_result):
                await remove_result

    def get_scoped_session(self):
        return async_scoped_session(
            session_factory=self.session_factory,
            scopefunc=current_task,
        )


db_helper = DatabaseHelper(
    url=settings.db.url,
    echo=settings.db.echo,
)
