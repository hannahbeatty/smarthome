from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from model.db import Base

# Change this URL to your actual database configuration
# For SQLite (good for local/demo use):
DATABASE_URL = "sqlite:///smart_home.db"

# Create engine
engine = create_engine(DATABASE_URL, echo=True)

# Scoped session for thread-safe use
SessionLocal = scoped_session(sessionmaker(bind=engine))

# Call this once at application startup to ensure all tables exist
def init_db():
    Base.metadata.create_all(bind=engine)

# Example usage (call this from main app):
# from db.setup import init_db, SessionLocal
# init_db()
# session = SessionLocal()
