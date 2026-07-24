from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore")


class Profile(_Base):
    id: int
    email: str
    name: str | None = None
    author_name: str | None = None
    key_prefix: str | None = None


class Model3D(_Base):
    id: int
    title: str
    description: str = ""
    category: str | None = None
    tags: list[str] = Field(default_factory=list)
    price_eur: float | None = None
    filename: str | None = None
    stored_name: str | None = None
    file_format: str | None = None
    file_size: int | None = None
    thumbnail: str | None = None
    uploader: str | None = None
    owner_id: int | None = None
    author: str | None = None
    published: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class Pack(_Base):
    id: int
    title: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    price_eur: float | None = None
    cover: str | None = None
    model_ids: list[int] = Field(default_factory=list)
    uploader: str | None = None
    owner_id: int | None = None
    author: str | None = None
    published: bool = False
    created_at: str | None = None
    updated_at: str | None = None


class GeneratedMeta(_Base):
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    category: str
    price_eur: float | None = None
    best_thumbnail_index: int = 0


class GeneratedPackMeta(_Base):
    title: str
    description: str
    tags: list[str] = Field(default_factory=list)
    price_eur: float | None = None
    best_cover_index: int = 0
