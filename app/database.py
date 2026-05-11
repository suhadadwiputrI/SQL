from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os

# ═══════════════════════════════════════════════════════════════════════════
# database.py
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "mysql+pymysql://root:12345678@localhost:3306/smartschool_db"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,        # reconnect otomatis jika koneksi putus
    pool_recycle=3600,         # recycle koneksi tiap 1 jam
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    """Dependency FastAPI — yield db session, tutup setelah request selesai."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()