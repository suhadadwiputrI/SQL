from sqlalchemy import (
    Boolean, Column, ForeignKey, Integer, String,
    Enum, TIMESTAMP
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


# ─── Enums ────────────────────────────────────────────────────────────────────

class RoleEnum(str, enum.Enum):
    admin = "admin"
    guru = "guru"
    wali_siswa = "wali_siswa"
    kepala_sekolah = "kepala_sekolah"


# ─── Tabel Akun ───────────────────────────────────────────────────────────────

class Akun(Base):
    __tablename__ = "akun"

    id_akun         = Column(Integer, primary_key=True, index=True)
    username        = Column(String(100), unique=True, index=True, nullable=False)
    password        = Column(String(255), nullable=False)
    nama            = Column(String(100), nullable=False)
    role            = Column(Enum(RoleEnum), default=RoleEnum.admin, nullable=False)
    first_login     = Column(Boolean, default=True)
    created_at      = Column(TIMESTAMP, server_default=func.now())
    updated_at      = Column(TIMESTAMP, onupdate=func.now())

    # Relationships
    admin          = relationship("Admin", back_populates="akun", uselist=False)
    reset_password = relationship("ResetPassword", back_populates="akun")

    def __repr__(self):
        return f"<Akun id={self.id_akun} username={self.username}>"


# ─── Tabel Admin ──────────────────────────────────────────────────────────────

class Admin(Base):
    __tablename__ = "admin"

    id_admin = Column(Integer, primary_key=True, index=True)
    id_akun  = Column(Integer, ForeignKey("akun.id_akun"), nullable=False)

    # Relationships
    akun = relationship("Akun", back_populates="admin")

    def __repr__(self):
        return f"<Admin id={self.id_admin}>"


# ─── Tabel Reset Password ─────────────────────────────────────────────────────

class ResetPassword(Base):
    __tablename__ = "reset_password"

    id_pertanyaan  = Column(Integer, primary_key=True, index=True)
    id_akun        = Column(Integer, ForeignKey("akun.id_akun"), nullable=False)
    isi_pertanyaan = Column(String(50), nullable=False)
    jawaban        = Column(String(50), nullable=False)

    # Relationships
    akun = relationship("Akun", back_populates="reset_password")

    def __repr__(self):
        return f"<ResetPassword id={self.id_pertanyaan}>"