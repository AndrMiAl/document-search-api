import ast
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from elasticsearch.helpers import async_bulk
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, SeedState

SEED_KEY = "assignment_csv_v1"


def read_documents(path: Path) -> list[Document]:
    documents = []
    with path.open("r", encoding="utf-8-sig", newline="") as source:
        for row_number, row in enumerate(csv.DictReader(source), start=2):
            try:
                raw_rubrics = (row.get("rubrics") or "").strip()
                rubrics = ast.literal_eval(raw_rubrics) if raw_rubrics.startswith("[") else [raw_rubrics]
                if not isinstance(rubrics, list):
                    rubrics = [str(rubrics)]
                created_date = datetime.fromisoformat(row["created_date"].replace("Z", "+00:00"))
                documents.append(
                    Document(
                        id=int(row["id"]) if row.get("id") else row_number - 1,
                        rubrics=rubrics,
                        text=row["text"],
                        created_date=created_date,
                    )
                )
            except (KeyError, ValueError, TypeError, SyntaxError) as exc:
                raise ValueError(f"Некорректная строка CSV {row_number}: {exc}") from exc
    return documents


def index_action(index_name: str, document: Document) -> dict[str, Any]:
    created_date = document.created_date
    if created_date.tzinfo is None:
        created_date = created_date.replace(tzinfo=timezone.utc)
    return {
        "_op_type": "index",
        "_index": index_name,
        "_id": str(document.id),
        "_source": {
            "id": document.id,
            "text": document.text,
            "created_date": created_date.isoformat(),
        },
    }


async def sync_search_index(client: Any, index_name: str, documents: list[Document]) -> None:
    if documents:
        await async_bulk(
            client,
            (index_action(index_name, document) for document in documents),
            chunk_size=250,
            refresh="wait_for",
        )


async def seed_and_sync(session: AsyncSession, client: Any, index_name: str, csv_path: Path) -> int:
    seeded = await session.get(SeedState, SEED_KEY)
    if seeded is None:
        has_documents = await session.scalar(select(Document.id).limit(1))
        if has_documents is None:
            session.add_all(read_documents(csv_path))
        session.add(SeedState(key=SEED_KEY))
        await session.commit()

    documents = list((await session.scalars(select(Document))).all())
    await sync_search_index(client, index_name, documents)
    return len(documents)
