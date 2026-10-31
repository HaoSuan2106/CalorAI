from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import settings

_url = make_url(settings.DATABASE_URL)
_is_sqlite = _url.get_backend_name() == "sqlite"


def _ensure_mysql_database() -> None:
    """Create the MySQL database on first run so the user only needs a running server."""
    if _url.get_backend_name() != "mysql" or not _url.database:
        return
    server_engine = create_engine(_url.set(database=""), pool_pre_ping=True)
    with server_engine.connect() as conn:
        conn.execute(text(
            f"CREATE DATABASE IF NOT EXISTS `{_url.database}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        ))
    server_engine.dispose()


engine = create_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"check_same_thread": False} if _is_sqlite else {},
)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)
    from .seed import seed_food_items

    _ensure_mysql_database()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_food_items(db)
