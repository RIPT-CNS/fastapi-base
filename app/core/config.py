import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from typing import List

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../"))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Settings(BaseSettings):
    PROJECT_NAME: str = os.getenv("PROJECT_NAME", "FASTAPI_BASE")
    SECRET_KEY: str = os.getenv("SECRET_KEY", None)
    API_PREFIX: str = os.getenv("API_PREFIX", "/api")
    API_VERSIONS: str = os.getenv("API_VERSIONS", "")
    API_VERSION: str = os.getenv("API_VERSION", "v1")
    BACKEND_CORS_ORIGINS: str = os.getenv("BACKEND_CORS_ORIGINS", '["*"]')
    DATABASE_URL: str = os.getenv("SQL_DATABASE_URL", None)
    ACCESS_TOKEN_EXPIRE_SECONDS: int = 60 * 60 * 24 * 7  # Token expired after 7 days
    SECURITY_ALGORITHM: str = "HS256"
    LOGGING_CONFIG_FILE: str = os.path.join(BASE_DIR, "logging.ini")
    DEBUG: bool = os.getenv("DEBUG", "False").lower() == "true"


settings = Settings()
