import os
import re
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker


def _fix_database_url(url: str) -> str:
    """
    Membersihkan DATABASE_URL dari Railway agar kompatibel dengan SQLAlchemy:
    1. Ganti mysql:// → mysql+pymysql://
    2. Hapus port kosong (host:/dbname → host/dbname)
    3. Hapus port kosong di akhir host (host: → host)
    """
    # Fix dialect
    if url.startswith("mysql://"):
        url = url.replace("mysql://", "mysql+pymysql://", 1)

    # Hapus port kosong — pola: @host:/dbname atau @host:
    # Contoh: @roundhouse.proxy.rlwy.net:/railway → @roundhouse.proxy.rlwy.net/railway
    url = re.sub(r'(@[^:/]+):(/)' , r'\1\2', url)  # @host:/db → @host/db
    url = re.sub(r'(@[^:/]+):$',    r'\1',   url)  # @host:    → @host

    return url


DATABASE_URL = _fix_database_url(
    os.getenv(
        "DATABASE_URL",
        "mysql+pymysql://root:password@localhost:3306/fastapi_db"
    )
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,   # Cek koneksi sebelum digunakan
    pool_recycle=300,     # Recycle koneksi setiap 5 menit
    pool_size=10,
    max_overflow=20,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()