from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = "postgresql://postgres:Niraj%40242@localhost:5432/scm_db"

engine = create_engine(
    DATABASE_URL,
    echo=True  # shows SQL queries in terminal (good for learning/debug)
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()
