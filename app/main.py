from contextlib import asynccontextmanager
from datetime import timezone
from pathlib import Path
from typing import Annotated

from elasticsearch import AsyncElasticsearch
from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import create_schema, engine, get_session, session_factory
from app.models import Document
from app.schemas import DocumentOut, DocumentsInput
from app.seed import seed_and_sync
from app.search import SearchIndex


@asynccontextmanager
async def lifespan(_: FastAPI):
    await create_schema()
    client = AsyncElasticsearch(settings.elasticsearch_url)
    search_index = SearchIndex(client, settings.elasticsearch_index)
    try:
        await search_index.ensure_index()
        async with session_factory() as session:
            seeded_count = await seed_and_sync(
                session,
                client,
                settings.elasticsearch_index,
                Path("data/posts.csv"),
            )
        print(f"Готово документов в поисковом индексе: {seeded_count}")
        app.state.search_index = search_index
        yield
    finally:
        await client.close()
        await engine.dispose()


app = FastAPI(
    title="Document Search API",
    description="Асинхронный полнотекстовый поиск документов с хранением в PostgreSQL и индексом Elasticsearch.",
    version="1.0.0",
    openapi_url="/docs.json",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", include_in_schema=False)
async def frontend() -> FileResponse:
    return FileResponse("app/static/index.html")


def get_search_index() -> SearchIndex:
    return app.state.search_index


@app.get("/health", tags=["service"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/documents", response_model=list[DocumentOut], status_code=status.HTTP_201_CREATED, tags=["documents"])
async def add_documents(
    payload: DocumentsInput,
    session: Annotated[AsyncSession, Depends(get_session)],
    search_index: Annotated[SearchIndex, Depends(get_search_index)],
) -> list[Document]:
    if not payload.documents:
        raise HTTPException(status_code=422, detail="Передайте хотя бы один документ")

    ids = [document.id for document in payload.documents]
    if len(ids) != len(set(ids)):
        raise HTTPException(status_code=422, detail="ID документов должны быть уникальными")

    rows = [Document(**document.model_dump()) for document in payload.documents]
    for row in rows:
        session.add(row)
    try:
        await session.commit()
    except Exception as exc:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Не удалось сохранить документы; проверьте уникальность ID") from exc

    for row in rows:
        created_date = row.created_date
        if created_date.tzinfo is None:
            created_date = created_date.replace(tzinfo=timezone.utc)
        await search_index.index_document(row.id, row.text, created_date.isoformat())
    return rows


@app.get("/documents", response_model=list[DocumentOut], tags=["documents"])
async def list_documents(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[Document]:
    result = await session.scalars(
        select(Document).order_by(Document.created_date.desc(), Document.id.asc()).limit(20)
    )
    return list(result.all())


@app.get("/documents/search", response_model=list[DocumentOut], tags=["documents"])
async def search_documents(
    q: Annotated[str, Query(min_length=1, description="Текстовый поисковый запрос")],
    session: Annotated[AsyncSession, Depends(get_session)],
    search_index: Annotated[SearchIndex, Depends(get_search_index)],
) -> list[Document]:
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="Поисковый запрос не должен быть пустым")

    ids = await search_index.search(query, limit=20)
    if not ids:
        return []
    result = await session.scalars(select(Document).where(Document.id.in_(ids)))
    by_id = {document.id: document for document in result.all()}
    return sorted(
        (by_id[document_id] for document_id in ids if document_id in by_id),
        key=lambda document: (document.created_date, -document.id),
        reverse=True,
    )


@app.delete("/documents/{document_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["documents"])
async def delete_document(
    document_id: int,
    session: Annotated[AsyncSession, Depends(get_session)],
    search_index: Annotated[SearchIndex, Depends(get_search_index)],
) -> Response:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Документ не найден")
    await session.delete(document)
    await session.commit()
    await search_index.delete_document(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
