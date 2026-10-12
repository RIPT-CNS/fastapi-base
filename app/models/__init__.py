"""Every `model_*.py` module in this package is imported automatically,
so Alembic autogenerate sees new models without registering them anywhere."""

import importlib
import pkgutil

from app.models.model_base import BareBaseModel, Base, SoftDeleteMixin, TimestampMixin  # noqa: F401

for _module in pkgutil.iter_modules(__path__):
    if _module.name.startswith("model_"):
        importlib.import_module(f"{__name__}.{_module.name}")

from app.models.model_user import User  # noqa: E402, F401
