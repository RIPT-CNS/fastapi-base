# Import all the models, so that Base has them before being
# imported by Alembic
from app.models.model_base import Base  # noqa
from app.models.model_user import User  # noqa
from app.models.model_thread import Thread  # noqa
from app.models.model_message import Message  # noqa
from app.models.model_document import Document  # noqa
from app.models.model_vector_session import VectorSession  # noqa
from app.models.model_feedback import Feedback  # noqa

