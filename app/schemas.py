from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime
from enum import Enum


# ─── Token ────────────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    id_akun: Optional[int] = None
    username: Optional[str] = None
    role: Optional[str] = None


# ─── Login ────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str = Field(..., example="masteradmin")
    password: str = Field(..., example="admin123")


# ─── Enums ────────────────────────────────────────────────────────────────────

class RoleEnum(str, Enum):
    admin = "admin"
    guru = "guru"
    wali_siswa = "wali_siswa"
    kepala_sekolah = "kepala_sekolah"


# ─── Akun ─────────────────────────────────────────────────────────────────────

class AkunBase(BaseModel):
    username: str = Field(..., max_length=100, example="budi123")
    nama: str = Field(..., max_length=100, example="Budi Santoso")
    role: RoleEnum = Field(default=RoleEnum.admin)

class AkunCreate(AkunBase):
    password: str = Field(..., min_length=6, example="rahasia123")

class AkunUpdate(BaseModel):
    username: Optional[str] = Field(None, max_length=100)
    nama: Optional[str] = Field(None, max_length=100)
    role: Optional[RoleEnum] = None
    first_login: Optional[bool] = None

class AkunOut(AkunBase):
    id_akun: int
    first_login: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── Admin ────────────────────────────────────────────────────────────────────

class AdminCreate(BaseModel):
    id_akun: int

class AdminOut(BaseModel):
    id_admin: int
    id_akun: int

    class Config:
        from_attributes = True


# ─── Reset Password ───────────────────────────────────────────────────────────

class ResetPasswordBase(BaseModel):
    isi_pertanyaan: str = Field(..., max_length=50, example="Nama hewan peliharaan pertama?")
    jawaban: str = Field(..., max_length=50, example="Kucingku")

class ResetPasswordCreate(ResetPasswordBase):
    id_akun: int

class ResetPasswordUpdate(BaseModel):
    isi_pertanyaan: Optional[str] = Field(None, max_length=50)
    jawaban: Optional[str] = Field(None, max_length=50)

class ResetPasswordOut(ResetPasswordBase):
    id_pertanyaan: int
    id_akun: int

    class Config:
        from_attributes = True