from sqlalchemy import Column, Integer, String
from database import Base

class Siswa(Base):
    __tablename__ = "siswa"

    id = Column(Integer, primary_key=True, index=True)
    nama = Column(String(100))
    kelas = Column(String(20))