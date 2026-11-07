import os
import tempfile
from pathlib import Path

_test_dir = Path(tempfile.mkdtemp(prefix="pulsewatch-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_test_dir / 'test.db').as_posix()}"
os.environ["REDIS_URL"] = ""
os.environ["SCHEDULER_ENABLED"] = "false"
os.environ["SEED_DEMO"] = "false"
os.environ["AUTH_ENABLED"] = "false"
os.environ["RETENTION_DAYS"] = "30"

import pytest  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402

from app.database import Base, engine  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
async def client():
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http:
        yield http

    await engine.dispose()
