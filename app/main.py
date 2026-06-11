import asyncio
import json
import logging
import os
import shutil
import uuid
from reportlab.platypus import Image
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


# =============================================================================
# Config
# =============================================================================

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


# =============================================================================
# Auth Helpers
# =============================================================================

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
        id = payload.get("id")
        if id is None:
            raise exc
    except jwt.PyJWTError:
        raise exc

    akun = crud.get_akun(db, id)
    if not akun:
        raise exc

    # Cek apakah device sudah di-force logout
    # Jika device_id di DB sudah NULL, akun ini sudah di-kick
    token_device_id = payload.get("device_id")
    if token_device_id and akun.device_id != token_device_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sesi telah berakhir. Silakan login kembali.",
            headers={"WWW-Authenticate": "Bearer"},
        )

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


def _get_guru_or_403(db: Session, id: int) -> models.Guru:
    guru = crud.get_guru_by_akun(db, id)
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
        wali = crud.get_wali_siswa_by_akun(db, current_user.id)
        if not wali or wali.id_siswa != id_siswa:
            raise HTTPException(status_code=403, detail="Akses ditolak")


# =============================================================================
# Startup
# =============================================================================

@app.on_event("startup")
def seed_master_admin():
    crud.init_firebase()  
    
    db = next(get_db())
    try:
        if not crud.get_akun_by_username(db, "TkQoulansadid"):
            crud.create_admin_with_akun(db, schemas.AdminCreate(username="TkQoulansadid", nama="Admin"))
            logging.info("Akun DEFAULT dibuat")
        for id_k, nama_k in [(1, "TK A"), (2, "TK B")]:
            if not db.get(models.Kelas, id_k):
                db.add(models.Kelas(id_kelas=id_k, nama_kelas=nama_k))
        db.commit()
    finally:
        db.close()

# =============================================================================
# Root
# =============================================================================

@app.get("/", tags=["Root"])
def root():
    return {"message": "Smart School API berjalan!", "docs": "/docs"}


@app.get("/health", tags=["Root"])
def health():
    return {"status": "ok"}


# =============================================================================
# Auth
# =============================================================================

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
        "id":          akun.id,
        "device_id":   akun.device_id,
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


@app.post("/akun/{id}/force-logout", tags=["Akun"])
async def force_logout(
    id: int,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat melakukan logout paksa")
    if id == current_user.id:
        raise HTTPException(status_code=400, detail="Tidak dapat logout paksa akun sendiri")
    berhasil = crud.force_logout_akun(db, id)
    if not berhasil:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan atau sudah offline")

    await ws_manager.kirim_ke_akun(id, {
        "type": "force_logout",
        "message": "Sesi Anda telah diakhiri oleh Admin.",
    })
    return {"message": "Logout paksa berhasil"}


@app.get("/auth/me", tags=["Auth"])
def me(current_user: models.Akun = Depends(get_current_user)):
    return current_user


# =============================================================================
# Akun
# =============================================================================

@app.get("/akun/", response_model=List[schemas.AkunOut], tags=["Akun"])
def list_akun(skip=0, limit=100, db: Session = Depends(get_db), _=Depends(require_admin)):
    return crud.get_all_akun(db, skip, limit)


@app.get("/akun/by-username/{username}", response_model=schemas.AkunOut, tags=["Akun"])
def get_akun_by_username(username: str, db: Session = Depends(get_db)):
    akun = crud.get_akun_by_username(db, username)
    if not akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return akun


@app.get("/akun/{id}", response_model=schemas.AkunOut, tags=["Akun"])
def get_akun(id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    akun = crud.get_akun(db, id)
    if not akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return akun


@app.put("/akun/{id}", response_model=schemas.AkunOut, tags=["Akun"])
def update_akun(id: int, akun: schemas.AkunUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    obj = crud.update_akun(db, id, akun)
    if not obj:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return obj


@app.delete("/akun/{id}", tags=["Akun"])
def delete_akun(id: int, db: Session = Depends(get_db), _=Depends(require_admin)):
    if not crud.delete_akun(db, id):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return {"message": f"Akun {id} berhasil dihapus"}


@app.post("/akun/{id}/selesai-setup", response_model=schemas.AkunOut, tags=["Akun"])
def selesai_setup(id: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin and current_user.id != id:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    akun = crud.get_akun(db, id)
    if not akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    akun.first_login = False
    db.commit()
    db.refresh(akun)
    return akun


@app.post("/akun/{id}/ganti-password-firstlogin", response_model=schemas.AkunOut, tags=["Akun"])
def ganti_password_first_login(id: int, payload: schemas.GantiPasswordFirstLoginRequest, db: Session = Depends(get_db)):
    akun = crud.get_akun(db, id)
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


# =============================================================================
# Reset Password
# =============================================================================

@app.post("/reset-password/", response_model=schemas.ResetPasswordOut, status_code=201, tags=["Reset Password"])
def create_reset_password(rp: schemas.ResetPasswordCreate, db: Session = Depends(get_db)):
    if not crud.get_akun(db, rp.id_akun):                 
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    if crud.get_reset_password_by_akun(db, rp.id_akun):  
        raise HTTPException(status_code=400, detail="Pertanyaan keamanan sudah ada")
    return crud.create_reset_password(db, rp)


@app.get("/reset-password/akun/{id}", response_model=schemas.ResetPasswordOut, tags=["Reset Password"])
def get_pertanyaan_by_akun(id: int, db: Session = Depends(get_db)):
    if not crud.get_akun(db, id):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    obj = crud.get_reset_password_by_akun(db, id)
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


# =============================================================================
# Kelas
# =============================================================================

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


# =============================================================================
# Guru
# =============================================================================

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
    obj = crud.get_guru_by_akun(db, current_user.id)
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


# =============================================================================
# Admin
# =============================================================================

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


# =============================================================================
# Kepala Sekolah
# =============================================================================

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


# =============================================================================
# Siswa
# =============================================================================

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


@app.get("/siswa/kelas/{id_kelas}", response_model=List[schemas.SiswaOut], tags=["Siswa"])
def get_siswa_by_kelas(
    id_kelas: int,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    """Ambil daftar siswa berdasarkan kelas.
    Dapat diakses oleh: admin, kepala_sekolah, dan guru (yang punya akses ke kelas tersebut).
    """
    if not crud.get_kelas(db, id_kelas):
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")

    if current_user.role == models.RoleEnum.guru:
        guru = _get_guru_or_403(db, current_user.id)
        _cek_guru_akses_kelas(guru, id_kelas)
    elif current_user.role not in (
        models.RoleEnum.admin,
        models.RoleEnum.kepala_sekolah,
    ):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    siswa_list = (
        db.query(models.Siswa)
        .filter(models.Siswa.id_kelas == id_kelas)
        .order_by(models.Siswa.nama_siswa)
        .all()
    )
    return siswa_list


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


# =============================================================================
# Wali Siswa
# =============================================================================

@app.put("/wali-siswa/{id_wali_siswa}", response_model=schemas.WaliSiswaOut, tags=["Wali Siswa"])
def update_wali_siswa(id_wali_siswa: int, data: schemas.WaliSiswaUpdate, db: Session = Depends(get_db), _=Depends(require_admin)):
    obj = crud.update_wali_siswa(db, id_wali_siswa, data)
    if not obj:
        raise HTTPException(status_code=404, detail="Wali siswa tidak ditemukan")
    return obj


@app.get("/wali-siswa/by-akun/{id}", response_model=schemas.WaliSiswaOut, tags=["Wali Siswa"])
def get_wali_by_akun(id: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role == models.RoleEnum.wali_siswa and current_user.id != id:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    obj = crud.get_wali_siswa_by_akun(db, id)
    if not obj:
        raise HTTPException(status_code=404, detail="Data wali tidak ditemukan")
    return obj


# =============================================================================
# Pesan
# =============================================================================

@app.post("/pesan/", response_model=schemas.PesanOut, status_code=201, tags=["Pesan"])
def kirim_pesan(data: schemas.PesanCreate, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if not crud.get_akun(db, data.id_penerima):
        raise HTTPException(status_code=404, detail="Penerima tidak ditemukan")
    pesan = models.Pesan(
        id_pengirim=current_user.id,
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
        id_pengirim=current_user.id,
        id_pesan=pesan.id_pesan,
        payload_ws={
            "type": "pesan_baru",   # ← tambah ini
            "data": {
                "id_pesan":      pesan.id_pesan,
                "id_pengirim":   pesan.id_pengirim,
                "id_penerima":   pesan.id_penerima,
                "isi_pesan":     pesan.isi_pesan,
                "waktu":         str(pesan.waktu),
                "waktu_millis":  int(pesan.waktu.timestamp() * 1000),
                "nama_pengirim": current_user.nama,
            }
        },
    )
    return pesan



@app.get("/pesan/riwayat/{id_a}/{id_b}", response_model=List[schemas.PesanOutWithEdit], tags=["Pesan"])
def get_riwayat_percakapan(
    id_a: int, id_b: int,
    after_id: Optional[int] = Query(None),
    before_id: Optional[int] = Query(None),
    order: str = Query("asc"),
    skip: int = Query(0),
    limit: int = Query(30),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if current_user.id not in (id_a, id_b):
        raise HTTPException(status_code=403, detail="Akses ditolak")
 
    kedua_arah = or_(
        and_(models.Pesan.id_pengirim == id_a, models.Pesan.id_penerima == id_b),
        and_(models.Pesan.id_pengirim == id_b, models.Pesan.id_penerima == id_a),
    )
 
    filter_tidak_dihapus = ~(
        ((models.Pesan.id_pengirim == current_user.id) & models.Pesan.dihapus_pengirim) |
        ((models.Pesan.id_penerima == current_user.id) & models.Pesan.dihapus_penerima)
    )
 
    # ── Polling ───────────────────────────────────────────────────────────────
    if after_id is not None:
        hasil = (
            db.query(models.Pesan)
            .filter(kedua_arah, filter_tidak_dihapus, models.Pesan.id_pesan > after_id)
            .order_by(models.Pesan.waktu.asc()).all()
        )
        return _serialize_pesan_list(hasil)
 
    # ── Tandai diterima saat fetch awal ───────────────────────────────────────
    if before_id is None:
        lawan_id = id_b if current_user.id == id_a else id_a
        db.query(models.Pesan).filter(
            models.Pesan.id_pengirim == lawan_id,
            models.Pesan.id_penerima == current_user.id,
            models.Pesan.status == models.StatusPesanEnum.terkirim,
        ).update({"status": models.StatusPesanEnum.diterima}, synchronize_session=False)
        db.commit()
 
    total = db.query(models.Pesan).filter(kedua_arah, filter_tidak_dihapus).count()
 
    q = db.query(models.Pesan).filter(kedua_arah, filter_tidak_dihapus)
 
    if before_id is not None:
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
    return JSONResponse(
        content=_serialize_pesan_list(hasil),
        headers={"X-Total-Count": str(total)},
    )
 
 
def _serialize_pesan_list(pesan_list) -> list:
    """
    Serialisasi list Pesan ke dict dengan waktu_millis yang benar.
 
    datetime dari SQLAlchemy bersifat naive (tanpa tzinfo). MySQL TIMESTAMP
    menyimpan UTC. Supaya Android tahu waktu UTC-nya, kita tambahkan
    waktu_millis = epoch ms dengan asumsi naive datetime = UTC.
    """
    from datetime import timezone
    from fastapi.encoders import jsonable_encoder
 
    result = []
    for p in pesan_list:
        item = jsonable_encoder(p)
        # Hitung waktu_millis: naive datetime dari DB = UTC → beri tzinfo UTC dulu
        if p.waktu:
            waktu_utc = p.waktu.replace(tzinfo=timezone.utc)
            item["waktu_millis"] = int(waktu_utc.timestamp() * 1000)
        else:
            item["waktu_millis"] = None
        # Lakukan hal yang sama untuk waktu_edit (opsional, untuk konsistensi)
        if getattr(p, "waktu_edit", None):
            waktu_edit_utc = p.waktu_edit.replace(tzinfo=timezone.utc)
            item["waktu_edit_millis"] = int(waktu_edit_utc.timestamp() * 1000)
        result.append(item)
    return result

@app.put("/pesan/baca", tags=["Pesan"])
def tandai_dibaca(data: schemas.TandaiBacaRequest, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    db.query(models.Pesan).filter(
        models.Pesan.id_pengirim == data.id_pengirim,
        models.Pesan.id_penerima == current_user.id,
        models.Pesan.status.in_([models.StatusPesanEnum.terkirim, models.StatusPesanEnum.diterima]),
    ).update({"status": models.StatusPesanEnum.dibaca}, synchronize_session=False)
    
    db.query(models.Notifikasi).filter(
        models.Notifikasi.id_akun == current_user.id,
        models.Notifikasi.tipe == models.TipeNotifEnum.pesan,
        models.Notifikasi.ref_id == data.id_pengirim,
        models.Notifikasi.status == models.StatusNotifEnum.belum_dibaca,
    ).update({"status": models.StatusNotifEnum.sudah_dibaca}, synchronize_session=False)
    
    db.commit()
    return {"message": "Pesan ditandai dibaca"}

# ── Edit Pesan ────────────────────────────────────────────────────────────────

@app.put("/pesan/{id_pesan}/edit", response_model=schemas.PesanOut, tags=["Pesan"])
async def edit_pesan(
    id_pesan: int,
    data: schemas.EditPesanRequest,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    pesan = db.get(models.Pesan, id_pesan)
    if not pesan:
        raise HTTPException(status_code=404, detail="Pesan tidak ditemukan")
    if pesan.id_pengirim != current_user.id:
        raise HTTPException(status_code=403, detail="Bukan pesan Anda")
    selisih = datetime.utcnow() - pesan.waktu.replace(tzinfo=None)
    if selisih.total_seconds() > 5 * 60:
        raise HTTPException(status_code=400, detail="Pesan hanya bisa diedit dalam 5 menit")
    pesan.isi_pesan  = data.isi_pesan.strip()
    pesan.waktu_edit = datetime.utcnow()
    db.commit()
    db.refresh(pesan)
    await ws_manager.kirim_ke_akun(pesan.id_penerima, {
        "type":     "pesan_diedit",
        "id_pesan": pesan.id_pesan,
        "isi_baru": pesan.isi_pesan,
    })
    return pesan


# ── Hapus untuk Saya ─────────────────────────────────────────────────────────

@app.delete("/pesan/{id_pesan}/saya", tags=["Pesan"])
def hapus_pesan_saya(
    id_pesan: int,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    pesan = db.get(models.Pesan, id_pesan)
    if not pesan:
        raise HTTPException(status_code=404, detail="Pesan tidak ditemukan")

    if pesan.id_pengirim == current_user.id:
        pesan.dihapus_pengirim = True
    elif pesan.id_penerima == current_user.id:
        pesan.dihapus_penerima = True
    else:
        raise HTTPException(status_code=403, detail="Akses ditolak")

    if pesan.dihapus_pengirim and pesan.dihapus_penerima:
        db.delete(pesan)
        db.commit()
        return {"message": "Pesan dihapus permanen"}

    db.commit()
    return {"message": "Pesan dihapus untuk Anda"}

# ── Hapus untuk Semua ─────────────────────────────────────────────────────────

@app.delete("/pesan/{id_pesan}/semua", tags=["Pesan"])
async def hapus_pesan_semua(
    id_pesan: int,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    pesan = db.get(models.Pesan, id_pesan)
    if not pesan:
        raise HTTPException(status_code=404, detail="Pesan tidak ditemukan")
    if pesan.id_pengirim != current_user.id:
        raise HTTPException(status_code=403, detail="Hanya pengirim yang bisa hapus untuk semua")
    id_penerima = pesan.id_penerima
    db.delete(pesan)
    db.commit()
    await ws_manager.kirim_ke_akun(id_penerima, {
        "type":     "pesan_dihapus",
        "id_pesan": id_pesan,
    })
    return {"message": "Pesan dihapus untuk semua"}

@app.get("/pesan/percakapan/{id}", response_model=List[schemas.PercakapanItem], tags=["Pesan"])
def get_daftar_percakapan(id: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.id != id:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    semua_pesan = (
        db.query(models.Pesan)
        .filter(
            or_(models.Pesan.id_pengirim == id, models.Pesan.id_penerima == id),
            ~(
                ((models.Pesan.id_pengirim == id) & models.Pesan.dihapus_pengirim) |
                ((models.Pesan.id_penerima == id) & models.Pesan.dihapus_penerima)
            )
        )
        .order_by(models.Pesan.waktu.desc()).all()
    )
    hasil, sudah = [], set()
    for p in semua_pesan:
        lawan_id = p.id_penerima if p.id_pengirim == id else p.id_pengirim
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
            models.Pesan.id_penerima == id,
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
            .filter(
                or_(
                    and_(models.Pesan.id_pengirim == current_user.id, models.Pesan.id_penerima == gid),
                    and_(models.Pesan.id_pengirim == gid, models.Pesan.id_penerima == current_user.id),
                ),
                ~(
                    ((models.Pesan.id_pengirim == current_user.id) & models.Pesan.dihapus_pengirim) |
                    ((models.Pesan.id_penerima == current_user.id) & models.Pesan.dihapus_penerima)
                )
            )
            .order_by(models.Pesan.waktu.desc()).first()
        )
        belum = db.query(models.Pesan).filter(
            models.Pesan.id_pengirim == gid,
            models.Pesan.id_penerima == current_user.id,
            models.Pesan.status.in_([
                models.StatusPesanEnum.terkirim,
                models.StatusPesanEnum.diterima,
            ]),
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
    guru = _get_guru_or_403(db, current_user.id)
    allowed_kelas = crud.decode_id_kelas(guru.id_kelas)
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


# =============================================================================
# Absensi
# =============================================================================

@app.get("/absensi/kelas/{id_kelas}", response_model=List[schemas.SiswaAbsensiItem], tags=["Absensi"])
def get_siswa_absensi(id_kelas: int, tanggal: date, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")
    guru = _get_guru_or_403(db, current_user.id)
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
    guru = _get_guru_or_403(db, current_user.id)
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


@app.get("/absensi/siswa/{id_siswa}/ringkasan", response_model=schemas.RingkasanAbsensiOut, tags=["Absensi"])
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


# =============================================================================
# Catatan Harian
# =============================================================================

@app.post("/catatan/", response_model=schemas.CatatanHarianOut, status_code=201, tags=["Catatan Harian"])
def buat_catatan(
    payload: schemas.CatatanHarianCreate,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat membuat catatan")
    guru = _get_guru_or_403(db, current_user.id)
    catatan = crud.create_catatan_harian(db, payload, guru.id_guru)
    crud.kirim_notif_catatan(db, catatan, current_user.nama)
    return crud._build_catatan_out(catatan)


@app.get("/catatan/siswa/{id_siswa}", response_model=schemas.CatatanListResponse, tags=["Catatan Harian"])
def get_catatan_siswa(id_siswa: int, skip=0, limit=20, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    siswa = crud.get_siswa(db, id_siswa)
    if not siswa:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    if current_user.role == models.RoleEnum.wali_siswa:
        wali = crud.get_wali_siswa_by_akun(db, current_user.id)
        if not wali or wali.id_siswa != id_siswa:
            raise HTTPException(status_code=403, detail="Anda hanya dapat melihat catatan anak Anda")
    catatan_list = crud.get_catatan_by_siswa(db, id_siswa, siswa.id_kelas, skip, limit)
    return schemas.CatatanListResponse(total=len(catatan_list), data=[crud._build_catatan_out(c) for c in catatan_list])


@app.get("/catatan/guru/", response_model=schemas.CatatanListResponse, tags=["Catatan Harian"])
def get_catatan_by_guru_login(skip=0, limit=50, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")
    guru = _get_guru_or_403(db, current_user.id)
    catatan_list = crud.get_catatan_by_guru(db, guru.id_guru, skip, limit)
    return schemas.CatatanListResponse(total=len(catatan_list), data=[crud._build_catatan_out(c) for c in catatan_list])


@app.get("/catatan/{id_catatan}", response_model=schemas.CatatanHarianOut, tags=["Catatan Harian"])
def get_catatan_detail(id_catatan: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    catatan = crud.get_catatan_harian(db, id_catatan)
    if not catatan:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    if current_user.role == models.RoleEnum.wali_siswa:
        wali  = crud.get_wali_siswa_by_akun(db, current_user.id)
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
    guru = _get_guru_or_403(db, current_user.id)
    if catatan.id_guru != guru.id_guru:
        raise HTTPException(status_code=403, detail="Anda bukan pembuat catatan ini")
    return crud._build_catatan_out(crud.update_catatan_harian(db, id_catatan, payload))


@app.delete("/catatan/{id_catatan}", tags=["Catatan Harian"])
def delete_catatan(id_catatan: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    catatan = crud.get_catatan_harian(db, id_catatan)
    if not catatan:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    if current_user.role == models.RoleEnum.guru:
        guru = _get_guru_or_403(db, current_user.id)
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
    guru = _get_guru_or_403(db, current_user.id)
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


# =============================================================================
# Notifikasi
# =============================================================================

@app.get("/notifikasi/", response_model=schemas.NotifikasiListResponse, tags=["Notifikasi"])
def get_notifikasi(skip=0, limit=50, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    return schemas.NotifikasiListResponse(
        total_belum_dibaca=crud.count_notif_belum_dibaca(db, current_user.id),
        data=crud.get_notifikasi_by_akun(db, current_user.id, skip, limit),
    )


@app.put("/notifikasi/baca", tags=["Notifikasi"])
def tandai_notif_dibaca(payload: schemas.BacaNotifRequest, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    jumlah = crud.tandai_notif_dibaca(db, current_user.id, payload.id_notif)
    return {"message": f"{jumlah} notifikasi ditandai sudah dibaca", "jumlah": jumlah}


# =============================================================================
# Laporan (router)
#
# Urutan route PENTING — spesifik dulu, baru /{id_laporan}.
# FastAPI membaca dari atas ke bawah; "/{id_laporan}" akan menangkap
# "/absensi", "/catatan", "/guru/", "/pdf/..." jika diletakkan lebih atas.
# =============================================================================

@router_laporan.post("/", response_model=schemas.LaporanOut, status_code=201, summary="Guru membuat laporan baru untuk satu kelas")
def buat_laporan(payload: schemas.LaporanCreate, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat membuat laporan")
    guru = _get_guru_or_403(db, current_user.id)
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
    guru = _get_guru_or_403(db, current_user.id)
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
    guru = _get_guru_or_403(db, current_user.id)
    _cek_guru_akses_kelas(guru, id_kelas)
    result = crud.get_laporan_absensi_kelas_range(db, id_kelas, tanggal_awal, tanggal_akhir)
    if not result:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    if result.siswa:
        nisn_map = {s.id_siswa: (s.nisn or "") for s in db.query(models.Siswa).filter(models.Siswa.id_kelas == id_kelas).all()}
        for item in result.siswa:
            if not getattr(item, "nisn", None):
                item.nisn = nisn_map.get(item.id_siswa, "")
    return result


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

    is_admin = current_user.role in (models.RoleEnum.admin, models.RoleEnum.kepala_sekolah)
    if not is_admin:
        guru = _get_guru_or_403(db, current_user.id)
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


@router_laporan.get("/otomatis/siswa/{id_siswa}", response_model=schemas.LaporanSiswaOut,
                    summary="[WALI/GURU/ADMIN] Laporan otomatis satu siswa (absensi + catatan)")
def get_laporan_otomatis_siswa(
    id_siswa: int,
    bulan: int = Query(..., ge=1, le=12, description="Bulan (1-12)"),
    tahun: int = Query(..., ge=2000, description="Tahun, contoh: 2025"),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    _cek_wali_akses_siswa(db, current_user, id_siswa)
    result = crud.get_laporan_otomatis_siswa(db, id_siswa, bulan, tahun)
    if not result:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return result


@router_laporan.get("/otomatis/kelas/{id_kelas}", response_model=schemas.LaporanKelasOut,
                    summary="[GURU/ADMIN] Laporan otomatis satu kelas (rekap absensi semua siswa)")
def get_laporan_otomatis_kelas(
    id_kelas: int,
    bulan: int = Query(..., ge=1, le=12, description="Bulan (1-12)"),
    tahun: int = Query(..., ge=2000, description="Tahun, contoh: 2025"),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    is_admin = current_user.role in (models.RoleEnum.admin, models.RoleEnum.kepala_sekolah)
    if not is_admin:
        guru = _get_guru_or_403(db, current_user.id)
        _cek_guru_akses_kelas(guru, id_kelas)
    result = crud.get_laporan_otomatis_kelas(db, id_kelas, bulan, tahun)
    if not result:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return result


@router_laporan.get("/pdf/absensi", summary="Generate PDF buku absensi harian kelas (per bulan)")
def download_pdf_absensi(
    id_kelas: int   = Query(...),
    bulan:    int   = Query(..., ge=1, le=12, description="Bulan (1-12)"),
    tahun:    int   = Query(..., ge=2000,     description="Tahun, contoh: 2025"),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    import calendar as _cal
    from datetime import date as _date

    if current_user.role in (models.RoleEnum.admin, models.RoleEnum.kepala_sekolah):
        if not db.get(models.Kelas, id_kelas):
            raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    else:
        guru = _get_guru_or_403(db, current_user.id)
        _cek_guru_akses_kelas(guru, id_kelas)

    tanggal_awal  = _date(tahun, bulan, 1)
    hari_terakhir = _cal.monthrange(tahun, bulan)[1]
    tanggal_akhir = _date(tahun, bulan, hari_terakhir)

    data = crud.get_laporan_absensi_kelas_range(db, id_kelas, tanggal_awal, tanggal_akhir)
    if not data:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")

    if data.siswa:
        nisn_map = {s.id_siswa: (s.nisn or "") for s in
                    db.query(models.Siswa).filter(models.Siswa.id_kelas == id_kelas).all()}
        for item in data.siswa:
            if not getattr(item, "nisn", None):
                item.nisn = nisn_map.get(item.id_siswa, "")

    detail_map: dict[int, dict[int, str]] = {}
    absensi_rows = (
        db.query(models.Absensi)
        .filter(
            models.Absensi.id_siswa.in_([s.id_siswa for s in data.siswa]),
            models.Absensi.tanggal >= tanggal_awal,
            models.Absensi.tanggal <= tanggal_akhir,
        )
        .all()
    )
    SIMBOL = {"hadir": ".", "sakit": "S", "izin": "I", "alpha": "A"}
    for ab in absensi_rows:
        sv = ab.status.value if hasattr(ab.status, "value") else str(ab.status)
        detail_map.setdefault(ab.id_siswa, {})[ab.tanggal.day] = SIMBOL.get(sv, "")

    NAMA_BULAN_ID = ["", "Januari","Februari","Maret","April","Mei","Juni",
                     "Juli","Agustus","September","Oktober","November","Desember"]

    pdf_bytes = _generate_pdf_absensi_harian(
        data, detail_map, hari_terakhir, bulan, tahun, NAMA_BULAN_ID[bulan]
    )
    nama_file = f"absensi_{data.nama_kelas}_{NAMA_BULAN_ID[bulan]}_{tahun}.pdf".replace(" ", "_")
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nama_file}"'},
    )


@router_laporan.get("/pdf/catatan", summary="[GURU/ADMIN] Generate PDF laporan catatan harian satu siswa")
def download_pdf_catatan(
    id_siswa: int = Query(...),
    bulan:    int = Query(..., ge=1, le=12, description="Bulan (1-12)"),
    tahun:    int = Query(..., ge=2000,     description="Tahun, contoh: 2025"),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    import calendar as _cal
    from datetime import date as _date

    is_admin = current_user.role in (models.RoleEnum.admin, models.RoleEnum.kepala_sekolah)
    siswa = db.get(models.Siswa, id_siswa)
    if not siswa:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    if not is_admin:
        guru = _get_guru_or_403(db, current_user.id)
        if siswa.id_kelas is not None:
            _cek_guru_akses_kelas(guru, siswa.id_kelas)

    tanggal_awal  = _date(tahun, bulan, 1)
    hari_terakhir = _cal.monthrange(tahun, bulan)[1]
    tanggal_akhir = _date(tahun, bulan, hari_terakhir)

    nama_kelas   = siswa.kelas.nama_kelas if siswa.kelas else "-"
    catatan_list = crud.get_catatan_siswa_range(db, id_siswa, tanggal_awal, tanggal_akhir)
    catatan_out  = [
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

    NAMA_BULAN_ID = ["","Januari","Februari","Maret","April","Mei","Juni",
                     "Juli","Agustus","September","Oktober","November","Desember"]

    pdf_bytes = _generate_pdf_catatan(data_siswa, nama_kelas, tanggal_awal, tanggal_akhir)
    nama_file = (
        f"catatan_{siswa.nama_siswa}_{NAMA_BULAN_ID[bulan]}_{tahun}.pdf"
        .replace(" ", "_")
    )
    return StreamingResponse(
        BytesIO(pdf_bytes), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nama_file}"'},
    )


# /{id_laporan} harus paling bawah — jangan pindahkan ke atas

@router_laporan.get("/{id_laporan}", response_model=schemas.LaporanOut, summary="Detail satu laporan")
def get_laporan_detail(id_laporan: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    lap = crud.get_laporan(db, id_laporan)
    if not lap:
        raise HTTPException(status_code=404, detail="Laporan tidak ditemukan")
    if current_user.role == models.RoleEnum.guru:
        guru = _get_guru_or_403(db, current_user.id)
        if lap.id_guru != guru.id_guru:
            raise HTTPException(status_code=403, detail="Akses ditolak")
    return crud._build_laporan_out(lap)


@router_laporan.delete("/{id_laporan}", summary="Hapus laporan (guru pemilik atau admin)")
def hapus_laporan(id_laporan: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    lap = crud.get_laporan(db, id_laporan)
    if not lap:
        raise HTTPException(status_code=404, detail="Laporan tidak ditemukan")
    if current_user.role == models.RoleEnum.guru:
        guru = _get_guru_or_403(db, current_user.id)
        if lap.id_guru != guru.id_guru:
            raise HTTPException(status_code=403, detail="Anda bukan pembuat laporan ini")
    elif current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    crud.delete_laporan(db, id_laporan)
    return {"message": f"Laporan {id_laporan} berhasil dihapus"}


@router_laporan.put("/{id_laporan}/verifikasi")
def verifikasi_laporan(
    id_laporan: int,
    payload: schemas.LaporanVerifikasi,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if current_user.role not in (models.RoleEnum.admin, models.RoleEnum.kepala_sekolah):
        raise HTTPException(
            status_code=403,
            detail="Hanya admin atau kepala sekolah yang dapat memverifikasi laporan",
        )

    lap = crud.verifikasi_laporan(db, id_laporan, payload)
    if not lap:
        raise HTTPException(status_code=404, detail="Laporan tidak ditemukan")

    # Kirim notifikasi ke wali hanya saat status menjadi 'verifikasi'
    if payload.status == models.StatusLaporanEnum.verifikasi:
        crud.kirim_notif_laporan_terverifikasi(
            db,
            lap,
            nama_admin=current_user.nama,
        )

    return crud._build_laporan_out(lap)

@router_laporan.get("/wali/", response_model=schemas.LaporanListResponse,
                    summary="[WALI SISWA] Daftar laporan terverifikasi milik kelas anaknya")
def list_laporan_wali(
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if current_user.role != models.RoleEnum.wali_siswa:
        raise HTTPException(status_code=403, detail="Hanya wali siswa yang dapat mengakses")
 
    # Ambil data wali → siswa → id_kelas
    wali = crud.get_wali_siswa_by_akun(db, current_user.id)
    if not wali or not wali.id_siswa:
        return schemas.LaporanListResponse(total=0, total_selesai=0, total_belum=0, data=[])
 
    siswa = crud.get_siswa(db, wali.id_siswa)
    id_kelas = siswa.id_kelas if siswa else None
 
    # Ambil semua laporan, filter: sudah verifikasi + kelas sesuai siswa wali
    semua = crud.get_all_laporan(db, skip=0, limit=1000)
    data = [
        l for l in semua
        if l.status == models.StatusLaporanEnum.verifikasi
        and (id_kelas is None or l.id_kelas == id_kelas)
    ]
 
    # Terapkan skip & limit setelah filter
    data = data[skip: skip + limit]
 
    stat = crud._hitung_statistik_laporan(data)
    return schemas.LaporanListResponse(
        **stat,
        data=[crud._build_laporan_out(l) for l in data],
    )
 

# =============================================================================
# Register Router
# =============================================================================

app.include_router(router_laporan)


# =============================================================================
# PDF Generator — Buku Absensi Harian Kelas
# =============================================================================

def _generate_pdf_absensi_harian(
    data,           # schemas.LaporanAbsensiKelasOut
    detail_map,     # {id_siswa: {hari: simbol}}
    hari_terakhir,  # int: jumlah hari di bulan
    bulan,          # int
    tahun,          # int
    nama_bulan,     # str, misal "Mei"
) -> bytes:
    import calendar as _cal
    from datetime import date as _date

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        topMargin=1*cm, bottomMargin=1.2*cm,
        leftMargin=1*cm, rightMargin=1*cm,
    )
    styles  = getSampleStyleSheet()
    C_BLACK = colors.black
    C_WHITE = colors.white

    st_judul = ParagraphStyle("Judul", parent=styles["Heading1"],
                              alignment=TA_CENTER, fontSize=13, spaceAfter=2,
                              textColor=C_BLACK, fontName="Helvetica-Bold")
    st_cell  = ParagraphStyle("Cell",  parent=styles["Normal"],
                              fontSize=6.5, leading=8, alignment=TA_CENTER)
    st_name  = ParagraphStyle("Name",  parent=styles["Normal"],
                              fontSize=7, leading=9)
    st_rekap = ParagraphStyle("Rekap", parent=styles["Normal"],
                              fontSize=8, leading=12)

    PAGE_W = 27.7 * cm

    elems = []

    # ── Judul ──
    elems.append(Paragraph("BUKU ABSENSI HARIAN ANAK", st_judul))

    # ── Subtitle: Kelompok kiri, Bulan kanan ──
    sub_tbl = Table(
        [[Paragraph(f"Kelompok : {data.nama_kelas}",
                    ParagraphStyle("SL", parent=styles["Normal"], fontSize=9)),
          Paragraph(f"Bulan : {nama_bulan}, {tahun}",
                    ParagraphStyle("SR", parent=styles["Normal"], fontSize=9, alignment=2))]],
        colWidths=[PAGE_W * 0.5, PAGE_W * 0.5]
    )
    sub_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))
    elems.append(sub_tbl)
    elems.append(Spacer(1, 0.3*cm))

    # ── Lebar kolom ──
    W_NO   = 0.55 * cm
    W_NAMA = 3.8  * cm
    W_S    = 0.6  * cm
    W_I    = 0.6  * cm
    W_A    = 0.6  * cm
    W_KET  = 2.2  * cm
    sisa   = PAGE_W - W_NO - W_NAMA - W_S - W_I - W_A - W_KET
    W_TGL  = sisa / hari_terakhir

    col_widths = [W_NO, W_NAMA] + [W_TGL] * hari_terakhir + [W_S, W_I, W_A, W_KET]
    tgl_end    = 1 + hari_terakhir  # index kolom terakhir tanggal (0-based)

    # ── 2 baris header ──
    hdr1 = (
        [Paragraph("NO",              st_cell),
         Paragraph("NAMA SISWA",      st_cell)]
        + [Paragraph("TANGGAL ABSENSI", st_cell)] + [""] * (hari_terakhir - 1)
        + [Paragraph("S",             st_cell),
           Paragraph("I",             st_cell),
           Paragraph("A",             st_cell),
           Paragraph("Keterangan",    st_cell)]
    )
    hdr2 = (
        [Paragraph("", st_cell), Paragraph("", st_cell)]
        + [Paragraph(str(d), st_cell) for d in range(1, hari_terakhir + 1)]
        + [Paragraph("", st_cell)] * 4
    )

    siswa_list = sorted(data.siswa, key=lambda s: s.nama_siswa)
    rows = [hdr1, hdr2]

    for idx, siswa in enumerate(siswa_list, start=1):
        ab = detail_map.get(siswa.id_siswa, {})
        row = [Paragraph(str(idx), st_cell), Paragraph(siswa.nama_siswa, st_name)]
        row += [Paragraph(ab.get(d, ""), st_cell) for d in range(1, hari_terakhir + 1)]
        row += [
            Paragraph(str(siswa.sakit), st_cell),
            Paragraph(str(siswa.izin),  st_cell),
            Paragraph(str(siswa.alpha), st_cell),
            Paragraph("",               st_cell),
        ]
        rows.append(row)

    n_data = len(siswa_list)

    tbl = Table(rows, colWidths=col_widths, repeatRows=2)
    tbl.setStyle(TableStyle([
        # merge header baris-1
        ("SPAN", (0, 0),         (0, 1)),           # NO
        ("SPAN", (1, 0),         (1, 1)),           # NAMA SISWA
        ("SPAN", (2, 0),         (tgl_end, 0)),     # TANGGAL ABSENSI
        ("SPAN", (tgl_end+1, 0), (tgl_end+1, 1)),  # S
        ("SPAN", (tgl_end+2, 0), (tgl_end+2, 1)),  # I
        ("SPAN", (tgl_end+3, 0), (tgl_end+3, 1)),  # A
        ("SPAN", (tgl_end+4, 0), (tgl_end+4, 1)),  # Keterangan
        # header style
        ("FONTNAME",      (0, 0), (-1, 1),  "Helvetica-Bold"),
        ("FONTSIZE",      (0, 0), (-1, 1),  6.5),
        ("ALIGN",         (0, 0), (-1, 1),  "CENTER"),
        ("VALIGN",        (0, 0), (-1, 1),  "MIDDLE"),
        ("BACKGROUND",    (0, 0), (-1, 1),  C_WHITE),
        # data rows
        ("FONTNAME",      (0, 2), (-1, -1), "Helvetica"),
        ("FONTSIZE",      (0, 2), (-1, -1), 6.5),
        ("ALIGN",         (0, 2), (0, -1),  "CENTER"),
        ("ALIGN",         (1, 2), (1, -1),  "LEFT"),
        ("ALIGN",         (2, 2), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 2), (-1, -1), "MIDDLE"),
        ("BACKGROUND",    (0, 2), (-1, -1), C_WHITE),
        # grid
        ("GRID",          (0, 0), (-1, -1), 0.5, C_BLACK),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ("LEFTPADDING",   (0, 0), (-1, -1), 1),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 1),
        ("ROWHEIGHT",     (0, 0), (-1, -1), 0.52 * cm),
    ]))
    elems.append(tbl)
    elems.append(Spacer(1, 0.4*cm))

    # ── Rekap kiri sejajar ujung kiri tabel, TTD mentok kanan ──
    W_REKAP = W_NO + W_NAMA
    rekap_data = [
        [Paragraph(f"Hadir : {data.total_hadir}", st_rekap)],
        [Paragraph(f"Sakit : {data.total_sakit}", st_rekap)],
        [Paragraph(f"Izin  : {data.total_izin}",  st_rekap)],
        [Paragraph(f"Alpha : {data.total_alpha}", st_rekap)],
    ]
    rekap_tbl = Table(rekap_data, colWidths=[W_REKAP])
    rekap_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
    ]))

    W_TTD = 5.0 * cm
    W_MID = PAGE_W - W_REKAP - W_TTD

    ttd_content = Paragraph(
        f"{nama_bulan} {tahun}<br/><br/>"
        f"Kepala Sekolah<br/><br/><br/>"
        f"(………………………………………)",
        ParagraphStyle("TTD", parent=styles["Normal"], fontSize=8, alignment=TA_CENTER))

    outer = Table(
        [[rekap_tbl, Paragraph("", styles["Normal"]), ttd_content]],
        colWidths=[W_REKAP, W_MID, W_TTD]
    )
    outer.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    elems.append(outer)

    doc.build(elems)
    buffer.seek(0)
    return buffer.read()

def _generate_pdf_catatan(
    data: schemas.LaporanCatatanSiswaOut,
    nama_kelas: str,
    tanggal_awal: date,
    tanggal_akhir: date,
) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=1.5*cm, bottomMargin=1.5*cm,
        leftMargin=2*cm,  rightMargin=2*cm,
    )
    styles = getSampleStyleSheet()

    NAMA_BULAN_ID = ["","Januari","Februari","Maret","April","Mei","Juni",
                     "Juli","Agustus","September","Oktober","November","Desember"]

    def fmt_tgl(d: date) -> str:
        return f"{d.day:02d} {NAMA_BULAN_ID[d.month]} {d.year}"

    st_kop  = ParagraphStyle("Kop",  parent=styles["Normal"],
                              alignment=TA_CENTER, fontSize=10,
                              leading=14, textColor=colors.black)
    st_info = ParagraphStyle("Info", parent=styles["Normal"],
                              fontSize=10, spaceAfter=4, leftIndent=0)
    st_cell = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=9, leading=12)

    # --- Header kop surat ---
    LOGO_PATH = os.path.join(os.path.dirname(__file__), "qoulansadid.png")
    logo_img  = Image(LOGO_PATH, width=3*cm, height=3*cm)

    header_text = Paragraph(
        "<b>LAPORAN CATATAN HARIAN SISWA</b><br/>"
        "TK Qoulansadid<br/>"
        "<font size='8'>Jl. Suban Mas Kel. Patih Galung Kec. Prabumulih Barat "
        "Kota Prabumulih, Sumatera Selatan</font>",
        st_kop
    )

    LOGO_W = 3.2 * cm
    PAGE_W = 17.0 * cm
    MID_W  = PAGE_W - (LOGO_W * 2)

    kop_tbl = Table(
        [[logo_img, header_text, Paragraph("", styles["Normal"])]],
        colWidths=[LOGO_W, MID_W, LOGO_W]
    )
    kop_tbl.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))

    elems = []
    elems.append(kop_tbl)
    elems.append(Spacer(1, 0.2*cm))
    elems.append(HRFlowable(width="100%", thickness=1, color=colors.black))
    elems.append(Spacer(1, 0.5*cm))
    elems.append(Paragraph(f"Nama Siswa : {data.nama_siswa}", st_info))
    elems.append(Paragraph(f"Kelas      : {nama_kelas}", st_info))
    elems.append(Paragraph(
        f"Periode    : {fmt_tgl(tanggal_awal)} s/d {fmt_tgl(tanggal_akhir)}", st_info))
    elems.append(Spacer(1, 0.4*cm))

    col_w = [0.8*cm, 2.2*cm, 3*cm, 7*cm, 3*cm]

    if not data.catatan:
        st_empty = ParagraphStyle("Empty", parent=styles["Normal"],
                                  alignment=TA_CENTER, fontSize=10,
                                  textColor=colors.black)
        elems.append(Paragraph("Tidak ada catatan harian dalam periode ini.", st_empty))
    else:
        st_header = ParagraphStyle("Header", parent=styles["Normal"],
                                   fontSize=9, leading=12,
                                   fontName="Helvetica-Bold")
        rows = [
            [Paragraph(h, st_header) for h in ["No", "Tanggal", "Judul", "Catatan", "Saran"]]
        ]
        for i, catatan in enumerate(data.catatan, start=1):
            tgl_str = (catatan.tanggal.strftime("%d-%m-%Y")
                       if hasattr(catatan.tanggal, "strftime") else str(catatan.tanggal))
            rows.append([
                Paragraph(str(i),               st_cell),
                Paragraph(tgl_str,              st_cell),
                Paragraph(catatan.judul or "-", st_cell),
                Paragraph(catatan.isi   or "-", st_cell),
                Paragraph("",                   st_cell),
            ])

        tbl = Table(rows, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  colors.white),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.black),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0),  9),
            ("ALIGN",         (0, 0), (-1, 0),  "CENTER"),
            ("VALIGN",        (0, 0), (-1, -1), "TOP"),
            ("FONTNAME",      (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE",      (0, 1), (-1, -1), 9),
            ("ALIGN",         (0, 1), (1, -1),  "CENTER"),
            ("ALIGN",         (2, 1), (-1, -1), "LEFT"),
            ("BACKGROUND",    (0, 1), (-1, -1), colors.white),
            ("GRID",          (0, 0), (-1, -1), 0.5, colors.black),
            ("TOPPADDING",    (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING",   (0, 0), (-1, -1), 5),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 5),
        ]))
        elems.append(tbl)

    elems.append(Spacer(1, 1.2*cm))

    bulan_ttd = NAMA_BULAN_ID[tanggal_akhir.month]
    tahun_ttd = tanggal_akhir.year

    st_ttd = ParagraphStyle("TTD", parent=styles["Normal"],
                             fontSize=9, alignment=TA_CENTER, leading=14)
    W_TTD = 9.0 * cm
    W_MID = PAGE_W - W_TTD

    ttd_tbl = Table(
        [
            [Paragraph(f"Prabumulih, {bulan_ttd} {tahun_ttd}", st_ttd)],
            [Paragraph("Kepala Sekolah", st_ttd)],
            [Paragraph("", st_ttd)],
            [Paragraph("", st_ttd)],
            [Paragraph("(………………………………………)", st_ttd)],
        ],
        colWidths=[W_TTD],
        rowHeights=[0.5*cm, 0.5*cm, 0.5*cm, 0.5*cm, 1.5*cm, 0.5*cm]
    )
    ttd_tbl.setStyle(TableStyle([
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))

    outer = Table(
        [[Paragraph("", styles["Normal"]), ttd_tbl]],
        colWidths=[W_MID, W_TTD]
    )
    outer.setStyle(TableStyle([
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",   (0, 0), (-1, -1), 0),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 0),
        ("TOPPADDING",    (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    elems.append(outer)

    doc.build(elems)
    buffer.seek(0)
    return buffer.read()
# =============================================================================
# WebSocket
# =============================================================================

@app.websocket("/ws/{id}")
async def websocket_endpoint(websocket: WebSocket, id: int, token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        if payload.get("id") != id:
            await websocket.close(code=4001)
            return
    except jwt.PyJWTError:
        await websocket.close(code=4001)
        return

    await ws_manager.connect(id, websocket)
    try:
        while True:
            data = await asyncio.wait_for(
                websocket.receive_text(), timeout=60.0
            )
    except (WebSocketDisconnect, asyncio.TimeoutError, Exception):
        pass
    finally:
        ws_manager.disconnect(id, websocket)


# =============================================================================
# Entry Point
# =============================================================================

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)