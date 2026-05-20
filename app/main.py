import asyncio
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timedelta, date
from io import BytesIO
from typing import List, Optional

import jwt
import uvicorn
from fastapi import (
    FastAPI, Depends, HTTPException, Query, Request,
    UploadFile, File, WebSocket, WebSocketDisconnect, status,
    APIRouter,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT  # noqa: F401
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, HRFlowable,
)
from sqlalchemy import or_, and_, extract
from sqlalchemy.orm import Session

from app.database import engine, get_db, Base
from app import models, schemas, crud
from app.websocket_manager import ws_manager


# ─── Config ───────────────────────────────────────────────────────────────────

SECRET_KEY                  = os.getenv("SECRET_KEY", "smartschool-secret-key-laragon-dev")
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
FOTO_DIR                    = "static/foto"

os.makedirs(FOTO_DIR, exist_ok=True)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Smart School API",
    description="REST API Sistem Informasi Sekolah",
    version="1.4.0",
)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

router_laporan = APIRouter(prefix="/laporan", tags=["Laporan"])


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    payload = {
        **data,
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> models.Akun:
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid atau sudah kedaluwarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        id_akun = payload.get("id_akun")
        if id_akun is None:
            raise exc
    except jwt.PyJWTError:
        raise exc
    akun = crud.get_akun(db, id_akun)
    if not akun:
        raise exc
    return akun


def require_admin(
    current_user: models.Akun = Depends(get_current_user),
) -> models.Akun:
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya admin")
    return current_user


def _buat_inisial(nama: str) -> str:
    parts = [p for p in nama.split() if p]
    return "".join(p[0].upper() for p in parts[:2])


def _get_guru_or_403(db: Session, id_akun: int) -> models.Guru:
    guru = crud.get_guru_by_akun(db, id_akun)
    if not guru:
        raise HTTPException(status_code=404, detail="Data guru tidak ditemukan")
    return guru


def _cek_guru_akses_kelas(guru: models.Guru, id_kelas: int) -> None:
    """Pastikan guru memiliki akses ke id_kelas yang diminta.
    Guru dengan id_kelas NULL atau tidak mengandung id_kelas → 403.
    """
    allowed = crud.decode_id_kelas(guru.id_kelas)
    if not allowed or id_kelas not in allowed:
        raise HTTPException(status_code=403, detail="Guru tidak memiliki akses ke kelas ini")


def _cek_wali_akses_siswa(db: Session, current_user: models.Akun, id_siswa: int):
    if current_user.role == models.RoleEnum.wali_siswa:
        wali = crud.get_wali_siswa_by_akun(db, current_user.id_akun)
        if not wali or wali.id_siswa != id_siswa:
            raise HTTPException(status_code=403, detail="Akses ditolak")


# ─── Startup ──────────────────────────────────────────────────────────────────

@app.on_event("startup")
def seed_master_admin():
    db = next(get_db())
    try:
        if not crud.get_akun_by_username(db, "test"):
            crud.create_admin_with_akun(db, schemas.AdminCreate(username="test", nama="Admin"))
            logging.info("Akun TEST dibuat")
        for id_k, nama_k in [(1, "TK A"), (2, "TK B")]:
            if not db.get(models.Kelas, id_k):
                db.add(models.Kelas(id_kelas=id_k, nama_kelas=nama_k))
        db.commit()
    finally:
        db.close()


# ─── Root ─────────────────────────────────────────────────────────────────────

@app.get("/", tags=["Root"])
def root():
    return {"message": "Smart School API berjalan!", "docs": "/docs"}


@app.get("/health", tags=["Root"])
def health():
    return {"status": "ok"}


# ─── Auth ─────────────────────────────────────────────────────────────────────

@app.post("/auth/login", response_model=schemas.Token, tags=["Auth"])
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    akun = crud.authenticate_akun(db, payload.username, payload.password)
    if not akun:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        )
    device_id = payload.device_id
    if device_id and akun.device_id and akun.device_id != device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                "Akun ini sedang digunakan di perangkat lain. "
                "Logout terlebih dahulu sebelum login di sini."
            ),
        )
    if device_id:
        akun.device_id = device_id
        db.commit()
    token = create_access_token({
        "id_akun":     akun.id_akun,
        "username":    akun.username,
        "role":        akun.role.value,
        "first_login": akun.first_login,
    })
    return {"access_token": token, "token_type": "bearer", "first_login": akun.first_login}


@app.post("/auth/logout", tags=["Auth"])
def logout(db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    current_user.device_id = None
    db.commit()
    return {"message": "Logout berhasil"}

@app.post("/akun/{id_akun}/force-logout", tags=["Akun"])
def force_logout(
    id_akun: int,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user)
):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat melakukan logout paksa")
    if id_akun == current_user.id_akun:
        raise HTTPException(status_code=400, detail="Tidak dapat logout paksa akun sendiri")
    berhasil = crud.force_logout_akun(db, id_akun)
    if not berhasil:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan atau sudah offline")
    return {"message": "Logout paksa berhasil"}


@app.get("/auth/me", tags=["Auth"])
def me(current_user: models.Akun = Depends(get_current_user)):
    return current_user


# ─── Akun ─────────────────────────────────────────────────────────────────────

@app.get("/akun/", response_model=List[schemas.AkunOut], tags=["Akun"])
def list_akun(skip=0, limit=100, db: Session = Depends(get_db), _=Depends(require_admin)):
    return crud.get_all_akun(db, skip, limit)


@app.get("/akun/by-username/{username}", response_model=schemas.AkunOut, tags=["Akun"])
def get_akun_by_username(username: str, db: Session = Depends(get_db)):
    akun = crud.get_akun_by_username(db, username)
    if not akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return akun


@app.get("/akun/{id_akun}", response_model=schemas.AkunOut, tags=["Akun"])
def get_akun(id_akun: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    akun = crud.get_akun(db, id_akun)
    if not akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return akun


@app.put("/akun/{id_akun}", response_model=schemas.AkunOut, tags=["Akun"])
def update_akun(id_akun: int, akun: schemas.AkunUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    obj = crud.update_akun(db, id_akun, akun)
    if not obj:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return obj


@app.delete("/akun/{id_akun}", tags=["Akun"])
def delete_akun(id_akun: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not crud.delete_akun(db, id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return {"message": f"Akun {id_akun} berhasil dihapus"}


@app.post("/akun/{id_akun}/selesai-setup", response_model=schemas.AkunOut, tags=["Akun"])
def selesai_setup(id_akun: int, db: Session = Depends(get_db)):
    akun = crud.get_akun(db, id_akun)
    if not akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    akun.first_login = False
    db.commit()
    db.refresh(akun)
    return akun


@app.post("/akun/{id_akun}/ganti-password-firstlogin", response_model=schemas.AkunOut, tags=["Akun"])
def ganti_password_first_login(id_akun: int, payload: schemas.GantiPasswordFirstLoginRequest, db: Session = Depends(get_db)):
    akun = crud.get_akun(db, id_akun)
    if not akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    if not akun.first_login:
        raise HTTPException(status_code=400, detail="Hanya untuk akun yang belum selesai setup")
    akun.password = crud.hash_password(payload.password_baru)
    akun.first_login = False
    db.commit()
    db.refresh(akun)
    return akun


@app.post("/akun/create-with-role", response_model=schemas.AkunOut, status_code=201, tags=["Akun"])
async def create_akun_with_role(request: Request, db: Session = Depends(get_db), _=Depends(require_admin)):
    try:
        body = json.loads(await request.body())
        data = schemas.AkunCreateWithRole(**body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))
    if crud.get_akun_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    if data.role == schemas.RoleEnum.admin:
        return crud.create_admin_with_akun(db, schemas.AdminCreate(username=data.username, nama=data.nama)).akun
    if data.role == schemas.RoleEnum.kepala_sekolah:
        if data.nip and crud.get_kepsek_by_nip(db, data.nip):
            raise HTTPException(status_code=400, detail="NIP sudah terdaftar")
        return crud.create_kepsek_with_akun(db, schemas.KepsekCreate(username=data.username, nama=data.nama, nip=data.nip)).akun
    raise HTTPException(status_code=400, detail="Gunakan endpoint /guru/ untuk role guru")


# ─── Reset Password ───────────────────────────────────────────────────────────

@app.post("/reset-password/", response_model=schemas.ResetPasswordOut, status_code=201, tags=["Reset Password"])
def create_reset_password(rp: schemas.ResetPasswordCreate, db: Session = Depends(get_db)):
    if not crud.get_akun(db, rp.id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    if crud.get_reset_password_by_akun(db, rp.id_akun):
        raise HTTPException(status_code=400, detail="Pertanyaan keamanan sudah ada")
    return crud.create_reset_password(db, rp)


@app.get("/reset-password/akun/{id_akun}", response_model=schemas.ResetPasswordOut, tags=["Reset Password"])
def get_pertanyaan_by_akun(id_akun: int, db: Session = Depends(get_db)):
    if not crud.get_akun(db, id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    obj = crud.get_reset_password_by_akun(db, id_akun)
    if not obj:
        raise HTTPException(status_code=404, detail="Pertanyaan keamanan tidak ditemukan")
    return obj


@app.post("/reset-password/verify", tags=["Reset Password"])
def verify_jawaban(payload: schemas.VerifyJawabanRequest, db: Session = Depends(get_db)):
    if not crud.get_akun(db, payload.id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    if not crud.verify_jawaban_reset(db, payload.id_akun, payload.jawaban):
        raise HTTPException(status_code=400, detail="Jawaban keamanan salah")
    return {"message": "Jawaban benar. Silakan ganti password."}


@app.post("/reset-password/ganti-password", response_model=schemas.AkunOut, tags=["Reset Password"])
def ganti_password(payload: schemas.GantiPasswordRequest, db: Session = Depends(get_db)):
    if not crud.get_akun(db, payload.id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    if not crud.verify_jawaban_reset(db, payload.id_akun, payload.jawaban):
        raise HTTPException(status_code=400, detail="Jawaban keamanan salah")
    try:
        akun = crud.ganti_password(db, payload.id_akun, payload.password_baru)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return akun


@app.get("/reset-password/", response_model=List[schemas.ResetPasswordOut], tags=["Reset Password"])
def list_reset_password(skip=0, limit=100, db: Session = Depends(get_db), _=Depends(require_admin)):
    return crud.get_all_reset_password(db, skip, limit)


@app.put("/reset-password/{id_pertanyaan}", response_model=schemas.ResetPasswordOut, tags=["Reset Password"])
def update_reset_password(id_pertanyaan: int, rp: schemas.ResetPasswordUpdate, db: Session = Depends(get_db)):
    obj = crud.update_reset_password(db, id_pertanyaan, rp)
    if not obj:
        raise HTTPException(status_code=404, detail="Pertanyaan tidak ditemukan")
    return obj


@app.delete("/reset-password/{id_pertanyaan}", tags=["Reset Password"])
def delete_reset_password(id_pertanyaan: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not crud.delete_reset_password(db, id_pertanyaan):
        raise HTTPException(status_code=404, detail="Pertanyaan tidak ditemukan")
    return {"message": f"Pertanyaan {id_pertanyaan} berhasil dihapus"}


# ─── Kelas ────────────────────────────────────────────────────────────────────

@app.post("/kelas/", response_model=schemas.KelasOut, status_code=201, tags=["Kelas"])
def create_kelas(kelas: schemas.KelasCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    return crud.create_kelas(db, kelas)


@app.get("/kelas/", response_model=List[schemas.KelasOut], tags=["Kelas"])
def list_kelas(skip=0, limit=100, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return crud.get_all_kelas(db, skip, limit)


@app.get("/kelas/{id_kelas}", response_model=schemas.KelasOut, tags=["Kelas"])
def get_kelas(id_kelas: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = crud.get_kelas(db, id_kelas)
    if not obj:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return obj


@app.put("/kelas/{id_kelas}", response_model=schemas.KelasOut, tags=["Kelas"])
def update_kelas(id_kelas: int, kelas: schemas.KelasUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    obj = crud.update_kelas(db, id_kelas, kelas)
    if not obj:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return obj


@app.delete("/kelas/{id_kelas}", tags=["Kelas"])
def delete_kelas(id_kelas: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not crud.delete_kelas(db, id_kelas):
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return {"message": f"Kelas {id_kelas} berhasil dihapus"}


# ─── Guru ─────────────────────────────────────────────────────────────────────

@app.post("/guru/", response_model=schemas.GuruOut, status_code=201, tags=["Guru"])
def create_guru(guru: schemas.GuruCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if crud.get_akun_by_username(db, guru.username):
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    if guru.nip and crud.get_guru_by_nip(db, guru.nip):
        raise HTTPException(status_code=400, detail="NIP sudah terdaftar")
    for id_k in (guru.list_id_kelas or []):
        if not crud.get_kelas(db, id_k):
            raise HTTPException(status_code=404, detail=f"Kelas {id_k} tidak ditemukan")
    return crud.create_guru_with_akun(db, guru)


@app.get("/guru/", response_model=List[schemas.GuruOut], tags=["Guru"])
def list_guru(skip=0, limit=100, db: Session = Depends(get_db), _=Depends(require_admin)):
    return crud.get_all_guru(db, skip, limit)


@app.get("/guru/me", response_model=schemas.GuruOut, tags=["Guru"])
def get_guru_me(db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    """Ambil data guru milik user yang sedang login (berdasarkan token)."""
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses endpoint ini")
    obj = crud.get_guru_by_akun(db, current_user.id_akun)
    if not obj:
        raise HTTPException(status_code=404, detail="Data guru tidak ditemukan")
    return obj


@app.get("/guru/{id_guru}", response_model=schemas.GuruOut, tags=["Guru"])
def get_guru(id_guru: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = crud.get_guru(db, id_guru)
    if not obj:
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return obj


@app.put("/guru/{id_guru}", response_model=schemas.GuruOut, tags=["Guru"])
def update_guru(id_guru: int, guru: schemas.GuruUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    for id_k in (guru.list_id_kelas or []):
        if not crud.get_kelas(db, id_k):
            raise HTTPException(status_code=404, detail=f"Kelas {id_k} tidak ditemukan")
    obj = crud.update_guru(db, id_guru, guru)
    if not obj:
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return obj


@app.delete("/guru/{id_guru}", tags=["Guru"])
def delete_guru(id_guru: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not crud.delete_guru(db, id_guru):
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return {"message": f"Guru {id_guru} berhasil dihapus"}


# ─── Admin ────────────────────────────────────────────────────────────────────

@app.post("/admin/", response_model=schemas.AdminOut, status_code=201, tags=["Admin"])
def create_admin(data: schemas.AdminCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if crud.get_akun_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    return crud.create_admin_with_akun(db, data)


@app.get("/admin/", response_model=List[schemas.AdminOut], tags=["Admin"])
def list_admin(skip=0, limit=100, db: Session = Depends(get_db), _=Depends(require_admin)):
    return crud.get_all_admin(db, skip, limit)


@app.delete("/admin/{id_admin}", tags=["Admin"])
def delete_admin(id_admin: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not crud.delete_admin(db, id_admin):
        raise HTTPException(status_code=404, detail="Admin tidak ditemukan")
    return {"message": f"Admin {id_admin} berhasil dihapus"}


# ─── Kepala Sekolah ───────────────────────────────────────────────────────────

@app.post("/kepala-sekolah/", response_model=schemas.KepsekOut, status_code=201, tags=["Kepala Sekolah"])
def create_kepsek(data: schemas.KepsekCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if crud.get_akun_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    if data.nip and crud.get_kepsek_by_nip(db, data.nip):
        raise HTTPException(status_code=400, detail="NIP sudah terdaftar")
    return crud.create_kepsek_with_akun(db, data)


@app.get("/kepala-sekolah/", response_model=List[schemas.KepsekOut], tags=["Kepala Sekolah"])
def list_kepsek(skip=0, limit=100, db: Session = Depends(get_db), _=Depends(require_admin)):
    return crud.get_all_kepsek(db, skip, limit)


@app.get("/kepala-sekolah/{id_kepsek}", response_model=schemas.KepsekOut, tags=["Kepala Sekolah"])
def get_kepsek(id_kepsek: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = crud.get_kepsek(db, id_kepsek)
    if not obj:
        raise HTTPException(status_code=404, detail="Kepala sekolah tidak ditemukan")
    return obj


@app.put("/kepala-sekolah/{id_kepsek}", response_model=schemas.KepsekOut, tags=["Kepala Sekolah"])
def update_kepsek(id_kepsek: int, data: schemas.KepsekUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    obj = crud.update_kepsek(db, id_kepsek, data)
    if not obj:
        raise HTTPException(status_code=404, detail="Kepala sekolah tidak ditemukan")
    return obj


@app.delete("/kepala-sekolah/{id_kepsek}", tags=["Kepala Sekolah"])
def delete_kepsek(id_kepsek: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not crud.delete_kepsek(db, id_kepsek):
        raise HTTPException(status_code=404, detail="Kepala sekolah tidak ditemukan")
    return {"message": f"Kepala sekolah {id_kepsek} berhasil dihapus"}


# ─── Siswa ────────────────────────────────────────────────────────────────────

@app.post("/siswa/", response_model=schemas.SiswaOut, status_code=201, tags=["Siswa"])
def create_siswa(data: schemas.SiswaCreate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if crud.get_akun_by_username(db, data.username_wali):
        raise HTTPException(status_code=400, detail="Username wali sudah digunakan")
    if crud.get_siswa_by_nisn(db, data.nisn):
        raise HTTPException(status_code=400, detail="NISN sudah terdaftar")
    if data.id_kelas and not crud.get_kelas(db, data.id_kelas):
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return crud.create_siswa_with_wali(db, data)


@app.get("/siswa/", response_model=List[schemas.SiswaOut], tags=["Siswa"])
def list_siswa(skip=0, limit=100, db: Session = Depends(get_db), _=Depends(require_admin)):
    return crud.get_all_siswa(db, skip, limit)


@app.get("/siswa/{id_siswa}", response_model=schemas.SiswaOut, tags=["Siswa"])
def get_siswa(id_siswa: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = crud.get_siswa(db, id_siswa)
    if not obj:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return obj


@app.put("/siswa/{id_siswa}", response_model=schemas.SiswaOut, tags=["Siswa"])
def update_siswa(id_siswa: int, data: schemas.SiswaUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    if data.id_kelas and not crud.get_kelas(db, data.id_kelas):
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    obj = crud.update_siswa(db, id_siswa, data)
    if not obj:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return obj


@app.delete("/siswa/{id_siswa}", tags=["Siswa"])
def delete_siswa(id_siswa: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not crud.delete_siswa(db, id_siswa):
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return {"message": f"Siswa {id_siswa} berhasil dihapus"}


# ─── Wali Siswa ───────────────────────────────────────────────────────────────

@app.put("/wali-siswa/{id_wali_siswa}", response_model=schemas.WaliSiswaOut, tags=["Wali Siswa"])
def update_wali_siswa(id_wali_siswa: int, data: schemas.WaliSiswaUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    obj = crud.update_wali_siswa(db, id_wali_siswa, data)
    if not obj:
        raise HTTPException(status_code=404, detail="Wali siswa tidak ditemukan")
    return obj


@app.get("/wali-siswa/by-akun/{id_akun}", response_model=schemas.WaliSiswaOut, tags=["Wali Siswa"])
def get_wali_by_akun(id_akun: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role == models.RoleEnum.wali_siswa and current_user.id_akun != id_akun:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    obj = crud.get_wali_siswa_by_akun(db, id_akun)
    if not obj:
        raise HTTPException(status_code=404, detail="Data wali tidak ditemukan")
    return obj


# ─── Pesan ────────────────────────────────────────────────────────────────────

@app.post("/pesan/", response_model=schemas.PesanOut, status_code=201, tags=["Pesan"])
def kirim_pesan(data: schemas.PesanCreate, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if not crud.get_akun(db, data.id_penerima):
        raise HTTPException(status_code=404, detail="Penerima tidak ditemukan")
    pesan = models.Pesan(
        id_pengirim=current_user.id_akun,
        id_penerima=data.id_penerima,
        isi_pesan=data.isi_pesan.strip(),
        status=models.StatusPesanEnum.terkirim,
    )
    db.add(pesan)
    db.commit()
    db.refresh(pesan)
    crud.kirim_notif_pesan(
        db,
        id_akun_penerima=pesan.id_penerima,
        nama_pengirim=current_user.nama,
        id_pesan=pesan.id_pesan,
        payload_ws={
            "id_pesan":      pesan.id_pesan,
            "id_pengirim":   pesan.id_pengirim,
            "id_penerima":   pesan.id_penerima,
            "isi_pesan":     pesan.isi_pesan,
            "waktu":         str(pesan.waktu),
            "waktu_millis":  int(pesan.waktu.timestamp() * 1000),
            "nama_pengirim": current_user.nama,
        },
    )
    return pesan


@app.get("/pesan/riwayat/{id_a}/{id_b}", response_model=List[schemas.PesanOut], tags=["Pesan"])
def get_riwayat_percakapan(
    id_a: int, id_b: int,
    after_id: Optional[int] = Query(None, description="Ambil pesan dengan id_pesan > after_id (polling/realtime)"),
    before_id: Optional[int] = Query(None, description="Ambil pesan dengan id_pesan < before_id (load more ke atas)"),
    order: str = Query("asc", description="Urutan hasil: 'asc' atau 'desc'"),
    skip: int = Query(0),
    limit: int = Query(30),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    from fastapi.responses import Response as FastAPIResponse
    import json as _json

    if current_user.id_akun not in (id_a, id_b):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    kedua_arah = or_(
        and_(models.Pesan.id_pengirim == id_a, models.Pesan.id_penerima == id_b),
        and_(models.Pesan.id_pengirim == id_b, models.Pesan.id_penerima == id_a),
    )

    # ── Polling: hanya pesan baru setelah after_id (selalu asc) ───────────────
    if after_id is not None:
        return (
            db.query(models.Pesan)
            .filter(kedua_arah, models.Pesan.id_pesan > after_id)
            .order_by(models.Pesan.waktu.asc()).all()
        )

    # ── Tandai pesan dari lawan sebagai "diterima" (hanya saat fetch awal) ────
    if before_id is None:
        lawan_id = id_b if current_user.id_akun == id_a else id_a
        db.query(models.Pesan).filter(
            models.Pesan.id_pengirim == lawan_id,
            models.Pesan.id_penerima == current_user.id_akun,
            models.Pesan.status == models.StatusPesanEnum.terkirim,
        ).update({"status": models.StatusPesanEnum.diterima}, synchronize_session=False)
        db.commit()

    # ── Hitung total untuk header X-Total-Count ────────────────────────────────
    total = db.query(models.Pesan).filter(kedua_arah).count()

    # ── Bangun query utama ─────────────────────────────────────────────────────
    q = db.query(models.Pesan).filter(kedua_arah)

    if before_id is not None:
        # Load more ke atas: ambil N pesan tertua sebelum before_id
        # Pakai DESC dulu untuk mendapat yang terdekat, lalu balik urutan di Python
        q = (
            q.filter(models.Pesan.id_pesan < before_id)
            .order_by(models.Pesan.id_pesan.desc())
            .limit(limit)
        )
        hasil = list(reversed(q.all()))
    else:
        sort_col = models.Pesan.waktu.desc() if order == "desc" else models.Pesan.waktu.asc()
        hasil = q.order_by(sort_col).offset(skip).limit(limit).all()

    from fastapi.responses import JSONResponse
    from fastapi.encoders import jsonable_encoder
    response = JSONResponse(
        content=jsonable_encoder(hasil),
        headers={"X-Total-Count": str(total)},
    )
    return response


@app.put("/pesan/baca", tags=["Pesan"])
def tandai_dibaca(data: schemas.TandaiBacaRequest, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    db.query(models.Pesan).filter(
        models.Pesan.id_pengirim == data.id_pengirim,
        models.Pesan.id_penerima == current_user.id_akun,
        models.Pesan.status == models.StatusPesanEnum.diterima,
    ).update({"status": models.StatusPesanEnum.dibaca}, synchronize_session=False)
    db.commit()
    return {"message": "Pesan ditandai dibaca"}


@app.get("/pesan/percakapan/{id_akun}", response_model=List[schemas.PercakapanItem], tags=["Pesan"])
def get_daftar_percakapan(id_akun: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.id_akun != id_akun:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    semua_pesan = (
        db.query(models.Pesan)
        .filter(or_(models.Pesan.id_pengirim == id_akun, models.Pesan.id_penerima == id_akun))
        .order_by(models.Pesan.waktu.desc()).all()
    )
    hasil, sudah = [], set()
    for p in semua_pesan:
        lawan_id = p.id_penerima if p.id_pengirim == id_akun else p.id_pengirim
        if lawan_id in sudah:
            continue
        sudah.add(lawan_id)
        lawan_akun = crud.get_akun(db, lawan_id)
        if not lawan_akun:
            continue
        wali = db.query(models.WaliSiswa).filter(models.WaliSiswa.id_akun == lawan_id).first()
        nama_siswa = wali.siswa.nama_siswa if wali and wali.siswa else None
        belum_dibaca = db.query(models.Pesan).filter(
            models.Pesan.id_pengirim == lawan_id,
            models.Pesan.id_penerima == id_akun,
            models.Pesan.status.in_([models.StatusPesanEnum.terkirim, models.StatusPesanEnum.diterima]),
        ).count()
        hasil.append(schemas.PercakapanItem(
            id_akun_lawan=lawan_id,
            nama_lawan=lawan_akun.nama,
            nama_siswa=nama_siswa,
            inisial=_buat_inisial(lawan_akun.nama),
            pesan_terakhir=p.isi_pesan,
            waktu=p.waktu,
            status=p.status,
            jumlah_belum_dibaca=belum_dibaca,
        ))
    return hasil


@app.get("/pesan/semua-guru", response_model=List[schemas.GuruListItem], tags=["Pesan"])
def get_semua_guru(db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.wali_siswa:
        raise HTTPException(status_code=403, detail="Hanya wali siswa yang dapat mengakses")
    guru_list = db.query(models.Guru).join(models.Akun).all()
    hasil = []
    for guru in guru_list:
        gid = guru.id_akun
        pesan_terakhir = (
            db.query(models.Pesan)
            .filter(or_(
                and_(models.Pesan.id_pengirim == current_user.id_akun, models.Pesan.id_penerima == gid),
                and_(models.Pesan.id_pengirim == gid, models.Pesan.id_penerima == current_user.id_akun),
            ))
            .order_by(models.Pesan.waktu.desc()).first()
        )
        belum = db.query(models.Pesan).filter(
            models.Pesan.id_pengirim == gid,
            models.Pesan.id_penerima == current_user.id_akun,
            models.Pesan.status == models.StatusPesanEnum.diterima,
        ).count()
        hasil.append(schemas.GuruListItem(
            id_akun_guru=gid,
            nama_guru=guru.akun.nama,
            inisial=_buat_inisial(guru.akun.nama),
            pesan_terakhir=pesan_terakhir.isi_pesan if pesan_terakhir else None,
            waktu=pesan_terakhir.waktu if pesan_terakhir else None,
            status=pesan_terakhir.status if pesan_terakhir else None,
            jumlah_belum_dibaca=belum,
        ))
    hasil.sort(key=lambda x: x.waktu or datetime.min, reverse=True)
    return hasil


@app.get("/pesan/semua-wali", response_model=List[schemas.WaliListItem], tags=["Pesan"])
def get_semua_wali(db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")
    guru = _get_guru_or_403(db, current_user.id_akun)
    allowed_kelas = crud.decode_id_kelas(guru.id_kelas)  # [] jika NULL
    return [
        schemas.WaliListItem(
            id_akun_wali=w.id_akun,
            nama_wali=w.akun.nama,
            inisial=_buat_inisial(w.akun.nama),
            nama_siswa=w.siswa.nama_siswa if w.siswa else "",
            id_kelas_siswa=w.siswa.id_kelas if w.siswa else None,
        )
        for w in db.query(models.WaliSiswa).join(models.Akun).all()
        if w.siswa and w.siswa.id_kelas in allowed_kelas
    ]


# ─── Absensi ──────────────────────────────────────────────────────────────────

@app.get("/absensi/kelas/{id_kelas}", response_model=List[schemas.SiswaAbsensiItem], tags=["Absensi"])
def get_siswa_absensi(id_kelas: int, tanggal: date, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")
    guru = _get_guru_or_403(db, current_user.id_akun)
    _cek_guru_akses_kelas(guru, id_kelas)
    if not crud.get_kelas(db, id_kelas):
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    siswa_list = (
        db.query(models.Siswa)
        .filter(models.Siswa.id_kelas == id_kelas)
        .order_by(models.Siswa.nama_siswa).all()
    )
    id_list = [s.id_siswa for s in siswa_list]
    absensi_map = {}
    if id_list:
        absensi_map = {
            a.id_siswa: a
            for a in db.query(models.Absensi).filter(
                models.Absensi.id_siswa.in_(id_list),
                models.Absensi.tanggal == tanggal,
            ).all()
        }
    return [
        schemas.SiswaAbsensiItem(
            id_siswa=s.id_siswa,
            nama_siswa=s.nama_siswa,
            status=absensi_map[s.id_siswa].status if s.id_siswa in absensi_map else None,
            keterangan=absensi_map[s.id_siswa].keterangan if s.id_siswa in absensi_map else None,
        )
        for s in siswa_list
    ]


@app.post("/absensi/batch", response_model=List[schemas.AbsensiOut], tags=["Absensi"])
def simpan_absensi_batch(payload: schemas.AbsensiBatchRequest, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")
    guru = _get_guru_or_403(db, current_user.id_akun)
    _cek_guru_akses_kelas(guru, payload.id_kelas)
    hasil = []
    for item in payload.data:
        siswa = crud.get_siswa(db, item.id_siswa)
        if not siswa or siswa.id_kelas != payload.id_kelas:
            raise HTTPException(status_code=400, detail=f"Siswa {item.id_siswa} tidak ada di kelas {payload.id_kelas}")
        existing = db.query(models.Absensi).filter(
            models.Absensi.id_siswa == item.id_siswa,
            models.Absensi.tanggal == payload.tanggal,
        ).first()
        if existing:
            existing.status = item.status
            existing.keterangan = item.keterangan
            existing.id_guru = guru.id_guru
            hasil.append(existing)
        else:
            ab = models.Absensi(
                id_siswa=item.id_siswa, id_guru=guru.id_guru,
                tanggal=payload.tanggal, status=item.status, keterangan=item.keterangan,
            )
            db.add(ab)
            hasil.append(ab)
    db.commit()
    for ab in hasil:
        db.refresh(ab)
    if hasil:
        crud.kirim_notif_absensi_batch(db, payload.id_kelas, str(payload.tanggal), current_user.nama, hasil[0].id_absensi, hasil_absensi=hasil)
    return hasil


@app.get("/absensi/siswa/{id_siswa}", response_model=List[schemas.AbsensiHarianSiswaOut], tags=["Absensi"])
def get_absensi_siswa(id_siswa: int, bulan: int, tahun: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    _cek_wali_akses_siswa(db, current_user, id_siswa)
    records = db.query(models.Absensi).filter(
        models.Absensi.id_siswa == id_siswa,
        extract("month", models.Absensi.tanggal) == bulan,
        extract("year",  models.Absensi.tanggal) == tahun,
    ).order_by(models.Absensi.tanggal).all()
    return [
        schemas.AbsensiHarianSiswaOut(
            id_absensi=ab.id_absensi, id_siswa=ab.id_siswa, id_guru=ab.id_guru,
            tanggal=ab.tanggal, status=ab.status, keterangan=ab.keterangan,
            nama_guru=ab.guru.akun.nama if ab.guru and ab.guru.akun else None,
        )
        for ab in records
    ]


@app.get("/absensi/siswa/{id_siswa}/ringkasan",
         response_model=schemas.RingkasanAbsensiOut, tags=["Absensi"])
def get_ringkasan_absensi(
    id_siswa: int, bulan: int, tahun: int,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    _cek_wali_akses_siswa(db, current_user, id_siswa)
    records = db.query(models.Absensi).filter(
        models.Absensi.id_siswa == id_siswa,
        extract("month", models.Absensi.tanggal) == bulan,
        extract("year",  models.Absensi.tanggal) == tahun,
    ).all()

    rekap = schemas.RingkasanAbsensiOut(bulan=bulan, tahun=tahun)
    for ab in records:
        if   ab.status == models.StatusAbsensiEnum.hadir: rekap.hadir += 1
        elif ab.status == models.StatusAbsensiEnum.sakit: rekap.sakit += 1
        elif ab.status == models.StatusAbsensiEnum.izin:  rekap.izin  += 1
        elif ab.status == models.StatusAbsensiEnum.alpha: rekap.alpha += 1

    rekap.total_hari = rekap.hadir + rekap.sakit + rekap.izin + rekap.alpha

    return rekap


# ─── Catatan Harian ───────────────────────────────────────────────────────────

@router_laporan.get("/catatan", response_model=schemas.LaporanCatatanKelasOut, summary="[GURU/ADMIN] Daftar catatan harian semua siswa satu kelas (range tanggal)")
def get_laporan_catatan(
    id_kelas: int = Query(..., description="ID kelas"),
    tanggal_awal: date = Query(..., description="Format: yyyy-MM-dd"),
    tanggal_akhir: date = Query(..., description="Format: yyyy-MM-dd"),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if tanggal_awal > tanggal_akhir:
        raise HTTPException(status_code=400, detail="tanggal_awal tidak boleh lebih besar dari tanggal_akhir")

    # ✅ Admin/kepsek tidak perlu cek guru & akses kelas
    is_admin = current_user.role in (models.RoleEnum.admin, models.RoleEnum.kepala_sekolah)
    if not is_admin:
        guru = _get_guru_or_403(db, current_user.id_akun)
        _cek_guru_akses_kelas(guru, id_kelas)

    result = crud.get_laporan_catatan_kelas_range(db, id_kelas, tanggal_awal, tanggal_akhir)
    if not result:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    if result.siswa:
        nisn_map = {s.id_siswa: (s.nisn or "") for s in db.query(models.Siswa).filter(models.Siswa.id_kelas == id_kelas).all()}
        for item in result.siswa:
            if not getattr(item, "nisn", None):
                item.nisn = nisn_map.get(item.id_siswa, "")
    return result


@app.post("/catatan/", response_model=schemas.CatatanHarianOut, status_code=201, tags=["Catatan Harian"])
def buat_catatan(
    payload: schemas.CatatanHarianCreate,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat membuat catatan")
    guru = _get_guru_or_403(db, current_user.id_akun)
    catatan = crud.create_catatan_harian(db, payload, guru.id_guru)
    # Kirim notifikasi catatan ke wali yang relevan + WebSocket event
    crud.kirim_notif_catatan(db, catatan, current_user.nama)
    return crud._build_catatan_out(catatan)


@app.get("/catatan/siswa/{id_siswa}", response_model=schemas.CatatanListResponse, tags=["Catatan Harian"])
def get_catatan_siswa(id_siswa: int, skip=0, limit=20, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    siswa = crud.get_siswa(db, id_siswa)
    if not siswa:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    if current_user.role == models.RoleEnum.wali_siswa:
        wali = crud.get_wali_siswa_by_akun(db, current_user.id_akun)
        if not wali or wali.id_siswa != id_siswa:
            raise HTTPException(status_code=403, detail="Anda hanya dapat melihat catatan anak Anda")
    catatan_list = crud.get_catatan_by_siswa(db, id_siswa, siswa.id_kelas, skip, limit)
    return schemas.CatatanListResponse(total=len(catatan_list), data=[crud._build_catatan_out(c) for c in catatan_list])


@app.get("/catatan/guru/", response_model=schemas.CatatanListResponse, tags=["Catatan Harian"])
def get_catatan_by_guru_login(skip=0, limit=50, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")
    guru = _get_guru_or_403(db, current_user.id_akun)
    catatan_list = crud.get_catatan_by_guru(db, guru.id_guru, skip, limit)
    return schemas.CatatanListResponse(total=len(catatan_list), data=[crud._build_catatan_out(c) for c in catatan_list])


@app.get("/catatan/{id_catatan}", response_model=schemas.CatatanHarianOut, tags=["Catatan Harian"])
def get_catatan_detail(id_catatan: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    catatan = crud.get_catatan_harian(db, id_catatan)
    if not catatan:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    if current_user.role == models.RoleEnum.wali_siswa:
        wali  = crud.get_wali_siswa_by_akun(db, current_user.id_akun)
        siswa = crud.get_siswa(db, wali.id_siswa) if wali and wali.id_siswa else None
        visible = (
            catatan.target == models.TargetCatatanEnum.semua_kelas or
            (catatan.target == models.TargetCatatanEnum.satu_kelas and siswa and siswa.id_kelas == catatan.id_kelas) or
            (catatan.target == models.TargetCatatanEnum.satu_siswa and wali and wali.id_siswa == catatan.id_siswa)
        )
        if not visible:
            raise HTTPException(status_code=403, detail="Akses ditolak")
    return crud._build_catatan_out(catatan)


@app.put("/catatan/{id_catatan}", response_model=schemas.CatatanHarianOut, tags=["Catatan Harian"])
def update_catatan(id_catatan: int, payload: schemas.CatatanHarianUpdate, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengedit catatan")
    catatan = crud.get_catatan_harian(db, id_catatan)
    if not catatan:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    guru = _get_guru_or_403(db, current_user.id_akun)
    if catatan.id_guru != guru.id_guru:
        raise HTTPException(status_code=403, detail="Anda bukan pembuat catatan ini")
    return crud._build_catatan_out(crud.update_catatan_harian(db, id_catatan, payload))


@app.delete("/catatan/{id_catatan}", tags=["Catatan Harian"])
def delete_catatan(id_catatan: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    catatan = crud.get_catatan_harian(db, id_catatan)
    if not catatan:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    if current_user.role == models.RoleEnum.guru:
        guru = _get_guru_or_403(db, current_user.id_akun)
        if catatan.id_guru != guru.id_guru:
            raise HTTPException(status_code=403, detail="Anda bukan pembuat catatan ini")
    elif current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    crud.delete_catatan_harian(db, id_catatan)
    return {"message": f"Catatan {id_catatan} berhasil dihapus"}


@app.post("/catatan/{id_catatan}/upload-foto", tags=["Catatan Harian"])
async def upload_foto_catatan(id_catatan: int, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat upload foto")
    catatan = crud.get_catatan_harian(db, id_catatan)
    if not catatan:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    guru = _get_guru_or_403(db, current_user.id_akun)
    if catatan.id_guru != guru.id_guru:
        raise HTTPException(status_code=403, detail="Anda bukan pembuat catatan ini")
    if catatan.foto:
        lama = os.path.join(FOTO_DIR, catatan.foto)
        if os.path.exists(lama):
            os.remove(lama)
    ext = os.path.splitext(file.filename)[1].lower()
    nama_file = f"{uuid.uuid4().hex}{ext}"
    with open(os.path.join(FOTO_DIR, nama_file), "wb") as f:
        shutil.copyfileobj(file.file, f)
    catatan.foto = nama_file
    db.commit()
    return {"nama_file": nama_file, "url": f"/static/foto/{nama_file}"}


# ─── Notifikasi ───────────────────────────────────────────────────────────────

@app.get("/notifikasi/", response_model=schemas.NotifikasiListResponse, tags=["Notifikasi"])
def get_notifikasi(skip=0, limit=50, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    return schemas.NotifikasiListResponse(
        total_belum_dibaca=crud.count_notif_belum_dibaca(db, current_user.id_akun),
        data=crud.get_notifikasi_by_akun(db, current_user.id_akun, skip, limit),
    )


@app.put("/notifikasi/baca", tags=["Notifikasi"])
def tandai_notif_dibaca(payload: schemas.BacaNotifRequest, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    jumlah = crud.tandai_notif_dibaca(db, current_user.id_akun, payload.id_notif)
    return {"message": f"{jumlah} notifikasi ditandai sudah dibaca", "jumlah": jumlah}


# ─── Laporan ──────────────────────────────────────────────────────────────────
# PENTING: urutan route — spesifik dulu, baru /{id_laporan}
# FastAPI membaca dari atas ke bawah; "/{id_laporan}" akan menangkap
# "/absensi", "/catatan", "/guru/", "/pdf/..." jika diletakkan lebih atas.

@router_laporan.post("/", response_model=schemas.LaporanOut, status_code=201, summary="Guru membuat laporan baru untuk satu kelas")
def buat_laporan(payload: schemas.LaporanCreate, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat membuat laporan")
    guru = _get_guru_or_403(db, current_user.id_akun)
    # Validasi kelas ada dan guru memiliki akses ke kelas tersebut
    kelas = db.get(models.Kelas, payload.id_kelas)
    if not kelas:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    _cek_guru_akses_kelas(guru, payload.id_kelas)
    lap = crud.create_laporan(db, payload, guru.id_guru)
    return crud._build_laporan_out(lap)


@router_laporan.get("/guru/", response_model=schemas.LaporanListResponse, summary="Daftar laporan milik guru yang sedang login")
def list_laporan_guru(skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")
    guru = _get_guru_or_403(db, current_user.id_akun)
    data = crud.get_laporan_by_guru(db, guru.id_guru, skip, limit)
    stat = crud._hitung_statistik_laporan(data)
    return schemas.LaporanListResponse(**stat, data=[crud._build_laporan_out(l) for l in data])


@router_laporan.get("/admin/", response_model=schemas.LaporanListResponse, summary="[Admin] Daftar semua laporan dari semua guru")
def list_laporan_admin(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role not in (models.RoleEnum.admin, models.RoleEnum.kepala_sekolah):
        raise HTTPException(status_code=403, detail="Hanya admin atau kepala sekolah yang dapat mengakses")
    data = crud.get_all_laporan(db, skip, limit)
    stat = crud._hitung_statistik_laporan(data)
    return schemas.LaporanListResponse(**stat, data=[crud._build_laporan_out(l) for l in data])


@router_laporan.get("/absensi", response_model=schemas.LaporanAbsensiKelasOut, summary="[GURU] Rekap absensi seluruh siswa satu kelas (range tanggal)")
def get_laporan_absensi(
    id_kelas: int = Query(..., description="ID kelas"),
    tanggal_awal: date = Query(..., description="Format: yyyy-MM-dd"),
    tanggal_akhir: date = Query(..., description="Format: yyyy-MM-dd"),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if tanggal_awal > tanggal_akhir:
        raise HTTPException(status_code=400, detail="tanggal_awal tidak boleh lebih besar dari tanggal_akhir")
    guru = _get_guru_or_403(db, current_user.id_akun)
    _cek_guru_akses_kelas(guru, id_kelas)
    result = crud.get_laporan_absensi_kelas_range(db, id_kelas, tanggal_awal, tanggal_akhir)
    if not result:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    # ── Inject nisn dari DB ───────────────────────────────────────────────────
    if result.siswa:
        nisn_map = {s.id_siswa: (s.nisn or "") for s in db.query(models.Siswa).filter(models.Siswa.id_kelas == id_kelas).all()}
        for item in result.siswa:
            if not getattr(item, "nisn", None):
                item.nisn = nisn_map.get(item.id_siswa, "")
    return result



@router_laporan.get("/pdf/absensi", summary="Generate PDF laporan absensi satu kelas")
def download_pdf_absensi(
    id_kelas: int = Query(...),
    tanggal_awal: date = Query(...),
    tanggal_akhir: date = Query(...),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if tanggal_awal > tanggal_akhir:
        raise HTTPException(status_code=400, detail="tanggal_awal > tanggal_akhir")

    # ✅ FIX: admin & kepala_sekolah boleh akses tanpa cek guru
    if current_user.role in (models.RoleEnum.admin, models.RoleEnum.kepala_sekolah):
        # Validasi kelas ada
        if not db.get(models.Kelas, id_kelas):
            raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    else:
        # Guru: tetap cek akses kelas seperti semula
        guru = _get_guru_or_403(db, current_user.id_akun)
        _cek_guru_akses_kelas(guru, id_kelas)

    data = crud.get_laporan_absensi_kelas_range(db, id_kelas, tanggal_awal, tanggal_akhir)
    if not data:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")

    pdf_bytes = _generate_pdf_absensi(data)
    nama_file = (
        f"laporan_absensi_{data.nama_kelas}_{tanggal_awal}_{tanggal_akhir}.pdf"
        .replace(" ", "_")
    )
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nama_file}"'},
    )


@router_laporan.get("/pdf/catatan", summary="[GURU/ADMIN] Generate PDF laporan catatan harian satu siswa")
def download_pdf_catatan(
    id_siswa: int = Query(...),
    tanggal_awal: date = Query(...),
    tanggal_akhir: date = Query(...),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if tanggal_awal > tanggal_akhir:
        raise HTTPException(status_code=400, detail="tanggal_awal > tanggal_akhir")

    # ✅ Admin/kepsek tidak perlu cek guru & akses kelas
    is_admin = current_user.role in (models.RoleEnum.admin, models.RoleEnum.kepala_sekolah)
    siswa = db.get(models.Siswa, id_siswa)
    if not siswa:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    if not is_admin:
        guru = _get_guru_or_403(db, current_user.id_akun)
        if siswa.id_kelas is not None:
            _cek_guru_akses_kelas(guru, siswa.id_kelas)

    nama_kelas = siswa.kelas.nama_kelas if siswa.kelas else "-"
    catatan_list = crud.get_catatan_siswa_range(db, id_siswa, tanggal_awal, tanggal_akhir)
    catatan_out = [
        schemas.CatatanRangeOut(
            id_catatan=c.id_catatan,
            tanggal=c.tanggal.date() if hasattr(c.tanggal, "date") else c.tanggal,
            judul=c.judul, isi=c.isi,
        )
        for c in catatan_list
    ]
    data_siswa = schemas.LaporanCatatanSiswaOut(
        id_siswa=siswa.id_siswa, nama_siswa=siswa.nama_siswa,
        jumlah_catatan=len(catatan_out), catatan=catatan_out,
    )
    pdf_bytes = _generate_pdf_catatan(data_siswa, nama_kelas, tanggal_awal, tanggal_akhir)
    nama_file = f"laporan_catatan_{siswa.nama_siswa}_{tanggal_awal}_{tanggal_akhir}.pdf".replace(" ", "_")
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf",
                             headers={"Content-Disposition": f'attachment; filename="{nama_file}"'})
    
@router_laporan.get(
    "/wali/",
    response_model=schemas.LaporanListResponse,
    summary="[WALI] Daftar laporan terverifikasi untuk kelas anak wali",
)
def list_laporan_wali(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    """
    Wali siswa melihat laporan (status = terverifikasi) yang terkait
    dengan kelas anaknya.
    - Ambil data wali & siswa dari akun yang login.
    - Filter laporan berdasarkan id_kelas siswa dan status = terverifikasi.
    """
    if current_user.role != models.RoleEnum.wali_siswa:
        raise HTTPException(status_code=403, detail="Hanya wali siswa yang dapat mengakses")
 
    wali = crud.get_wali_siswa_by_akun(db, current_user.id_akun)
    if not wali or not wali.id_siswa:
        raise HTTPException(status_code=404, detail="Data wali atau siswa tidak ditemukan")
 
    siswa = db.get(models.Siswa, wali.id_siswa)
    if not siswa or siswa.id_kelas is None:
        raise HTTPException(status_code=404, detail="Data siswa atau kelas tidak ditemukan")
 
    data = (
        db.query(models.Laporan)
        .filter(
            models.Laporan.id_kelas == siswa.id_kelas,
            models.Laporan.status == models.StatusLaporanEnum.terverifikasi,
        )
        .order_by(models.Laporan.tanggal_dibuat.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
 
    stat = crud._hitung_statistik_laporan(data)
    return schemas.LaporanListResponse(
        **stat,
        data=[crud._build_laporan_out(l) for l in data],
    )
 
 
# ─────────────────────────────────────────────────────────────────────────────
# Tambahkan juga endpoint PDF absensi & catatan agar wali bisa unduh.
# Letakkan berdekatan dengan endpoint wali di atas.
# ─────────────────────────────────────────────────────────────────────────────
 
 
@router_laporan.get(
    "/wali/pdf/absensi",
    summary="[WALI] Unduh PDF laporan absensi kelas anak",
)
def wali_download_pdf_absensi(
    id_kelas: int = Query(...),
    tanggal_awal: date = Query(...),
    tanggal_akhir: date = Query(...),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if current_user.role != models.RoleEnum.wali_siswa:
        raise HTTPException(status_code=403, detail="Hanya wali siswa yang dapat mengakses")
 
    # Pastikan kelas yang diminta adalah kelas anak wali ini
    wali = crud.get_wali_siswa_by_akun(db, current_user.id_akun)
    if not wali or not wali.id_siswa:
        raise HTTPException(status_code=404, detail="Data wali tidak ditemukan")
    siswa = db.get(models.Siswa, wali.id_siswa)
    if not siswa or siswa.id_kelas != id_kelas:
        raise HTTPException(status_code=403, detail="Akses ditolak ke kelas ini")
 
    if tanggal_awal > tanggal_akhir:
        raise HTTPException(status_code=400, detail="tanggal_awal > tanggal_akhir")
 
    # PDF wali: tampilkan data anak sendiri saja (detail harian per siswa)
    rekap        = crud.get_rekap_absensi_siswa_range(db, siswa.id_siswa, tanggal_awal, tanggal_akhir)
    absensi_list = crud.get_detail_absensi_siswa_range(db, siswa.id_siswa, tanggal_awal, tanggal_akhir)
    nama_kelas   = siswa.kelas.nama_kelas if siswa.kelas else "-"

    pdf_bytes = _generate_pdf_absensi_wali(
        nama_siswa    = siswa.nama_siswa,
        nama_kelas    = nama_kelas,
        tanggal_awal  = tanggal_awal,
        tanggal_akhir = tanggal_akhir,
        absensi_list  = absensi_list,
        rekap         = rekap,
    )
    nama_file = (
        f"absensi_{siswa.nama_siswa}_{tanggal_awal}_{tanggal_akhir}.pdf"
        .replace(" ", "_")
    )
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nama_file}"'},
    )
 
 
@router_laporan.get(
    "/wali/pdf/catatan",
    summary="[WALI] Unduh PDF laporan catatan harian anak",
)
def wali_download_pdf_catatan(
    id_siswa: int = Query(...),
    tanggal_awal: date = Query(...),
    tanggal_akhir: date = Query(...),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if current_user.role != models.RoleEnum.wali_siswa:
        raise HTTPException(status_code=403, detail="Hanya wali siswa yang dapat mengakses")
 
    wali = crud.get_wali_siswa_by_akun(db, current_user.id_akun)
    if not wali or wali.id_siswa != id_siswa:
        raise HTTPException(status_code=403, detail="Akses ditolak ke data siswa ini")
 
    siswa = db.get(models.Siswa, id_siswa)
    if not siswa:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
 
    if tanggal_awal > tanggal_akhir:
        raise HTTPException(status_code=400, detail="tanggal_awal > tanggal_akhir")
 
    nama_kelas = siswa.kelas.nama_kelas if siswa.kelas else "-"
    catatan_list = crud.get_catatan_siswa_range(db, id_siswa, tanggal_awal, tanggal_akhir)
    catatan_out = [
        schemas.CatatanRangeOut(
            id_catatan=c.id_catatan,
            tanggal=c.tanggal.date() if hasattr(c.tanggal, "date") else c.tanggal,
            judul=c.judul,
            isi=c.isi,
        )
        for c in catatan_list
    ]
    data_siswa = schemas.LaporanCatatanSiswaOut(
        id_siswa=siswa.id_siswa,
        nama_siswa=siswa.nama_siswa,
        jumlah_catatan=len(catatan_out),
        catatan=catatan_out,
    )
    pdf_bytes = _generate_pdf_catatan(data_siswa, nama_kelas, tanggal_awal, tanggal_akhir)
    nama_file = f"catatan_{siswa.nama_siswa}_{tanggal_awal}_{tanggal_akhir}.pdf".replace(" ", "_")
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nama_file}"'},
    )    

# ── /{id_laporan} — HARUS paling bawah di router ini ─────────────────────────

@router_laporan.get("/{id_laporan}", response_model=schemas.LaporanOut, summary="Detail satu laporan")
def get_laporan_detail(id_laporan: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    lap = crud.get_laporan(db, id_laporan)
    if not lap:
        raise HTTPException(status_code=404, detail="Laporan tidak ditemukan")
    if current_user.role == models.RoleEnum.guru:
        guru = _get_guru_or_403(db, current_user.id_akun)
        if lap.id_guru != guru.id_guru:
            raise HTTPException(status_code=403, detail="Akses ditolak")
    return crud._build_laporan_out(lap)


@router_laporan.delete("/{id_laporan}", summary="Hapus laporan (guru pemilik atau admin)")
def hapus_laporan(id_laporan: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    lap = crud.get_laporan(db, id_laporan)
    if not lap:
        raise HTTPException(status_code=404, detail="Laporan tidak ditemukan")
    if current_user.role == models.RoleEnum.guru:
        guru = _get_guru_or_403(db, current_user.id_akun)
        if lap.id_guru != guru.id_guru:
            raise HTTPException(status_code=403, detail="Anda bukan pembuat laporan ini")
    elif current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    crud.delete_laporan(db, id_laporan)
    return {"message": f"Laporan {id_laporan} berhasil dihapus"}


@router_laporan.put("/{id_laporan}/verifikasi", response_model=schemas.LaporanOut, summary="Admin memverifikasi laporan (ubah status + update tanggal)")
def verifikasi_laporan(id_laporan: int, payload: schemas.LaporanVerifikasi, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role not in (models.RoleEnum.admin, models.RoleEnum.kepala_sekolah):
        raise HTTPException(status_code=403, detail="Hanya admin atau kepala sekolah yang dapat memverifikasi laporan")
    lap = crud.verifikasi_laporan(db, id_laporan, payload)
    if not lap:
        raise HTTPException(status_code=404, detail="Laporan tidak ditemukan")
    # Kirim notifikasi ke semua wali siswa di kelas laporan
    if lap.status == models.StatusLaporanEnum.terverifikasi:
        crud.kirim_notif_laporan_terverifikasi(db, lap)
    return crud._build_laporan_out(lap)


# ─── PDF Generator: Absensi ───────────────────────────────────────────────────

def _generate_pdf_absensi(data: schemas.LaporanAbsensiKelasOut) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            topMargin=1.5*cm, bottomMargin=1.5*cm, leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()
    elements = []
    style_judul = ParagraphStyle("Judul", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=14, spaceAfter=4)
    style_sub   = ParagraphStyle("Sub",   parent=styles["Normal"],   alignment=TA_CENTER, fontSize=10, spaceAfter=2)
    elements.append(Paragraph("LAPORAN ABSENSI SISWA", style_judul))
    elements.append(Paragraph("TK QoulanSadid", style_sub))
    elements.append(Paragraph(f"Kelas: {data.nama_kelas}", style_sub))
    elements.append(Paragraph(f"Periode: {data.tanggal_awal.strftime('%d-%m-%Y')} s/d {data.tanggal_akhir.strftime('%d-%m-%Y')}", style_sub))
    elements.append(Spacer(1, 0.4*cm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2d6a4f")))
    elements.append(Spacer(1, 0.4*cm))
    header = ["No", "Nama Siswa", "Hadir", "Sakit", "Izin", "Alpha"]
    table_data = [header]
    for i, siswa in enumerate(data.siswa, start=1):
        table_data.append([str(i), siswa.nama_siswa, str(siswa.hadir), str(siswa.sakit), str(siswa.izin), str(siswa.alpha)])
    table_data.append(["", "TOTAL KELAS", str(data.total_hadir), str(data.total_sakit), str(data.total_izin), str(data.total_alpha)])
    col_widths = [1.2*cm, 11*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm]
    tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0),  (-1, 0),  colors.HexColor("#2d6a4f")),
        ("TEXTCOLOR",      (0, 0),  (-1, 0),  colors.white),
        ("FONTNAME",       (0, 0),  (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",       (0, 0),  (-1, 0),  9),
        ("ALIGN",          (0, 0),  (-1, 0),  "CENTER"),
        ("VALIGN",         (0, 0),  (-1, 0),  "MIDDLE"),
        ("FONTNAME",       (0, 1),  (-1, -2), "Helvetica"),
        ("FONTSIZE",       (0, 1),  (-1, -2), 9),
        ("ALIGN",          (0, 1),  (0, -1),  "CENTER"),
        ("ALIGN",          (1, 1),  (1, -1),  "LEFT"),
        ("ALIGN",          (2, 1),  (-1, -1), "CENTER"),
        ("VALIGN",         (0, 1),  (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1),  (-1, -2), [colors.white, colors.HexColor("#f0f7f4")]),
        ("BACKGROUND",     (0, -1), (-1, -1), colors.HexColor("#d8f3dc")),
        ("FONTNAME",       (0, -1), (-1, -1), "Helvetica-Bold"),
        ("FONTSIZE",       (0, -1), (-1, -1), 9),
        ("GRID",           (0, 0),  (-1, -1), 0.5, colors.HexColor("#b7d4c8")),
        ("ROWHEIGHT",      (0, 0),  (-1, -1), 0.7*cm),
        ("TOPPADDING",     (0, 0),  (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0),  (-1, -1), 4),
        ("LEFTPADDING",    (0, 0),  (-1, -1), 6),
        ("RIGHTPADDING",   (0, 0),  (-1, -1), 6),
    ]))
    elements.append(tbl)
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


# ─── PDF Generator: Catatan Harian ───────────────────────────────────────────

def _generate_pdf_catatan(data: schemas.LaporanCatatanSiswaOut, nama_kelas: str, tanggal_awal: date, tanggal_akhir: date) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            topMargin=1.5*cm, bottomMargin=1.5*cm, leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()
    elements = []
    style_judul = ParagraphStyle("Judul", parent=styles["Heading1"], alignment=TA_CENTER, fontSize=13, spaceAfter=4)
    style_sub   = ParagraphStyle("Sub",   parent=styles["Normal"],   alignment=TA_CENTER, fontSize=10, spaceAfter=2)
    style_info  = ParagraphStyle("Info",  parent=styles["Normal"],   fontSize=10, spaceAfter=2, leftIndent=20)
    elements.append(Paragraph("LAPORAN CATATAN HARIAN SISWA", style_judul))
    elements.append(Paragraph("TK QoulanSadid", style_sub))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#2d6a4f")))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(f"Nama Siswa : {data.nama_siswa}", style_info))
    elements.append(Paragraph(f"Kelas      : {nama_kelas}", style_info))
    elements.append(Paragraph(f"Periode    : {tanggal_awal.strftime('%d-%m-%Y')} s/d {tanggal_akhir.strftime('%d-%m-%Y')}", style_info))
    elements.append(Spacer(1, 0.4*cm))
    if not data.catatan:
        style_empty = ParagraphStyle("Empty", parent=styles["Normal"], alignment=TA_CENTER, fontSize=10, textColor=colors.HexColor("#999999"))
        elements.append(Paragraph("Tidak ada catatan harian dalam periode ini.", style_empty))
    else:
        style_cell = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=8, leading=11)
        table_data = [["No", "Tanggal", "Judul", "Catatan", "Saran"]]
        for i, catatan in enumerate(data.catatan, start=1):
            table_data.append([
                str(i),
                catatan.tanggal.strftime("%d-%m-%Y"),
                Paragraph(catatan.judul or "-", style_cell),
                Paragraph(catatan.isi or "-", style_cell),
                "",
            ])
        col_widths = [0.8*cm, 2.2*cm, 3*cm, 7*cm, 3*cm]
        tbl = Table(table_data, colWidths=col_widths, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",     (0, 0),  (-1, 0),  colors.HexColor("#2d6a4f")),
            ("TEXTCOLOR",      (0, 0),  (-1, 0),  colors.white),
            ("FONTNAME",       (0, 0),  (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",       (0, 0),  (-1, 0),  9),
            ("ALIGN",          (0, 0),  (-1, 0),  "CENTER"),
            ("VALIGN",         (0, 0),  (-1, 0),  "MIDDLE"),
            ("FONTNAME",       (0, 1),  (-1, -1), "Helvetica"),
            ("FONTSIZE",       (0, 1),  (-1, -1), 8),
            ("ALIGN",          (0, 1),  (1, -1),  "CENTER"),
            ("ALIGN",          (2, 1),  (-1, -1), "LEFT"),
            ("VALIGN",         (0, 1),  (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1),  (-1, -1), [colors.white, colors.HexColor("#f0f7f4")]),
            ("GRID",           (0, 0),  (-1, -1), 0.5, colors.HexColor("#b7d4c8")),
            ("TOPPADDING",     (0, 0),  (-1, -1), 5),
            ("BOTTOMPADDING",  (0, 0),  (-1, -1), 5),
            ("LEFTPADDING",    (0, 0),  (-1, -1), 5),
            ("RIGHTPADDING",   (0, 0),  (-1, -1), 5),
        ]))
        elements.append(tbl)
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


# ─── PDF Generator: Absensi Wali (per siswa, detail harian) ──────────────────

def _generate_pdf_absensi_wali(
    nama_siswa: str,
    nama_kelas: str,
    tanggal_awal: date,
    tanggal_akhir: date,
    absensi_list: list,          # list models.Absensi
    rekap: dict,                 # {"hadir":n, "sakit":n, "izin":n, "alpha":n}
) -> bytes:
    from reportlab.lib.enums import TA_RIGHT
    buffer  = BytesIO()
    doc     = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.5*cm, bottomMargin=2*cm,
        leftMargin=2*cm,  rightMargin=2*cm,
    )
    styles  = getSampleStyleSheet()
    COLOR_GREEN  = colors.HexColor("#2d6a4f")
    COLOR_LIGHT  = colors.HexColor("#f0f7f4")
    COLOR_BORDER = colors.HexColor("#b7d4c8")
    COLOR_TOTAL  = colors.HexColor("#d8f3dc")
    COLOR_GREY   = colors.HexColor("#555555")

    st_judul = ParagraphStyle("WJudul", parent=styles["Heading1"],
                              alignment=TA_CENTER, fontSize=14, spaceAfter=3,
                              textColor=COLOR_GREEN)
    st_sub   = ParagraphStyle("WSub",   parent=styles["Normal"],
                              alignment=TA_CENTER, fontSize=10, spaceAfter=2)
    st_info  = ParagraphStyle("WInfo",  parent=styles["Normal"],
                              fontSize=10, spaceAfter=3, leftIndent=10)
    st_label = ParagraphStyle("WLabel", parent=styles["Normal"],
                              fontSize=9,  textColor=COLOR_GREY)
    st_right = ParagraphStyle("WRight", parent=styles["Normal"],
                              fontSize=9,  alignment=TA_RIGHT, textColor=COLOR_GREY)

    NAMA_BULAN_ID = [
        "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
        "Juli", "Agustus", "September", "Oktober", "November", "Desember",
    ]
    NAMA_HARI_ID = {
        0: "Senin", 1: "Selasa", 2: "Rabu", 3: "Kamis",
        4: "Jumat", 5: "Sabtu", 6: "Minggu",
    }

    def fmt_tanggal(d: date) -> str:
        return (f"{NAMA_HARI_ID[d.weekday()]}, "
                f"{d.day:02d} {NAMA_BULAN_ID[d.month]} {d.year}")

    def fmt_periode(a: date, b: date) -> str:
        if a.month == b.month and a.year == b.year:
            return f"{NAMA_BULAN_ID[a.month]} {a.year}"
        return (f"{a.day:02d} {NAMA_BULAN_ID[a.month]} {a.year}"
                f" s/d {b.day:02d} {NAMA_BULAN_ID[b.month]} {b.year}")

    STATUS_LABEL = {
        "hadir": "Hadir", "sakit": "Sakit",
        "izin":  "Izin",  "alpha": "Alpha",
    }
    STATUS_COLOR = {
        "hadir": colors.HexColor("#1b7a4a"),
        "sakit": colors.HexColor("#e67e22"),
        "izin":  colors.HexColor("#2980b9"),
        "alpha": colors.HexColor("#c0392b"),
    }
    st_cell = ParagraphStyle("WCell", parent=styles["Normal"], fontSize=9, leading=12)

    elems = []

    # ── Header ────────────────────────────────────────────────────────────────
    elems.append(Paragraph("LAPORAN ABSENSI SISWA", st_judul))
    elems.append(Paragraph("TK Qoulan Sadid", st_sub))
    elems.append(Spacer(1, 0.3*cm))
    elems.append(HRFlowable(width="100%", thickness=1.5, color=COLOR_GREEN))
    elems.append(Spacer(1, 0.35*cm))

    # ── Info siswa ────────────────────────────────────────────────────────────
    info_data = [
        [Paragraph("<b>Nama Siswa</b>", st_info),
         Paragraph(f": {nama_siswa}", st_info)],
        [Paragraph("<b>Kelas</b>", st_info),
         Paragraph(f": {nama_kelas}", st_info)],
        [Paragraph("<b>Periode</b>", st_info),
         Paragraph(f": {fmt_periode(tanggal_awal, tanggal_akhir)}", st_info)],
    ]
    info_tbl = Table(info_data, colWidths=[4*cm, 12*cm])
    info_tbl.setStyle(TableStyle([
        ("VALIGN",  (0,0), (-1,-1), "TOP"),
        ("TOPPADDING",    (0,0), (-1,-1), 2),
        ("BOTTOMPADDING", (0,0), (-1,-1), 2),
    ]))
    elems.append(info_tbl)
    elems.append(Spacer(1, 0.4*cm))
    elems.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER))
    elems.append(Spacer(1, 0.35*cm))

    # ── Ringkasan ─────────────────────────────────────────────────────────────
    elems.append(Paragraph("<b>Ringkasan Kehadiran</b>", st_info))
    elems.append(Spacer(1, 0.2*cm))

    rek_data = [[
        Paragraph(f"<b>{rekap.get('hadir',0)}</b>\nHadir",  st_cell),
        Paragraph(f"<b>{rekap.get('izin', 0)}</b>\nIzin",   st_cell),
        Paragraph(f"<b>{rekap.get('sakit',0)}</b>\nSakit",  st_cell),
        Paragraph(f"<b>{rekap.get('alpha',0)}</b>\nAlpha",  st_cell),
        Paragraph(f"<b>{rekap.get('total_hari',0)}</b>\nTotal Hari", st_cell),
    ]]
    rek_tbl = Table(rek_data, colWidths=[3.2*cm]*5)
    rek_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (0,0),  colors.HexColor("#d8f3dc")),
        ("BACKGROUND",    (1,0), (1,0),  colors.HexColor("#d6eaf8")),
        ("BACKGROUND",    (2,0), (2,0),  colors.HexColor("#fde8d8")),
        ("BACKGROUND",    (3,0), (3,0),  colors.HexColor("#fadbd8")),
        ("BACKGROUND",    (4,0), (4,0),  colors.HexColor("#eaf0fb")),
        ("ALIGN",         (0,0), (-1,-1), "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("FONTNAME",      (0,0), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,-1), 11),
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 8),
        ("GRID",          (0,0), (-1,-1), 0.5, COLOR_BORDER),
    ]))
    elems.append(rek_tbl)
    elems.append(Spacer(1, 0.5*cm))

    # ── Tabel detail ──────────────────────────────────────────────────────────
    elems.append(Paragraph("<b>Detail Kehadiran Harian</b>", st_info))
    elems.append(Spacer(1, 0.2*cm))

    header = ["No", "Tanggal", "Status", "Keterangan"]
    tbl_data = [header]

    if not absensi_list:
        tbl_data.append(["–", "Tidak ada data absensi dalam periode ini.", "", ""])
    else:
        for i, ab in enumerate(absensi_list, start=1):
            status_val = ab.status.value if hasattr(ab.status, "value") else str(ab.status)
            status_lbl = STATUS_LABEL.get(status_val, status_val.capitalize())
            ket = ab.keterangan or "-"
            tbl_data.append([
                str(i),
                fmt_tanggal(ab.tanggal),
                status_lbl,
                ket,
            ])

    # Baris Total
    tbl_data.append([
        "", "TOTAL",
        (f"Hadir: {rekap.get('hadir',0)}  |  "
         f"Izin: {rekap.get('izin',0)}  |  "
         f"Sakit: {rekap.get('sakit',0)}  |  "
         f"Alpha: {rekap.get('alpha',0)}"),
        "",
    ])

    col_w = [0.8*cm, 5.5*cm, 2.8*cm, 7*cm]
    tbl   = Table(tbl_data, colWidths=col_w, repeatRows=1)

    # Warnai baris status secara conditional
    ts = [
        # Header
        ("BACKGROUND",    (0,0), (-1,0),  COLOR_GREEN),
        ("TEXTCOLOR",     (0,0), (-1,0),  colors.white),
        ("FONTNAME",      (0,0), (-1,0),  "Helvetica-Bold"),
        ("FONTSIZE",      (0,0), (-1,0),  9),
        ("ALIGN",         (0,0), (-1,0),  "CENTER"),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        # Baris data
        ("FONTNAME",      (0,1), (-1,-2), "Helvetica"),
        ("FONTSIZE",      (0,1), (-1,-2), 9),
        ("ALIGN",         (0,1), (0,-1),  "CENTER"),
        ("ALIGN",         (2,1), (2,-2),  "CENTER"),
        ("ALIGN",         (1,1), (1,-2),  "LEFT"),
        ("ALIGN",         (3,1), (3,-2),  "LEFT"),
        ("ROWBACKGROUNDS",(0,1), (-1,-2), [colors.white, COLOR_LIGHT]),
        # Baris total
        ("BACKGROUND",   (0,-1), (-1,-1), COLOR_TOTAL),
        ("FONTNAME",     (0,-1), (-1,-1), "Helvetica-Bold"),
        ("FONTSIZE",     (0,-1), (-1,-1), 8),
        ("SPAN",         (2,-1), (3,-1)),
        # Grid
        ("GRID",          (0,0), (-1,-1), 0.5, COLOR_BORDER),
        ("TOPPADDING",    (0,0), (-1,-1), 5),
        ("BOTTOMPADDING", (0,0), (-1,-1), 5),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
    ]

    # Warnai kolom Status sesuai nilai
    if absensi_list:
        for row_i, ab in enumerate(absensi_list, start=1):
            sv = ab.status.value if hasattr(ab.status, "value") else str(ab.status)
            c  = STATUS_COLOR.get(sv)
            if c:
                ts.append(("TEXTCOLOR", (2, row_i), (2, row_i), c))
                ts.append(("FONTNAME",  (2, row_i), (2, row_i), "Helvetica-Bold"))

    tbl.setStyle(TableStyle(ts))
    elems.append(tbl)
    elems.append(Spacer(1, 0.6*cm))

    # ── Penutup ───────────────────────────────────────────────────────────────
    st_penutup = ParagraphStyle("WPenutup", parent=styles["Normal"],
                                fontSize=9, leading=14, textColor=COLOR_GREY)
    elems.append(Paragraph(
        "Demikian laporan absensi ini dibuat sebagai bahan monitoring "
        "perkembangan kehadiran siswa.",
        st_penutup,
    ))
    elems.append(Spacer(1, 0.5*cm))
    elems.append(HRFlowable(width="100%", thickness=0.5, color=COLOR_BORDER))
    elems.append(Spacer(1, 0.25*cm))

    tanggal_cetak = date.today().strftime("%d %B %Y").replace(
        "January","Januari").replace("February","Februari").replace(
        "March","Maret").replace("April","April").replace(
        "May","Mei").replace("June","Juni").replace(
        "July","Juli").replace("August","Agustus").replace(
        "September","September").replace("October","Oktober").replace(
        "November","November").replace("December","Desember")
    elems.append(Paragraph(f"Tanggal Cetak: {tanggal_cetak}", st_right))

    doc.build(elems)
    buffer.seek(0)
    return buffer.read()
app.include_router(router_laporan)


# ─── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws/{id_akun}")
async def websocket_endpoint(websocket: WebSocket, id_akun: int, token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("id_akun") != id_akun:
            await websocket.close(code=4001)
            return
    except jwt.PyJWTError:
        await websocket.close(code=4001)
        return
    await ws_manager.connect(id_akun, websocket)
    try:
        while True:
            await asyncio.sleep(30)
            await websocket.send_text('{"tipe":"ping"}')
    except (WebSocketDisconnect, Exception):
        pass
    finally:
        ws_manager.disconnect(id_akun, websocket)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)