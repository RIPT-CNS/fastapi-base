"""Management commands.

python -m app.cli serve          # run the API (dev: hot reload, else WEB_CONCURRENCY workers)
python -m app.cli migrate        # alembic upgrade head + seed
python -m app.cli seed           # create FIRST_SUPERUSER_* if missing
python -m app.cli create-user --username bob --password 'Secret@123' --roles admin,user
"""

import argparse
import logging

import uvicorn
from alembic import command
from alembic.config import Config

from app.core.config import BASE_DIR, settings
from app.core.database import SessionLocal
from app.core.logging import setup_logging
from app.services.srv_user import UserService

logger = logging.getLogger("app.cli")


def serve() -> None:
    reload = settings.ENVIRONMENT == "dev"
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=reload,
        reload_dirs=["app"] if reload else None,
        workers=1 if reload else settings.WEB_CONCURRENCY,
        proxy_headers=True,
        forwarded_allow_ips="*",
        access_log=False,  # written by RequestContextMiddleware
        log_config=None,  # keep app.core.logging config
    )


def migrate() -> None:
    logger.info("Running migrations")
    command.upgrade(Config(str(BASE_DIR / "alembic.ini")), "head")
    setup_logging()  # alembic's fileConfig replaces the logging setup
    seed()


def seed() -> None:
    if not settings.FIRST_SUPERUSER_PASSWORD:
        logger.info("FIRST_SUPERUSER_PASSWORD not set: skip creating the first admin")
        return
    with SessionLocal() as db:
        user, created = UserService(db).ensure_superuser(
            settings.FIRST_SUPERUSER_USERNAME,
            settings.FIRST_SUPERUSER_EMAIL,
            settings.FIRST_SUPERUSER_PASSWORD,
        )
    logger.info("Superuser '%s' %s", user.username, "created" if created else "already exists")


def create_user(username: str, password: str, email: str | None, roles: list[str]) -> None:
    with SessionLocal() as db:
        user = UserService(db).create(
            {"username": username, "password": password, "email": email, "roles": roles}
        )
    logger.info("User '%s' created (id=%s, roles=%s)", user.username, user.id, user.roles)


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="run the API server")
    commands.add_parser("migrate", help="alembic upgrade head + seed")
    commands.add_parser("seed", help="create the first superuser")
    create = commands.add_parser("create-user", help="create a local user")
    create.add_argument("--username", required=True)
    create.add_argument("--password", required=True)
    create.add_argument("--email")
    create.add_argument("--roles", default=",".join(settings.DEFAULT_USER_ROLES))
    args = parser.parse_args()

    if args.command == "serve":
        serve()
    elif args.command == "migrate":
        migrate()
    elif args.command == "seed":
        seed()
    elif args.command == "create-user":
        roles = [role.strip() for role in args.roles.split(",") if role.strip()]
        create_user(args.username, args.password, args.email, roles)


if __name__ == "__main__":
    main()
