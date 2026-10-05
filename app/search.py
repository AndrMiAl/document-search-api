from elasticsearch import AsyncElasticsearch

from app.config import settings


class SearchIndex:
    def __init__(self, client: AsyncElasticsearch, index_name: str) -> None:
        self.client = client
        self.index_name = index_name

    async def ensure_index(self) -> None:
        if await self.client.indices.exists(index=self.index_name):
            return
        await self.client.indices.create(
            index=self.index_name,
            mappings={
                "properties": {
                    "id": {"type": "long"},
                    "text": {"type": "text"},
                    "created_date": {"type": "date"},
                }
            },
        )

    async def index_document(self, document_id: int, text: str, created_date: str) -> None:
        await self.client.index(
            index=self.index_name,
            id=str(document_id),
            document={"id": document_id, "text": text, "created_date": created_date},
            refresh="wait_for",
        )

    async def search(self, query: str, limit: int = 20) -> list[int]:
        response = await self.client.search(
            index=self.index_name,
            query={"match": {"text": {"query": query}}},
            size=limit,
            sort=[{"created_date": {"order": "desc", "unmapped_type": "date"}}, {"id": "asc"}],
        )
        return [int(hit["_id"]) for hit in response["hits"]["hits"]]

    async def delete_document(self, document_id: int) -> None:
        await self.client.delete(index=self.index_name, id=str(document_id), ignore=[404], refresh=True)


async def create_search_index() -> SearchIndex:
    client = AsyncElasticsearch(settings.elasticsearch_url)
    return SearchIndex(client, settings.elasticsearch_index)
