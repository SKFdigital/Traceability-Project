import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

# 1. Correctly read the variable from Render's environment settings
DATABASE_URL = os.getenv("DATABASE_URL")

# 2. Safety check: crash early if Render isn't configured yet
if not DATABASE_URL:
    raise Exception("DATABASE_URL not set")

# 3. Handle SQLAlchemy's requirement for "postgresql://" instead of "postgres://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# 4. Create the engine with the safe URL
engine = create_engine(
    DATABASE_URL,
    echo=True  # useful for debugging logs on Render
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()

# 5. Add this function so that traceability_backend.py can import it
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
