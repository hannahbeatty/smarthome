from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, scoped_session
from model.db import Base

# Change this URL to your actual database configuration
# For SQLite (good for local/demo use):
DATABASE_URL = "sqlite:///smart_home.db"

# Create engine with thread safety settings
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Allow SQLite to be used from multiple threads
    echo=True,
    # Add connection pooling parameters
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800  # Recycle connections after 30 minutes
)

# Configure SQLite for better concurrent access
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")  # Write-Ahead Logging for better concurrency
    cursor.execute("PRAGMA synchronous=NORMAL")  # Slightly faster at minimal risk
    cursor.close()

# Scoped session for thread-safe use
SessionLocal = scoped_session(sessionmaker(bind=engine))

# Call this once at application startup to ensure all tables exist
def init_db():
    Base.metadata.create_all(bind=engine)

# Example usage (call this from main app):
# from db.setup import init_db, SessionLocal
# init_db()
# session = SessionLocal()