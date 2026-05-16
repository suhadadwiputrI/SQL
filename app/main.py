import asyncio
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timedelta, date
from typing import List, Optional

import jwt
import uvicorn
from fastapi import (FastAPI, Depends, HTTPException, Query, Request,
                     UploadFile, File, WebSocket, WebSocketDisconnect, status)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from fastapi.staticfiles import StaticFiles
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
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


# ─── Auth helpers ─────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    payload = {**data, "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme),
                     db: Session = Depends(get_db)) -> models.Akun:
    exc = HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Token tidak valid atau sudah kedaluwarsa",
                        headers={"WWW-Authenticate": "Bearer"})
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

def require_admin(current_user: models.Akun = Depends(get_current_user)) -> models.Akun:
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

def _cek_wali_akses_siswa(db: Session, current_user: models.Akun, id_siswa: int):
    """Raise 403 jika wali siswa mencoba akses data bukan anaknya."""
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Username atau password salah",
                            headers={"WWW-Authenticate": "Bearer"})

    # ── Device lock: tolak login jika akun aktif di device lain ──────────────
    device_id = payload.device_id
    if device_id and akun.device_id and akun.device_id != device_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Akun ini sedang digunakan di perangkat lain. "
                   "Logout terlebih dahulu sebelum login di sini.",
        )

    # Simpan / perbarui device_id
    if device_id:
        akun.device_id = device_id
        db.commit()

    token = create_access_token({
        "id_akun": akun.id_akun, "username": akun.username,
        "role": akun.role.value, "first_login": akun.first_login,
    })
    return {"access_token": token, "token_type": "bearer", "first_login": akun.first_login}

@app.post("/auth/logout", tags=["Auth"])
def logout(db: Session = Depends(get_db),
           current_user: models.Akun = Depends(get_current_user)):
    # Hapus device_id agar akun bisa login di device lain setelah logout
    current_user.device_id = None
    db.commit()
    return {"message": "Logout berhasil"}

@app.get("/auth/me", tags=["Auth"])
def me(current_user: models.Akun = Depends(get_current_user)):
    return current_user


# ─── Akun ─────────────────────────────────────────────────────────────────────

@app.get("/akun/", response_model=List[schemas.AkunOut], tags=["Akun"])
def list_akun(skip=0, limit=100, db: Session = Depends(get_db),
              _=Depends(require_admin)):
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
def update_akun(id_akun: int, akun: schemas.AkunUpdate, db: Session = Depends(get_db),
                _=Depends(require_admin)):
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
def ganti_password_first_login(id_akun: int, payload: schemas.GantiPasswordFirstLoginRequest,
                                db: Session = Depends(get_db)):
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

@app.post("/akun/create-with-role", response_model=schemas.AkunOut,
          status_code=201, tags=["Akun"])
async def create_akun_with_role(request: Request, db: Session = Depends(get_db),
                                _=Depends(require_admin)):
    try:
        body = json.loads(await request.body())
        data = schemas.AkunCreateWithRole(**body)
    except Exception as e:
        raise HTTPException(status_code=422, detail=str(e))

    if crud.get_akun_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="Username sudah digunakan")

    if data.role == schemas.RoleEnum.admin:
        return crud.create_admin_with_akun(
            db, schemas.AdminCreate(username=data.username, nama=data.nama)).akun
    if data.role == schemas.RoleEnum.kepala_sekolah:
        if data.nip and crud.get_kepsek_by_nip(db, data.nip):
            raise HTTPException(status_code=400, detail="NIP sudah terdaftar")
        return crud.create_kepsek_with_akun(
            db, schemas.KepsekCreate(username=data.username, nama=data.nama, nip=data.nip)).akun
    raise HTTPException(status_code=400, detail="Gunakan endpoint /guru/ untuk role guru")


# ─── Reset Password ───────────────────────────────────────────────────────────

@app.post("/reset-password/", response_model=schemas.ResetPasswordOut,
          status_code=201, tags=["Reset Password"])
def create_reset_password(rp: schemas.ResetPasswordCreate, db: Session = Depends(get_db)):
    if not crud.get_akun(db, rp.id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    if crud.get_reset_password_by_akun(db, rp.id_akun):
        raise HTTPException(status_code=400, detail="Pertanyaan keamanan sudah ada")
    return crud.create_reset_password(db, rp)

@app.get("/reset-password/akun/{id_akun}", response_model=schemas.ResetPasswordOut,
         tags=["Reset Password"])
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

@app.post("/reset-password/ganti-password", response_model=schemas.AkunOut,
          tags=["Reset Password"])
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

@app.get("/reset-password/", response_model=List[schemas.ResetPasswordOut],
         tags=["Reset Password"])
def list_reset_password(skip=0, limit=100, db: Session = Depends(get_db),
                        _=Depends(require_admin)):
    return crud.get_all_reset_password(db, skip, limit)

@app.put("/reset-password/{id_pertanyaan}", response_model=schemas.ResetPasswordOut,
         tags=["Reset Password"])
def update_reset_password(id_pertanyaan: int, rp: schemas.ResetPasswordUpdate,
                          db: Session = Depends(get_db)):
    obj = crud.update_reset_password(db, id_pertanyaan, rp)
    if not obj:
        raise HTTPException(status_code=404, detail="Pertanyaan tidak ditemukan")
    return obj

@app.delete("/reset-password/{id_pertanyaan}", tags=["Reset Password"])
def delete_reset_password(id_pertanyaan: int, db: Session = Depends(get_db),
                          _=Depends(require_admin)):
    if not crud.delete_reset_password(db, id_pertanyaan):
        raise HTTPException(status_code=404, detail="Pertanyaan tidak ditemukan")
    return {"message": f"Pertanyaan {id_pertanyaan} berhasil dihapus"}


# ─── Kelas ────────────────────────────────────────────────────────────────────

@app.post("/kelas/", response_model=schemas.KelasOut, status_code=201, tags=["Kelas"])
def create_kelas(kelas: schemas.KelasCreate, db: Session = Depends(get_db),
                 _=Depends(require_admin)):
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
def update_kelas(id_kelas: int, kelas: schemas.KelasUpdate, db: Session = Depends(get_db),
                 _=Depends(require_admin)):
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
def create_guru(guru: schemas.GuruCreate, db: Session = Depends(get_db),
                _=Depends(require_admin)):
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

@app.get("/guru/{id_guru}", response_model=schemas.GuruOut, tags=["Guru"])
def get_guru(id_guru: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    obj = crud.get_guru(db, id_guru)
    if not obj:
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return obj

@app.put("/guru/{id_guru}", response_model=schemas.GuruOut, tags=["Guru"])
def update_guru(id_guru: int, guru: schemas.GuruUpdate, db: Session = Depends(get_db),
                _=Depends(require_admin)):
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
def create_admin(data: schemas.AdminCreate, db: Session = Depends(get_db),
                 _=Depends(require_admin)):
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

@app.post("/kepala-sekolah/", response_model=schemas.KepsekOut,
          status_code=201, tags=["Kepala Sekolah"])
def create_kepsek(data: schemas.KepsekCreate, db: Session = Depends(get_db),
                  _=Depends(require_admin)):
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
def update_kepsek(id_kepsek: int, data: schemas.KepsekUpdate,
                  db: Session = Depends(get_db), _=Depends(require_admin)):
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
def create_siswa(data: schemas.SiswaCreate, db: Session = Depends(get_db),
                 _=Depends(require_admin)):
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
def update_siswa(id_siswa: int, data: schemas.SiswaUpdate,
                 db: Session = Depends(get_db), _=Depends(require_admin)):
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

@app.put("/wali-siswa/{id_wali_siswa}", response_model=schemas.WaliSiswaOut,
         tags=["Wali Siswa"])
def update_wali_siswa(id_wali_siswa: int, data: schemas.WaliSiswaUpdate,
                      db: Session = Depends(get_db), _=Depends(require_admin)):
    obj = crud.update_wali_siswa(db, id_wali_siswa, data)
    if not obj:
        raise HTTPException(status_code=404, detail="Wali siswa tidak ditemukan")
    return obj

@app.get("/wali-siswa/by-akun/{id_akun}", response_model=schemas.WaliSiswaOut,
         tags=["Wali Siswa"])
def get_wali_by_akun(id_akun: int, db: Session = Depends(get_db),
                     current_user: models.Akun = Depends(get_current_user)):
    if current_user.role == models.RoleEnum.wali_siswa and current_user.id_akun != id_akun:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    obj = crud.get_wali_siswa_by_akun(db, id_akun)
    if not obj:
        raise HTTPException(status_code=404, detail="Data wali tidak ditemukan")
    return obj


# ─── Pesan ────────────────────────────────────────────────────────────────────

@app.post("/pesan/", response_model=schemas.PesanOut, status_code=201, tags=["Pesan"])
def kirim_pesan(data: schemas.PesanCreate, db: Session = Depends(get_db),
                current_user: models.Akun = Depends(get_current_user)):
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

    # BUG FIX: kode asli merujuk `db_pesan` yang tidak didefinisikan → diganti `pesan`
    crud.kirim_notif_pesan(
        db,
        id_akun_penerima=pesan.id_penerima,
        nama_pengirim=current_user.nama,
        id_pesan=pesan.id_pesan,
        payload_ws={
            "id_pesan":     pesan.id_pesan,
            "id_pengirim":  pesan.id_pengirim,
            "id_penerima":  pesan.id_penerima,
            "isi_pesan":    pesan.isi_pesan,
            "waktu":        str(pesan.waktu),
            "nama_pengirim": current_user.nama,
        },
    )
    return pesan

@app.get("/pesan/riwayat/{id_a}/{id_b}", response_model=List[schemas.PesanOut], tags=["Pesan"])
def get_riwayat_percakapan(id_a: int, id_b: int,
                            after_id: Optional[int] = Query(None),
                            skip: int = Query(0), limit: int = Query(200),
                            db: Session = Depends(get_db),
                            current_user: models.Akun = Depends(get_current_user)):
    if current_user.id_akun not in (id_a, id_b):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    kedua_arah = or_(
        and_(models.Pesan.id_pengirim == id_a, models.Pesan.id_penerima == id_b),
        and_(models.Pesan.id_pengirim == id_b, models.Pesan.id_penerima == id_a),
    )

    if after_id is not None:
        return (db.query(models.Pesan)
                .filter(kedua_arah, models.Pesan.id_pesan > after_id)
                .order_by(models.Pesan.waktu.asc()).all())

    lawan_id = id_b if current_user.id_akun == id_a else id_a
    db.query(models.Pesan).filter(
        models.Pesan.id_pengirim == lawan_id,
        models.Pesan.id_penerima == current_user.id_akun,
        models.Pesan.status == models.StatusPesanEnum.terkirim,
    ).update({"status": models.StatusPesanEnum.diterima}, synchronize_session=False)
    db.commit()

    return (db.query(models.Pesan).filter(kedua_arah)
            .order_by(models.Pesan.waktu.asc())
            .offset(skip).limit(limit).all())

@app.put("/pesan/baca", tags=["Pesan"])
def tandai_dibaca(data: schemas.TandaiBacaRequest, db: Session = Depends(get_db),
                  current_user: models.Akun = Depends(get_current_user)):
    db.query(models.Pesan).filter(
        models.Pesan.id_pengirim == data.id_pengirim,
        models.Pesan.id_penerima == current_user.id_akun,
        models.Pesan.status == models.StatusPesanEnum.diterima,
    ).update({"status": models.StatusPesanEnum.dibaca}, synchronize_session=False)
    db.commit()
    return {"message": "Pesan ditandai dibaca"}

@app.get("/pesan/percakapan/{id_akun}", response_model=List[schemas.PercakapanItem], tags=["Pesan"])
def get_daftar_percakapan(id_akun: int, db: Session = Depends(get_db),
                           current_user: models.Akun = Depends(get_current_user)):
    if current_user.id_akun != id_akun:
        raise HTTPException(status_code=403, detail="Akses ditolak")

    semua_pesan = (db.query(models.Pesan)
                   .filter(or_(models.Pesan.id_pengirim == id_akun,
                               models.Pesan.id_penerima == id_akun))
                   .order_by(models.Pesan.waktu.desc()).all())

    hasil, sudah = [], set()
    for p in semua_pesan:
        lawan_id = p.id_penerima if p.id_pengirim == id_akun else p.id_pengirim
        if lawan_id in sudah:
            continue
        sudah.add(lawan_id)

        lawan_akun = crud.get_akun(db, lawan_id)
        if not lawan_akun:
            continue

        wali = (db.query(models.WaliSiswa)
                .filter(models.WaliSiswa.id_akun == lawan_id).first())
        nama_siswa = wali.siswa.nama_siswa if wali and wali.siswa else None

        belum_dibaca = (db.query(models.Pesan).filter(
            models.Pesan.id_pengirim == lawan_id,
            models.Pesan.id_penerima == id_akun,
            models.Pesan.status == models.StatusPesanEnum.diterima,
        ).count())

        hasil.append(schemas.PercakapanItem(
            id_akun_lawan=lawan_id, nama_lawan=lawan_akun.nama,
            nama_siswa=nama_siswa, inisial=_buat_inisial(lawan_akun.nama),
            pesan_terakhir=p.isi_pesan, waktu=p.waktu,
            status=p.status, jumlah_belum_dibaca=belum_dibaca,
        ))
    return hasil

@app.get("/pesan/semua-guru", response_model=List[schemas.GuruListItem], tags=["Pesan"])
def get_semua_guru(db: Session = Depends(get_db),
                   current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.wali_siswa:
        raise HTTPException(status_code=403, detail="Hanya wali siswa yang dapat mengakses")

    guru_list = db.query(models.Guru).join(models.Akun).all()
    hasil = []
    for guru in guru_list:
        gid = guru.id_akun
        pesan_terakhir = (db.query(models.Pesan).filter(
            or_(and_(models.Pesan.id_pengirim == current_user.id_akun,
                     models.Pesan.id_penerima == gid),
                and_(models.Pesan.id_pengirim == gid,
                     models.Pesan.id_penerima == current_user.id_akun)))
            .order_by(models.Pesan.waktu.desc()).first())
        belum = (db.query(models.Pesan).filter(
            models.Pesan.id_pengirim == gid,
            models.Pesan.id_penerima == current_user.id_akun,
            models.Pesan.status == models.StatusPesanEnum.diterima,
        ).count())
        hasil.append(schemas.GuruListItem(
            id_akun_guru=gid, nama_guru=guru.akun.nama,
            inisial=_buat_inisial(guru.akun.nama),
            pesan_terakhir=pesan_terakhir.isi_pesan if pesan_terakhir else None,
            waktu=pesan_terakhir.waktu if pesan_terakhir else None,
            status=pesan_terakhir.status if pesan_terakhir else None,
            jumlah_belum_dibaca=belum,
        ))
    hasil.sort(key=lambda x: x.waktu or datetime.min, reverse=True)
    return hasil

@app.get("/pesan/semua-wali", response_model=List[schemas.WaliListItem], tags=["Pesan"])
def get_semua_wali(db: Session = Depends(get_db),
                   current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")
    return [
        schemas.WaliListItem(
            id_akun_wali=w.id_akun, nama_wali=w.akun.nama,
            inisial=_buat_inisial(w.akun.nama),
            nama_siswa=w.siswa.nama_siswa if w.siswa else "",
        )
        for w in db.query(models.WaliSiswa).join(models.Akun).all()
    ]


# ─── Absensi ──────────────────────────────────────────────────────────────────

@app.get("/absensi/kelas/{id_kelas}", response_model=List[schemas.SiswaAbsensiItem],
         tags=["Absensi"])
def get_siswa_absensi(id_kelas: int, tanggal: date, db: Session = Depends(get_db),
                      current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")
    if not crud.get_kelas(db, id_kelas):
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")

    siswa_list = (db.query(models.Siswa).filter(models.Siswa.id_kelas == id_kelas)
                  .order_by(models.Siswa.nama_siswa).all())
    id_list = [s.id_siswa for s in siswa_list]
    absensi_map = {}
    if id_list:
        absensi_map = {a.id_siswa: a for a in
                       db.query(models.Absensi).filter(
                           models.Absensi.id_siswa.in_(id_list),
                           models.Absensi.tanggal == tanggal).all()}
    return [schemas.SiswaAbsensiItem(
        id_siswa=s.id_siswa, nama_siswa=s.nama_siswa,
        status=absensi_map[s.id_siswa].status if s.id_siswa in absensi_map else None,
        keterangan=absensi_map[s.id_siswa].keterangan if s.id_siswa in absensi_map else None,
    ) for s in siswa_list]

@app.post("/absensi/batch", response_model=List[schemas.AbsensiOut], tags=["Absensi"])
def simpan_absensi_batch(payload: schemas.AbsensiBatchRequest,
                          db: Session = Depends(get_db),
                          current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")
    guru = _get_guru_or_403(db, current_user.id_akun)

    hasil = []
    for item in payload.data:
        siswa = crud.get_siswa(db, item.id_siswa)
        if not siswa or siswa.id_kelas != payload.id_kelas:
            raise HTTPException(status_code=400,
                detail=f"Siswa {item.id_siswa} tidak ada di kelas {payload.id_kelas}")
        existing = (db.query(models.Absensi)
                    .filter(models.Absensi.id_siswa == item.id_siswa,
                            models.Absensi.tanggal == payload.tanggal).first())
        if existing:
            existing.status = item.status
            existing.keterangan = item.keterangan
            existing.id_guru = guru.id_guru
            hasil.append(existing)
        else:
            ab = models.Absensi(id_siswa=item.id_siswa, id_guru=guru.id_guru,
                                tanggal=payload.tanggal, status=item.status,
                                keterangan=item.keterangan)
            db.add(ab)
            hasil.append(ab)
    db.commit()
    for ab in hasil:
        db.refresh(ab)

    if hasil:
        crud.kirim_notif_absensi_batch(
            db, payload.id_kelas, str(payload.tanggal),
            current_user.nama, hasil[0].id_absensi)
    return hasil

@app.get("/absensi/siswa/{id_siswa}", response_model=List[schemas.AbsensiHarianSiswaOut],
         tags=["Absensi"])
def get_absensi_siswa(id_siswa: int, bulan: int, tahun: int,
                       db: Session = Depends(get_db),
                       current_user: models.Akun = Depends(get_current_user)):
    _cek_wali_akses_siswa(db, current_user, id_siswa)
    records = (db.query(models.Absensi).filter(
        models.Absensi.id_siswa == id_siswa,
        extract("month", models.Absensi.tanggal) == bulan,
        extract("year",  models.Absensi.tanggal) == tahun,
    ).order_by(models.Absensi.tanggal).all())
    return [schemas.AbsensiHarianSiswaOut(
        id_absensi=ab.id_absensi, id_siswa=ab.id_siswa, id_guru=ab.id_guru,
        tanggal=ab.tanggal, status=ab.status, keterangan=ab.keterangan,
        nama_guru=ab.guru.akun.nama if ab.guru and ab.guru.akun else None,
    ) for ab in records]

@app.get("/absensi/siswa/{id_siswa}/ringkasan", response_model=schemas.RingkasanAbsensiOut,
         tags=["Absensi"])
def get_ringkasan_absensi_siswa(id_siswa: int, bulan: int, tahun: int,
                                 db: Session = Depends(get_db),
                                 current_user: models.Akun = Depends(get_current_user)):
    _cek_wali_akses_siswa(db, current_user, id_siswa)
    records = (db.query(models.Absensi).filter(
        models.Absensi.id_siswa == id_siswa,
        extract("month", models.Absensi.tanggal) == bulan,
        extract("year",  models.Absensi.tanggal) == tahun,
    ).all())
    rekap = schemas.RingkasanAbsensiOut(bulan=bulan, tahun=tahun)
    for ab in records:
        if   ab.status == models.StatusAbsensiEnum.hadir: rekap.hadir += 1
        elif ab.status == models.StatusAbsensiEnum.sakit: rekap.sakit += 1
        elif ab.status == models.StatusAbsensiEnum.izin:  rekap.izin  += 1
        elif ab.status == models.StatusAbsensiEnum.alpha: rekap.alpha += 1
    return rekap


# ─── Catatan Harian ───────────────────────────────────────────────────────────

@app.post("/catatan/", response_model=schemas.CatatanHarianOut,
          status_code=201, tags=["Catatan Harian"])
def buat_catatan(payload: schemas.CatatanHarianCreate, db: Session = Depends(get_db),
                 current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat membuat catatan")
    guru = _get_guru_or_403(db, current_user.id_akun)
    if payload.target == models.TargetCatatanEnum.satu_kelas:
        if not crud.get_kelas(db, payload.id_kelas):
            raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    if payload.target == models.TargetCatatanEnum.satu_siswa:
        if not crud.get_siswa(db, payload.id_siswa):
            raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    catatan = crud.create_catatan_harian(db, payload, guru.id_guru)
    crud.kirim_notif_catatan(db, catatan, current_user.nama)
    return crud._build_catatan_out(catatan)

@app.get("/catatan/siswa/{id_siswa}", response_model=schemas.CatatanListResponse,
         tags=["Catatan Harian"])
def get_catatan_siswa(id_siswa: int, skip=0, limit=20,
                       db: Session = Depends(get_db),
                       current_user: models.Akun = Depends(get_current_user)):
    siswa = crud.get_siswa(db, id_siswa)
    if not siswa:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    if current_user.role == models.RoleEnum.wali_siswa:
        wali = crud.get_wali_siswa_by_akun(db, current_user.id_akun)
        if not wali or wali.id_siswa != id_siswa:
            raise HTTPException(status_code=403, detail="Anda hanya dapat melihat catatan anak Anda")
    catatan_list = crud.get_catatan_by_siswa(db, id_siswa, siswa.id_kelas, skip, limit)
    return schemas.CatatanListResponse(
        total=len(catatan_list),
        data=[crud._build_catatan_out(c) for c in catatan_list])

@app.get("/catatan/guru/", response_model=schemas.CatatanListResponse, tags=["Catatan Harian"])
def get_catatan_by_guru_login(skip=0, limit=50, db: Session = Depends(get_db),
                               current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")
    guru = _get_guru_or_403(db, current_user.id_akun)
    catatan_list = crud.get_catatan_by_guru(db, guru.id_guru, skip, limit)
    return schemas.CatatanListResponse(
        total=len(catatan_list),
        data=[crud._build_catatan_out(c) for c in catatan_list])

@app.get("/catatan/{id_catatan}", response_model=schemas.CatatanHarianOut, tags=["Catatan Harian"])
def get_catatan_detail(id_catatan: int, db: Session = Depends(get_db),
                        current_user: models.Akun = Depends(get_current_user)):
    catatan = crud.get_catatan_harian(db, id_catatan)
    if not catatan:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    if current_user.role == models.RoleEnum.wali_siswa:
        wali  = crud.get_wali_siswa_by_akun(db, current_user.id_akun)
        siswa = crud.get_siswa(db, wali.id_siswa) if wali and wali.id_siswa else None
        visible = (
            catatan.target == models.TargetCatatanEnum.semua_kelas or
            (catatan.target == models.TargetCatatanEnum.satu_kelas and
             siswa and siswa.id_kelas == catatan.id_kelas) or
            (catatan.target == models.TargetCatatanEnum.satu_siswa and
             wali and wali.id_siswa == catatan.id_siswa)
        )
        if not visible:
            raise HTTPException(status_code=403, detail="Akses ditolak")
    return crud._build_catatan_out(catatan)

@app.put("/catatan/{id_catatan}", response_model=schemas.CatatanHarianOut, tags=["Catatan Harian"])
def update_catatan(id_catatan: int, payload: schemas.CatatanHarianUpdate,
                   db: Session = Depends(get_db),
                   current_user: models.Akun = Depends(get_current_user)):
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
def delete_catatan(id_catatan: int, db: Session = Depends(get_db),
                   current_user: models.Akun = Depends(get_current_user)):
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
async def upload_foto_catatan(id_catatan: int, file: UploadFile = File(...),
                               db: Session = Depends(get_db),
                               current_user: models.Akun = Depends(get_current_user)):
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
def get_notifikasi(skip=0, limit=50, db: Session = Depends(get_db),
                   current_user: models.Akun = Depends(get_current_user)):
    return schemas.NotifikasiListResponse(
        total_belum_dibaca=crud.count_notif_belum_dibaca(db, current_user.id_akun),
        data=crud.get_notifikasi_by_akun(db, current_user.id_akun, skip, limit),
    )

@app.put("/notifikasi/baca", tags=["Notifikasi"])
def tandai_notif_dibaca(payload: schemas.BacaNotifRequest,
                         db: Session = Depends(get_db),
                         current_user: models.Akun = Depends(get_current_user)):
    jumlah = crud.tandai_notif_dibaca(db, current_user.id_akun, payload.id_notif)
    return {"message": f"{jumlah} notifikasi ditandai sudah dibaca", "jumlah": jumlah}


# ─── WebSocket ────────────────────────────────────────────────────────────────

@app.websocket("/ws/{id_akun}")
async def websocket_endpoint(websocket: WebSocket, id_akun: int, token: str):
    """
    ws://HOST/ws/{id_akun}?token=<raw_token>
    Push: {"tipe":"pesan_baru","data":{...}} | {"tipe":"ping"}
    """
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