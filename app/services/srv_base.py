from typing import Generic, TypeVar, Type, Any, Optional, List, Tuple
from fastapi.encoders import jsonable_encoder
from fastapi_sqlalchemy import db
from app.models.model_base import BareBaseModel
from app.utils.exception_handler import CustomException, ExceptionType
from app.schemas.sche_base import PaginationParams, SortParams
from app.utils.paging import paginate
from app.schemas.sche_response import MetadataResponse


ModelType = TypeVar("ModelType", bound=BareBaseModel)


class BaseService(Generic[ModelType], object):

    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get_by_id(self, id: int) -> ModelType:
        obj = db.session.query(self.model).get(id)
        if obj is None:
            raise CustomException(exception=ExceptionType.NOT_FOUND)
        return obj

    def get_by_id_optional(self, id: int) -> Optional[ModelType]:
        obj = db.session.query(self.model).get(id)
        return obj

    def get_all(
        self, sort_params: Optional[SortParams] = SortParams()
    ) -> Tuple[List[ModelType], MetadataResponse]:
        query = db.session.query(self.model)
        return paginate(
            model=self.model,
            query=query,
            pagination_params=None,
            sort_params=sort_params,
        )

    def get_by_filter(
        self,
        pagination_params: Optional[PaginationParams] = PaginationParams(),
        sort_params: Optional[SortParams] = SortParams(),
    ) -> Tuple[List[ModelType], MetadataResponse]:
        query = db.session.query(self.model)
        return paginate(
            model=self.model,
            query=query,
            pagination_params=pagination_params,
            sort_params=sort_params,
        )

    def create(self, data: dict[str, Any]) -> ModelType:
        obj_data = jsonable_encoder(data)
        obj = self.model(**obj_data)
        db.session.add(obj)
        db.session.commit()
        db.session.refresh(obj)
        return obj

    def update_by_id(self, id: int, data: dict[str, Any]) -> ModelType:
        obj_data = jsonable_encoder(data)
        exist_obj = self.get_by_id(id)
        for field in obj_data:
            setattr(exist_obj, field, obj_data[field])
        db.session.commit()
        db.session.refresh(exist_obj)
        return exist_obj

    def partial_update_by_id(self, id: int, data: dict[str, Any]) -> ModelType:
        obj_data = jsonable_encoder(data)
        exist_obj = self.get_by_id(id)
        for field in obj_data:
            if hasattr(exist_obj, field) and obj_data[field] is not None:
                if isinstance(getattr(exist_obj, field), list) and not obj_data[field]:
                    setattr(exist_obj, field, [])
                else:
                    setattr(exist_obj, field, obj_data[field])
        db.session.commit()
        db.session.refresh(exist_obj)
        return exist_obj

    def delete_by_id(self, id: int) -> None:
        obj = self.get_by_id(id)
        db.session.delete(obj)
        db.session.commit()
