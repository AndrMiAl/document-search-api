from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentInput(BaseModel):
    id: int
    rubrics: list[str] = Field(default_factory=list)
    text: str
    created_date: datetime


class DocumentOut(DocumentInput):
    model_config = ConfigDict(from_attributes=True)


class DocumentsInput(BaseModel):
    documents: list[DocumentInput]
