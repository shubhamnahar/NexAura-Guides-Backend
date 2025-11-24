# app/database.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# Replace with your actual PostgreSQL connection string
# Format: "postgresql://USER:PASSWORD@HOST:PORT/DATABASE_NAME"
# It's best to load this from environment variables
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:AndyLove%402022@localhost:5432/nexauraguides")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency to get DB session in routes
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()