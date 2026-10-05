import argparse
import asyncio
from pathlib import Path

from sqlalchemy import select

from app.database import create_schema, engine, session_factory
from app.models import Document
from app.search import create_search_index
from app.seed import read_documents, sync_search_index


async def import_documents(path: Path) -> None:
    documents = read_documents(path)
    await create_schema()
    async with session_factory() as session:
        stored_documents = {document.id: document for document in (await session.scalars(select(Document))).all()}
        fresh = []
        for document in documents:
            stored = stored_documents.get(document.id)
            if stored is None:
                fresh.append(document)
                continue
            stored.rubrics = document.rubrics
            stored.text = document.text
            stored.created_date = document.created_date
        session.add_all(fresh)
        await session.commit()

    index = await create_search_index()
    try:
        await index.ensure_index()
        await sync_search_index(index.client, index.index_name, documents)
    finally:
        await index.client.close()
        await engine.dispose()
    print(f"Проиндексировано документов: {len(documents)}; новых записей в БД: {len(fresh)}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Импорт документов из CSV в PostgreSQL и Elasticsearch")
    parser.add_argument("csv_file", type=Path)
    args = parser.parse_args()
    asyncio.run(import_documents(args.csv_file))


if __name__ == "__main__":
    main()
