import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from keycloak.keycloak_openid import KeycloakOpenID


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
    KEYCLOAK_SERVER_URL: str = os.getenv("KEYCLOAK_SERVER_URL", None)
    KEYCLOAK_REALM: str = os.getenv("KEYCLOAK_REALM", None)
    KEYCLOAK_CLIENT_ID: str = os.getenv("KEYCLOAK_CLIENT_ID", None)
    KEYCLOAK_CLIENT_SECRET: str = os.getenv("KEYCLOAK_CLIENT_SECRET", None)
    KEYCLOAK_VERIFY: bool = os.getenv("KEYCLOAK_VERIFY", "False").lower() == "true"


settings = Settings()

if (
    settings.KEYCLOAK_SERVER_URL != None
    and settings.KEYCLOAK_REALM != None
    and settings.KEYCLOAK_CLIENT_ID != None
    and settings.KEYCLOAK_CLIENT_SECRET != None
    and settings.KEYCLOAK_VERIFY != None
):
    keycloak_openid = KeycloakOpenID(
        server_url=settings.KEYCLOAK_SERVER_URL,
        realm_name=settings.KEYCLOAK_REALM,
        client_id=settings.KEYCLOAK_CLIENT_ID,
        client_secret_key=settings.KEYCLOAK_CLIENT_SECRET,
        verify=settings.KEYCLOAK_VERIFY,
    )
else:
    keycloak_openid = None


def get_openid_config():
    if keycloak_openid == None:
        return {}
    return keycloak_openid.well_known()
