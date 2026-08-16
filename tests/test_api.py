from collections.abc import AsyncIterator

from fastapi.testclient import TestClient

from backend.db.session import get_db_session
from backend.main import create_app


class StubSession:
    def __init__(self) -> None:
        self.executed_statement = ""

    async def execute(self, statement: object) -> None:
        self.executed_statement = str(statement)


def test_health_checks_database_without_real_postgres() -> None:
    app = create_app()
    session = StubSession()

    async def override_session() -> AsyncIterator[StubSession]:
        yield session

    app.dependency_overrides[get_db_session] = override_session

    with TestClient(app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "reachable"}
    assert session.executed_statement == "SELECT 1"


def test_local_frontend_origin_is_allowed_by_cors() -> None:
    app = create_app()

    with TestClient(app) as client:
        response = client.options(
            "/api/v1/projects",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:3000"
    )
