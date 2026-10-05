import csv
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import get_session
from app.main import app, get_search_index
from app.models import Base, Document
from app.seed import read_documents, seed_and_sync
from scripts.import_csv import read_documents as read_documents_from_cli


class FakeSearchIndex:
    def __init__(self, ids: list[int] | None = None) -> None:
        self.ids = ids or []
        self.deleted: list[int] = []
        self.indexed: list[int] = []

    async def search(self, query: str, limit: int = 20) -> list[int]:
        assert query
        assert limit == 20
        return self.ids[:limit]

    async def delete_document(self, document_id: int) -> None:
        self.deleted.append(document_id)

    async def index_document(self, document_id: int, text: str, created_date: str) -> None:
        self.indexed.append(document_id)


@pytest_asyncio.fixture
async def client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'test.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    index = FakeSearchIndex([2, 1, 3])

    async def override_session():
        async with session_factory() as session:
            yield session

    async def override_schema():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    await override_schema()
    async with session_factory() as session:
        session.add_all(
            [
                Document(id=1, rubrics=["a"], text="hello", created_date=datetime(2024, 1, 1, tzinfo=timezone.utc)),
                Document(id=2, rubrics=["b"], text="hello newer", created_date=datetime(2024, 2, 1, tzinfo=timezone.utc)),
                Document(id=3, rubrics=["c"], text="hello", created_date=datetime(2024, 3, 1, tzinfo=timezone.utc)),
            ]
        )
        await session.commit()
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_search_index] = lambda: index
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as test_client:
        yield test_client, index, session_factory
    app.dependency_overrides.clear()
    await engine.dispose()


@pytest.mark.asyncio
async def test_search_returns_full_documents_in_date_order(client):
    test_client, _, _ = client
    response = await test_client.get("/documents/search", params={"q": "hello"})

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [3, 2, 1]
    assert set(response.json()[0]) == {"id", "rubrics", "text", "created_date"}


@pytest.mark.asyncio
async def test_list_returns_latest_documents_without_search_query(client):
    test_client, _, _ = client
    response = await test_client.get("/documents")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [3, 2, 1]


@pytest.mark.asyncio
async def test_delete_removes_document_from_database_and_index(client):
    test_client, index, session_factory = client
    response = await test_client.delete("/documents/2")

    assert response.status_code == 204
    assert index.deleted == [2]

    async def check_missing():
        async with session_factory() as session:
            return await session.scalar(select(Document).where(Document.id == 2))

    assert await check_missing() is None


@pytest.mark.asyncio
async def test_search_rejects_blank_query(client):
    test_client, _, _ = client

    response = await test_client.get("/documents/search", params={"q": " "})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_openapi_is_served_at_requested_path(client):
    test_client, _, _ = client

    response = await test_client.get("/docs.json")
    assert response.status_code == 200
    assert "/documents/search" in response.json()["paths"]


@pytest.mark.asyncio
async def test_add_documents_persists_and_indexes_documents(client):
    test_client, index, session_factory = client
    response = await test_client.post(
        "/documents",
        json={
            "documents": [
                {
                    "id": 4,
                    "rubrics": ["python"],
                    "text": "An async document",
                    "created_date": "2025-01-02T03:04:05Z",
                }
            ]
        },
    )

    assert response.status_code == 201
    assert response.json()[0]["id"] == 4
    assert index.indexed == [4]
    async with session_factory() as session:
        assert await session.get(Document, 4) is not None


def test_csv_import_parses_document_fields(tmp_path):
    csv_file = tmp_path / "documents.csv"
    with csv_file.open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=["rubrics", "text", "created_date"])
        writer.writeheader()
        writer.writerow(
            {
                "rubrics": "['news', 'tech']",
                "text": "Python async service",
                "created_date": "2025-01-02T03:04:05Z",
            }
        )

    [document] = read_documents(csv_file)

    assert document.id == 1
    assert document.rubrics == ["news", "tech"]
    assert document.text == "Python async service"
    assert document.created_date.utcoffset().total_seconds() == 0


def test_assignment_csv_contains_1500_documents_with_generated_ids():
    from pathlib import Path

    dataset = Path(__file__).parents[1] / "data" / "posts.csv"
    documents = read_documents(dataset)

    assert len(documents) == 1500
    assert documents[0].id == 1
    assert documents[-1].id == 1500
    assert all(document.text and isinstance(document.rubrics, list) for document in documents)


@pytest.mark.asyncio
async def test_seed_runs_only_for_empty_database_and_syncs_existing_rows(tmp_path, monkeypatch):
    from app import seed

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'seed.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    csv_file = tmp_path / "documents.csv"
    csv_file.write_text(
        "text,created_date,rubrics\nseeded,2025-01-02T03:04:05Z,news\n",
        encoding="utf-8",
    )
    indexed: list[list[int]] = []

    async def capture_sync(_client, _index_name, documents):
        indexed.append([document.id for document in documents])

    monkeypatch.setattr(seed, "sync_search_index", capture_sync)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        assert await seed_and_sync(session, object(), "documents", csv_file) == 1
        assert indexed[-1] == [1]
        await session.delete(await session.get(Document, 1))
        await session.commit()
        assert await seed_and_sync(session, object(), "documents", csv_file) == 0
        assert indexed[-1] == []

    await engine.dispose()


def test_cli_and_startup_share_csv_parser(tmp_path):
    csv_file = tmp_path / "documents.csv"
    csv_file.write_text(
        "text,created_date,rubrics\nshared,2025-01-02T03:04:05Z,news\n",
        encoding="utf-8",
    )

    assert read_documents_from_cli(csv_file)[0].text == read_documents(csv_file)[0].text
