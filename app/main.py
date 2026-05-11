from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from typing import List, Optional
from datetime import datetime, timedelta
import uvicorn
import jwt
import os

from app.database import engine, get_db, Base
from app import models, schemas, crud

SECRET_KEY                  = os.getenv("SECRET_KEY", "smartschool-secret-key-laragon-dev")
ALGORITHM                   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Smart School API",
    description="REST API Sistem Informasi Sekolah — Akun, Guru, Admin, Kepsek, Siswa, Kelas, Reset Password & Pesan",
    version="1.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    to_encode["exp"] = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

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
        payload  = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        id_akun: int = payload.get("id_akun")
        if id_akun is None:
            raise exc
    except jwt.PyJWTError:
        raise exc

    akun = crud.get_akun(db, id_akun)
    if akun is None:
        raise exc
    return akun

def require_admin(current_user: models.Akun = Depends(get_current_user)) -> models.Akun:
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya admin")
    return current_user

def _buat_inisial(nama: str) -> str:
    """Ambil huruf pertama dari dua kata pertama nama, kapital."""
    parts = [p for p in nama.split() if p]
    return "".join(p[0].upper() for p in parts[:2])


# ─── Startup: seed akun test + kelas default ──────────────────────────────────

@app.on_event("startup")
def seed_master_admin():
    db = next(get_db())
    try:
        if not crud.get_akun_by_username(db, "test"):
            crud.create_admin_with_akun(db, schemas.AdminCreate(
                username="test", nama="Admin"))
            print("✅ Akun TEST + baris admin dibuat")
        else:
            print("✅ Akun TEST sudah ada")

        nama_kelas_ada = {k.nama_kelas for k in crud.get_all_kelas(db)}
        for nama in ["TK A", "TK B"]:
            if nama not in nama_kelas_ada:
                crud.create_kelas(db, schemas.KelasCreate(nama_kelas=nama))
                print(f"✅ Kelas '{nama}' dibuat")
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
    token = create_access_token({
        "id_akun": akun.id_akun, "username": akun.username,
        "role": akun.role.value, "first_login": akun.first_login,
    })
    return {"access_token": token, "token_type": "bearer", "first_login": akun.first_login}

@app.get("/auth/me", tags=["Auth"])
def me(current_user: models.Akun = Depends(get_current_user)):
    return current_user


# ─── Akun ─────────────────────────────────────────────────────────────────────

@app.get("/akun/", response_model=List[schemas.AkunOut], tags=["Akun"])
def list_akun(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
              _: models.Akun = Depends(require_admin)):
    return crud.get_all_akun(db, skip=skip, limit=limit)

@app.get("/akun/by-username/{username}", response_model=schemas.AkunOut, tags=["Akun"])
def get_akun_by_username(username: str, db: Session = Depends(get_db)):
    akun = crud.get_akun_by_username(db, username)
    if not akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return akun

@app.get("/akun/{id_akun}", response_model=schemas.AkunOut, tags=["Akun"])
def get_akun(id_akun: int, db: Session = Depends(get_db),
             _: models.Akun = Depends(get_current_user)):
    akun = crud.get_akun(db, id_akun)
    if not akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return akun

@app.put("/akun/{id_akun}", response_model=schemas.AkunOut, tags=["Akun"])
def update_akun(id_akun: int, akun: schemas.AkunUpdate, db: Session = Depends(get_db),
                _: models.Akun = Depends(require_admin)):
    db_akun = crud.update_akun(db, id_akun, akun)
    if not db_akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return db_akun

@app.delete("/akun/{id_akun}", tags=["Akun"])
def delete_akun(id_akun: int, db: Session = Depends(get_db),
                _: models.Akun = Depends(require_admin)):
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


# ─── Reset Password ───────────────────────────────────────────────────────────

@app.post("/reset-password/", response_model=schemas.ResetPasswordOut, status_code=201,
          tags=["Reset Password"])
def create_reset_password(rp: schemas.ResetPasswordCreate, db: Session = Depends(get_db)):
    if not crud.get_akun(db, rp.id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    if crud.get_reset_password_by_akun(db, rp.id_akun):
        raise HTTPException(status_code=400, detail="Pertanyaan keamanan sudah ada")
    return crud.create_reset_password(db=db, rp=rp)

@app.get("/reset-password/akun/{id_akun}", response_model=schemas.ResetPasswordOut,
         tags=["Reset Password"])
def get_pertanyaan_by_akun(id_akun: int, db: Session = Depends(get_db)):
    if not crud.get_akun(db, id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    db_rp = crud.get_reset_password_by_akun(db, id_akun)
    if not db_rp:
        raise HTTPException(status_code=404, detail="Pertanyaan keamanan tidak ditemukan")
    return db_rp

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
    if not akun:
        raise HTTPException(status_code=500, detail="Gagal mengganti password")
    return akun

@app.get("/reset-password/", response_model=List[schemas.ResetPasswordOut],
         tags=["Reset Password"])
def list_reset_password(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
                        _: models.Akun = Depends(require_admin)):
    return crud.get_all_reset_password(db, skip=skip, limit=limit)

@app.put("/reset-password/{id_pertanyaan}", response_model=schemas.ResetPasswordOut,
         tags=["Reset Password"])
def update_reset_password(id_pertanyaan: int, rp: schemas.ResetPasswordUpdate,
                          db: Session = Depends(get_db)):
    db_rp = crud.update_reset_password(db, id_pertanyaan, rp)
    if not db_rp:
        raise HTTPException(status_code=404, detail="Pertanyaan tidak ditemukan")
    return db_rp

@app.delete("/reset-password/{id_pertanyaan}", tags=["Reset Password"])
def delete_reset_password(id_pertanyaan: int, db: Session = Depends(get_db),
                          _: models.Akun = Depends(require_admin)):
    if not crud.delete_reset_password(db, id_pertanyaan):
        raise HTTPException(status_code=404, detail="Pertanyaan tidak ditemukan")
    return {"message": f"Pertanyaan {id_pertanyaan} berhasil dihapus"}


# ─── Kelas ────────────────────────────────────────────────────────────────────

@app.post("/kelas/", response_model=schemas.KelasOut, status_code=201, tags=["Kelas"])
def create_kelas(kelas: schemas.KelasCreate, db: Session = Depends(get_db),
                 _: models.Akun = Depends(require_admin)):
    return crud.create_kelas(db=db, kelas=kelas)

@app.get("/kelas/", response_model=List[schemas.KelasOut], tags=["Kelas"])
def list_kelas(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
               _: models.Akun = Depends(get_current_user)):
    return crud.get_all_kelas(db, skip=skip, limit=limit)

@app.get("/kelas/{id_kelas}", response_model=schemas.KelasOut, tags=["Kelas"])
def get_kelas(id_kelas: int, db: Session = Depends(get_db),
              _: models.Akun = Depends(get_current_user)):
    db_kelas = crud.get_kelas(db, id_kelas)
    if not db_kelas:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return db_kelas

@app.put("/kelas/{id_kelas}", response_model=schemas.KelasOut, tags=["Kelas"])
def update_kelas(id_kelas: int, kelas: schemas.KelasUpdate, db: Session = Depends(get_db),
                 _: models.Akun = Depends(require_admin)):
    db_kelas = crud.update_kelas(db, id_kelas, kelas)
    if not db_kelas:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return db_kelas

@app.delete("/kelas/{id_kelas}", tags=["Kelas"])
def delete_kelas(id_kelas: int, db: Session = Depends(get_db),
                 _: models.Akun = Depends(require_admin)):
    if not crud.delete_kelas(db, id_kelas):
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return {"message": f"Kelas {id_kelas} berhasil dihapus"}


# ─── Guru ─────────────────────────────────────────────────────────────────────

@app.post("/guru/", response_model=schemas.GuruOut, status_code=201, tags=["Guru"],
          summary="Buat akun + data guru sekaligus")
def create_guru(guru: schemas.GuruCreate, db: Session = Depends(get_db),
                _: models.Akun = Depends(require_admin)):
    if crud.get_akun_by_username(db, guru.username):
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    if guru.nip and crud.get_guru_by_nip(db, guru.nip):
        raise HTTPException(status_code=400, detail="NIP sudah terdaftar")
    for id_k in (guru.list_id_kelas or []):
        if not crud.get_kelas(db, id_k):
            raise HTTPException(status_code=404, detail=f"Kelas {id_k} tidak ditemukan")
    return crud.create_guru_with_akun(db=db, guru=guru)

@app.get("/guru/", response_model=List[schemas.GuruOut], tags=["Guru"])
def list_guru(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
              _: models.Akun = Depends(require_admin)):
    return crud.get_all_guru(db, skip=skip, limit=limit)

@app.get("/guru/{id_guru}", response_model=schemas.GuruOut, tags=["Guru"])
def get_guru(id_guru: int, db: Session = Depends(get_db),
             _: models.Akun = Depends(get_current_user)):
    db_guru = crud.get_guru(db, id_guru)
    if not db_guru:
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return db_guru

@app.put("/guru/{id_guru}", response_model=schemas.GuruOut, tags=["Guru"])
def update_guru(id_guru: int, guru: schemas.GuruUpdate, db: Session = Depends(get_db),
                _: models.Akun = Depends(require_admin)):
    for id_k in (guru.list_id_kelas or []):
        if not crud.get_kelas(db, id_k):
            raise HTTPException(status_code=404, detail=f"Kelas {id_k} tidak ditemukan")
    db_guru = crud.update_guru(db, id_guru, guru)
    if not db_guru:
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return db_guru

@app.delete("/guru/{id_guru}", tags=["Guru"])
def delete_guru(id_guru: int, db: Session = Depends(get_db),
                _: models.Akun = Depends(require_admin)):
    if not crud.delete_guru(db, id_guru):
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return {"message": f"Guru {id_guru} berhasil dihapus"}


# ─── Admin ────────────────────────────────────────────────────────────────────

@app.post("/admin/", response_model=schemas.AdminOut, status_code=201, tags=["Admin"],
          summary="Buat akun + data admin sekaligus")
def create_admin(data: schemas.AdminCreate, db: Session = Depends(get_db),
                 _: models.Akun = Depends(require_admin)):
    if crud.get_akun_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    return crud.create_admin_with_akun(db=db, data=data)

@app.get("/admin/", response_model=List[schemas.AdminOut], tags=["Admin"])
def list_admin(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
               _: models.Akun = Depends(require_admin)):
    return crud.get_all_admin(db, skip=skip, limit=limit)

@app.delete("/admin/{id_admin}", tags=["Admin"])
def delete_admin(id_admin: int, db: Session = Depends(get_db),
                 _: models.Akun = Depends(require_admin)):
    if not crud.delete_admin(db, id_admin):
        raise HTTPException(status_code=404, detail="Admin tidak ditemukan")
    return {"message": f"Admin {id_admin} berhasil dihapus"}


# ─── Akun + Role (endpoint universal untuk Android) ──────────────────────────

@app.post("/akun/create-with-role", response_model=schemas.AkunOut,
          status_code=201, tags=["Akun"],
          summary="Buat akun sekaligus baris tabel sesuai role (admin/kepala_sekolah)")
async def create_akun_with_role(request: Request,
                                db: Session = Depends(get_db),
                                _: models.Akun = Depends(require_admin)):
    raw = await request.body()
    import logging
    logging.warning(f"[create-with-role] raw body: {raw.decode()}")

    import json
    try:
        body = json.loads(raw)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"JSON tidak valid: {e}")

    try:
        data = schemas.AkunCreateWithRole(**body)
    except Exception as e:
        logging.warning(f"[create-with-role] validation error: {e}")
        raise HTTPException(status_code=422, detail=str(e))

    if crud.get_akun_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    if data.role == schemas.RoleEnum.admin:
        db_admin = crud.create_admin_with_akun(
            db, schemas.AdminCreate(username=data.username, nama=data.nama))
        return db_admin.akun
    if data.role == schemas.RoleEnum.kepala_sekolah:
        if data.nip and crud.get_kepsek_by_nip(db, data.nip):
            raise HTTPException(status_code=400, detail="NIP sudah terdaftar")
        db_kepsek = crud.create_kepsek_with_akun(
            db, schemas.KepsekCreate(username=data.username, nama=data.nama, nip=data.nip))
        return db_kepsek.akun
    raise HTTPException(status_code=400,
                        detail="Gunakan endpoint /guru/ untuk role guru")


# ─── Kepala Sekolah ───────────────────────────────────────────────────────────

@app.post("/kepala-sekolah/", response_model=schemas.KepsekOut, status_code=201,
          tags=["Kepala Sekolah"], summary="Buat akun + data kepala sekolah sekaligus")
def create_kepsek(data: schemas.KepsekCreate, db: Session = Depends(get_db),
                  _: models.Akun = Depends(require_admin)):
    if crud.get_akun_by_username(db, data.username):
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    if data.nip and crud.get_kepsek_by_nip(db, data.nip):
        raise HTTPException(status_code=400, detail="NIP sudah terdaftar")
    return crud.create_kepsek_with_akun(db=db, data=data)

@app.get("/kepala-sekolah/", response_model=List[schemas.KepsekOut], tags=["Kepala Sekolah"])
def list_kepsek(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
                _: models.Akun = Depends(require_admin)):
    return crud.get_all_kepsek(db, skip=skip, limit=limit)

@app.get("/kepala-sekolah/{id_kepsek}", response_model=schemas.KepsekOut, tags=["Kepala Sekolah"])
def get_kepsek(id_kepsek: int, db: Session = Depends(get_db),
               _: models.Akun = Depends(get_current_user)):
    db_kepsek = crud.get_kepsek(db, id_kepsek)
    if not db_kepsek:
        raise HTTPException(status_code=404, detail="Kepala sekolah tidak ditemukan")
    return db_kepsek

@app.put("/kepala-sekolah/{id_kepsek}", response_model=schemas.KepsekOut, tags=["Kepala Sekolah"])
def update_kepsek(id_kepsek: int, data: schemas.KepsekUpdate, db: Session = Depends(get_db),
                  _: models.Akun = Depends(require_admin)):
    db_kepsek = crud.update_kepsek(db, id_kepsek, data)
    if not db_kepsek:
        raise HTTPException(status_code=404, detail="Kepala sekolah tidak ditemukan")
    return db_kepsek

@app.delete("/kepala-sekolah/{id_kepsek}", tags=["Kepala Sekolah"])
def delete_kepsek(id_kepsek: int, db: Session = Depends(get_db),
                  _: models.Akun = Depends(require_admin)):
    if not crud.delete_kepsek(db, id_kepsek):
        raise HTTPException(status_code=404, detail="Kepala sekolah tidak ditemukan")
    return {"message": f"Kepala sekolah {id_kepsek} berhasil dihapus"}


# ─── Siswa ────────────────────────────────────────────────────────────────────

@app.post("/siswa/", response_model=schemas.SiswaOut, status_code=201, tags=["Siswa"],
          summary="Buat akun wali + data wali + data siswa sekaligus")
def create_siswa(data: schemas.SiswaCreate, db: Session = Depends(get_db),
                 _: models.Akun = Depends(require_admin)):
    if crud.get_akun_by_username(db, data.username_wali):
        raise HTTPException(status_code=400, detail="Username wali sudah digunakan")
    if crud.get_siswa_by_nisn(db, data.nisn):
        raise HTTPException(status_code=400, detail="NISN sudah terdaftar")
    if data.id_kelas and not crud.get_kelas(db, data.id_kelas):
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return crud.create_siswa_with_wali(db=db, data=data)

@app.get("/siswa/", response_model=List[schemas.SiswaOut], tags=["Siswa"])
def list_siswa(skip: int = 0, limit: int = 100, db: Session = Depends(get_db),
               _: models.Akun = Depends(require_admin)):
    return crud.get_all_siswa(db, skip=skip, limit=limit)

@app.get("/siswa/{id_siswa}", response_model=schemas.SiswaOut, tags=["Siswa"])
def get_siswa(id_siswa: int, db: Session = Depends(get_db),
              _: models.Akun = Depends(get_current_user)):
    db_siswa = crud.get_siswa(db, id_siswa)
    if not db_siswa:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return db_siswa

@app.put("/siswa/{id_siswa}", response_model=schemas.SiswaOut, tags=["Siswa"])
def update_siswa(id_siswa: int, data: schemas.SiswaUpdate, db: Session = Depends(get_db),
                 _: models.Akun = Depends(require_admin)):
    if data.id_kelas and not crud.get_kelas(db, data.id_kelas):
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    db_siswa = crud.update_siswa(db, id_siswa, data)
    if not db_siswa:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return db_siswa

@app.delete("/siswa/{id_siswa}", tags=["Siswa"])
def delete_siswa(id_siswa: int, db: Session = Depends(get_db),
                 _: models.Akun = Depends(require_admin)):
    if not crud.delete_siswa(db, id_siswa):
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return {"message": f"Siswa {id_siswa} berhasil dihapus"}


# ─── Wali Siswa ───────────────────────────────────────────────────────────────

@app.put("/wali-siswa/{id_wali_siswa}", response_model=schemas.WaliSiswaOut,
         tags=["Wali Siswa"])
def update_wali_siswa(id_wali_siswa: int, data: schemas.WaliSiswaUpdate,
                      db: Session = Depends(get_db),
                      _: models.Akun = Depends(require_admin)):
    db_wali = crud.update_wali_siswa(db, id_wali_siswa, data)
    if not db_wali:
        raise HTTPException(status_code=404, detail="Wali siswa tidak ditemukan")
    return db_wali

@app.get("/wali-siswa/by-akun/{id_akun}", response_model=schemas.WaliSiswaOut,
         tags=["Wali Siswa"],
         summary="Ambil data wali beserta siswa & kelas berdasarkan id_akun")
def get_wali_by_akun(
    id_akun: int,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if (current_user.role == models.RoleEnum.wali_siswa
            and current_user.id_akun != id_akun):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    db_wali = crud.get_wali_siswa_by_akun(db, id_akun)
    if not db_wali:
        raise HTTPException(status_code=404, detail="Data wali tidak ditemukan")
    return db_wali


# ─── Pesan ────────────────────────────────────────────────────────────────────
#
# id_pengirim dan id_penerima merujuk ke akun.id_akun — bukan id_guru / id_wali_siswa.
#
# Endpoint:
#   POST  /pesan/                         → kirim pesan (auth)
#   GET   /pesan/riwayat/{id_a}/{id_b}    → histori percakapan dua user (auth)
#   PUT   /pesan/baca                     → tandai pesan masuk sebagai dibaca (auth)
#   GET   /pesan/percakapan/{id_akun}     → daftar percakapan aktif (auth, untuk guru)
#   GET   /pesan/semua-guru               → semua guru + info pesan terakhir (auth, untuk wali)
#   GET   /pesan/semua-wali               → semua wali siswa (auth, untuk guru pilih kontak baru)
# ─────────────────────────────────────────────────────────────────────────────

@app.post(
    "/pesan/",
    response_model=schemas.PesanOut,
    status_code=201,
    tags=["Pesan"],
    summary="Kirim pesan ke pengguna lain (id_pengirim otomatis dari JWT)",
)
def kirim_pesan(
    data: schemas.PesanCreate,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    """
    Mengirim pesan.
    - `id_pengirim` diisi otomatis dari token login, tidak perlu dikirim dari client.
    - `id_penerima` harus merupakan id_akun yang valid.
    - Status awal: `terkirim`.
    """
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
    return pesan


@app.get(
    "/pesan/riwayat/{id_a}/{id_b}",
    response_model=List[schemas.PesanOut],
    tags=["Pesan"],
    summary="Histori percakapan antara dua pengguna, urut dari lama ke baru",
)
def get_riwayat_percakapan(
    id_a: int,
    id_b: int,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    """
    Mengembalikan semua pesan antara id_a dan id_b (dua arah).
    Hanya boleh diakses oleh salah satu dari dua pengguna tersebut.
    Otomatis menandai pesan yang diterima current_user sebagai 'diterima'.
    """
    if current_user.id_akun not in (id_a, id_b):
        raise HTTPException(status_code=403, detail="Akses ditolak")

    # Tandai pesan dari lawan sebagai "diterima" (sudah sampai, belum tentu dibaca)
    lawan_id = id_b if current_user.id_akun == id_a else id_a
    db.query(models.Pesan).filter(
        models.Pesan.id_pengirim == lawan_id,
        models.Pesan.id_penerima == current_user.id_akun,
        models.Pesan.status == models.StatusPesanEnum.terkirim,
    ).update({"status": models.StatusPesanEnum.diterima}, synchronize_session=False)
    db.commit()

    return (
        db.query(models.Pesan)
        .filter(
            or_(
                and_(models.Pesan.id_pengirim == id_a, models.Pesan.id_penerima == id_b),
                and_(models.Pesan.id_pengirim == id_b, models.Pesan.id_penerima == id_a),
            )
        )
        .order_by(models.Pesan.waktu.asc())
        .all()
    )


@app.put(
    "/pesan/baca",
    tags=["Pesan"],
    summary="Tandai semua pesan dari id_pengirim sebagai 'dibaca'",
)
def tandai_dibaca(
    data: schemas.TandaiBacaRequest,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    """
    Dipanggil saat pengguna membuka percakapan (chat window terbuka).
    Mengubah status pesan dari 'diterima' → 'dibaca'.
    """
    db.query(models.Pesan).filter(
        models.Pesan.id_pengirim == data.id_pengirim,
        models.Pesan.id_penerima == current_user.id_akun,
        models.Pesan.status == models.StatusPesanEnum.diterima,
    ).update({"status": models.StatusPesanEnum.dibaca}, synchronize_session=False)
    db.commit()
    return {"message": "Pesan ditandai dibaca"}


@app.get(
    "/pesan/percakapan/{id_akun}",
    response_model=List[schemas.PercakapanItem],
    tags=["Pesan"],
    summary="Daftar percakapan aktif (hanya yang sudah ada riwayat pesan)",
)
def get_daftar_percakapan(
    id_akun: int,
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    """
    Dipakai oleh GURU untuk menampilkan list percakapan yang sudah berjalan.
    Mengembalikan satu item per lawan bicara, dengan pesan terakhir & jumlah belum dibaca.
    """
    if current_user.id_akun != id_akun:
        raise HTTPException(status_code=403, detail="Akses ditolak")

    # Semua pesan yang melibatkan id_akun, diurutkan dari terbaru
    semua_pesan = (
        db.query(models.Pesan)
        .filter(
            or_(
                models.Pesan.id_pengirim == id_akun,
                models.Pesan.id_penerima == id_akun,
            )
        )
        .order_by(models.Pesan.waktu.desc())
        .all()
    )

    hasil: List[schemas.PercakapanItem] = []
    sudah_diproses: set = set()

    for p in semua_pesan:
        lawan_id = p.id_penerima if p.id_pengirim == id_akun else p.id_pengirim
        if lawan_id in sudah_diproses:
            continue
        sudah_diproses.add(lawan_id)

        lawan_akun = crud.get_akun(db, lawan_id)
        if not lawan_akun:
            continue

        # Nama siswa (jika lawan adalah wali_siswa)
        nama_siswa: Optional[str] = None
        wali = (
            db.query(models.WaliSiswa)
            .filter(models.WaliSiswa.id_akun == lawan_id)
            .first()
        )
        if wali and wali.siswa:
            nama_siswa = wali.siswa.nama_siswa

        jumlah_belum_dibaca = (
            db.query(models.Pesan)
            .filter(
                models.Pesan.id_pengirim == lawan_id,
                models.Pesan.id_penerima == id_akun,
                models.Pesan.status == models.StatusPesanEnum.diterima,
            )
            .count()
        )

        hasil.append(
            schemas.PercakapanItem(
                id_akun_lawan=lawan_id,
                nama_lawan=lawan_akun.nama,
                nama_siswa=nama_siswa,
                inisial=_buat_inisial(lawan_akun.nama),
                pesan_terakhir=p.isi_pesan,
                waktu=p.waktu,
                status=p.status,
                jumlah_belum_dibaca=jumlah_belum_dibaca,
            )
        )

    return hasil


@app.get(
    "/pesan/semua-guru",
    response_model=List[schemas.GuruListItem],
    tags=["Pesan"],
    summary="Semua guru + info pesan terakhir (untuk daftar kontak wali siswa)",
)
def get_semua_guru(
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    """
    Dipakai oleh WALI SISWA untuk menampilkan daftar semua guru yang bisa dihubungi.
    Setiap item dilengkapi preview pesan terakhir & jumlah belum dibaca jika ada.
    """
    if current_user.role not in (models.RoleEnum.wali_siswa,):
        raise HTTPException(status_code=403, detail="Hanya wali siswa yang dapat mengakses")

    guru_list = db.query(models.Guru).join(models.Akun).all()
    hasil: List[schemas.GuruListItem] = []

    for guru in guru_list:
        id_akun_guru = guru.id_akun
        nama = guru.akun.nama

        # Pesan terakhir antara wali ini dan guru
        pesan_terakhir = (
            db.query(models.Pesan)
            .filter(
                or_(
                    and_(
                        models.Pesan.id_pengirim == current_user.id_akun,
                        models.Pesan.id_penerima == id_akun_guru,
                    ),
                    and_(
                        models.Pesan.id_pengirim == id_akun_guru,
                        models.Pesan.id_penerima == current_user.id_akun,
                    ),
                )
            )
            .order_by(models.Pesan.waktu.desc())
            .first()
        )

        jumlah_belum_dibaca = (
            db.query(models.Pesan)
            .filter(
                models.Pesan.id_pengirim == id_akun_guru,
                models.Pesan.id_penerima == current_user.id_akun,
                models.Pesan.status == models.StatusPesanEnum.diterima,
            )
            .count()
        )

        hasil.append(
            schemas.GuruListItem(
                id_akun_guru=id_akun_guru,
                nama_guru=nama,
                inisial=_buat_inisial(nama),
                pesan_terakhir=pesan_terakhir.isi_pesan if pesan_terakhir else None,
                waktu=pesan_terakhir.waktu if pesan_terakhir else None,
                status=pesan_terakhir.status if pesan_terakhir else None,
                jumlah_belum_dibaca=jumlah_belum_dibaca,
            )
        )

    # Urutkan: yang punya riwayat pesan (terbaru) dulu, lalu yang belum
    hasil.sort(
        key=lambda x: x.waktu if x.waktu else datetime.min,
        reverse=True,
    )
    return hasil


@app.get(
    "/pesan/semua-wali",
    response_model=List[schemas.WaliListItem],
    tags=["Pesan"],
    summary="Semua wali siswa (untuk guru memilih kontak percakapan baru)",
)
def get_semua_wali(
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    """
    Dipakai oleh GURU untuk menampilkan daftar semua wali siswa
    saat ingin memulai percakapan baru.
    """
    if current_user.role not in (models.RoleEnum.guru,):
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")

    wali_list = db.query(models.WaliSiswa).join(models.Akun).all()
    return [
        schemas.WaliListItem(
            id_akun_wali=w.id_akun,
            nama_wali=w.akun.nama,
            inisial=_buat_inisial(w.akun.nama),
            nama_siswa=w.siswa.nama_siswa if w.siswa else "",
        )
        for w in wali_list
    ]
    


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)