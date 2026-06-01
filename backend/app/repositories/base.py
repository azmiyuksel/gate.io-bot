from typing import Generic, TypeVar

from sqlalchemy.orm import Session

ModelT = TypeVar("ModelT")


class Repository(Generic[ModelT]):
    def __init__(self, db: Session, model: type[ModelT]) -> None:
        self.db = db
        self.model = model

    def get(self, item_id: int) -> ModelT | None:
        return self.db.get(self.model, item_id)

    def add(self, entity: ModelT) -> ModelT:
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity

    def list(self, limit: int = 100) -> list[ModelT]:
        return list(self.db.query(self.model).limit(limit))
