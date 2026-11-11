"""Only PostgreSQL URLs are accepted; credentials never enter run reports."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url


def create_database_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.get_backend_name() != "postgresql":
        raise ValueError("PostgreSQL export requires a postgresql:// database URL")
    url = url.set(drivername="postgresql+psycopg")
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10})
