import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

def _build_url() -> str:
    url = os.getenv("DATABASE_URL")
    if url:
        return url
    host = os.getenv("MYSQLHOST", "localhost")
    user = os.getenv("MYSQLUSER", "root")
    pwd  = os.getenv("MYSQLPASSWORD", "")
    db   = os.getenv("MYSQLDATABASE", "smartschool_db")
    port = os.getenv("MYSQLPORT", "3306")
    return f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}"

engine = create_engine(_build_url(), pool_pre_ping=True, pool_recycle=3600)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()