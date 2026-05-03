from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
import uvicorn
import jwt
import os

from app.database import engine, get_db, Base
from app import models, schemas, crud

# ─── Konfigurasi JWT ──────────────────────────────────────────────────────────
SECRET_KEY  = os.getenv("SECRET_KEY", "ganti-dengan-secret-key-yang-aman-di-production")
ALGORITHM   = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24  # 1 hari

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")

# Create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Sistem Informasi Sekolah API",
    description="REST API untuk manajemen akun, admin, dan reset password.",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Helper JWT ───────────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.Akun:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid atau sudah kedaluwarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        id_akun: int = payload.get("id_akun")
        if id_akun is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception
    akun = crud.get_akun(db, id_akun)
    if akun is None:
        raise credentials_exception
    return akun

def require_admin(current_user: models.Akun = Depends(get_current_user)) -> models.Akun:
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Akses ditolak: hanya admin")
    return current_user


# ─── Seeder: Akun Master Admin ────────────────────────────────────────────────

@app.on_event("startup")
def seed_master_admin():
    db = next(get_db())
    try:
        existing = crud.get_akun_by_username(db, "qoulansadid")
        if not existing:
            akun_data = schemas.AkunCreate(
                username="qoulansadid",
                password="123",
                nama="Administrator",
                role=schemas.RoleEnum.admin,
            )
            new_akun = crud.create_akun(db, akun_data)
            admin_data = schemas.AdminCreate(id_akun=new_akun.id_akun)
            crud.create_admin(db, admin_data)
            print("✅ Master admin berhasil dibuat  |  username: masteradmin  |  password: admin123")
        else:
            print("ℹ️  Master admin sudah ada, seeder dilewati.")
    finally:
        db.close()


# ══════════════════════════════════════════════════════════════════════════════
# ROOT
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/", tags=["Root"])
def root():
    return {"message": "Sistem Informasi Sekolah API berjalan!", "docs": "/docs"}

@app.get("/health", tags=["Root"])
def health():
    return {"status": "ok"}


# ══════════════════════════════════════════════════════════════════════════════
# AUTH — LOGIN
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/auth/login", response_model=schemas.Token, tags=["Auth"])
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Login dengan username & password. Mengembalikan JWT access token."""
    akun = crud.authenticate_akun(db, payload.username, payload.password)
    if not akun:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token_data = {
        "id_akun":  akun.id_akun,
        "username": akun.username,
        "role":     akun.role.value,
    }
    access_token = create_access_token(token_data)
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/auth/me", response_model=schemas.AkunOut, tags=["Auth"])
def me(current_user: models.Akun = Depends(get_current_user)):
    """Ambil data akun yang sedang login berdasarkan token."""
    return current_user


# ══════════════════════════════════════════════════════════════════════════════
# AKUN
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/akun/", response_model=schemas.AkunOut, status_code=201, tags=["Akun"])
def create_akun(
    akun: schemas.AkunCreate,
    db: Session = Depends(get_db),
    _: models.Akun = Depends(require_admin),
):
    """Buat akun baru. (Hanya admin)"""
    if crud.get_akun_by_username(db, akun.username):
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    return crud.create_akun(db=db, akun=akun)

@app.get("/akun/", response_model=List[schemas.AkunOut], tags=["Akun"])
def list_akun(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: models.Akun = Depends(require_admin),
):
    """Ambil semua data akun. (Hanya admin)"""
    return crud.get_all_akun(db, skip=skip, limit=limit)

@app.get("/akun/{id_akun}", response_model=schemas.AkunOut, tags=["Akun"])
def get_akun(
    id_akun: int,
    db: Session = Depends(get_db),
    _: models.Akun = Depends(get_current_user),
):
    """Ambil data akun berdasarkan ID."""
    db_akun = crud.get_akun(db, id_akun)
    if not db_akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return db_akun

@app.put("/akun/{id_akun}", response_model=schemas.AkunOut, tags=["Akun"])
def update_akun(
    id_akun: int,
    akun: schemas.AkunUpdate,
    db: Session = Depends(get_db),
    _: models.Akun = Depends(require_admin),
):
    """Update data akun. (Hanya admin)"""
    db_akun = crud.update_akun(db, id_akun, akun)
    if not db_akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return db_akun

@app.delete("/akun/{id_akun}", tags=["Akun"])
def delete_akun(
    id_akun: int,
    db: Session = Depends(get_db),
    _: models.Akun = Depends(require_admin),
):
    """Hapus akun berdasarkan ID. (Hanya admin)"""
    if not crud.delete_akun(db, id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return {"message": f"Akun {id_akun} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/admin/", response_model=schemas.AdminOut, status_code=201, tags=["Admin"])
def create_admin(
    admin: schemas.AdminCreate,
    db: Session = Depends(get_db),
    _: models.Akun = Depends(require_admin),
):
    """Daftarkan akun sebagai admin. (Hanya admin)"""
    if not crud.get_akun(db, admin.id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    if crud.get_admin_by_akun(db, admin.id_akun):
        raise HTTPException(status_code=400, detail="Akun sudah terdaftar sebagai admin")
    return crud.create_admin(db=db, admin=admin)

@app.get("/admin/", response_model=List[schemas.AdminOut], tags=["Admin"])
def list_admin(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: models.Akun = Depends(require_admin),
):
    """Ambil semua data admin. (Hanya admin)"""
    return crud.get_all_admin(db, skip=skip, limit=limit)

@app.get("/admin/{id_admin}", response_model=schemas.AdminOut, tags=["Admin"])
def get_admin(
    id_admin: int,
    db: Session = Depends(get_db),
    _: models.Akun = Depends(require_admin),
):
    """Ambil data admin berdasarkan ID. (Hanya admin)"""
    db_admin = crud.get_admin(db, id_admin)
    if not db_admin:
        raise HTTPException(status_code=404, detail="Admin tidak ditemukan")
    return db_admin

@app.delete("/admin/{id_admin}", tags=["Admin"])
def delete_admin(
    id_admin: int,
    db: Session = Depends(get_db),
    _: models.Akun = Depends(require_admin),
):
    """Hapus data admin berdasarkan ID. (Hanya admin)"""
    if not crud.delete_admin(db, id_admin):
        raise HTTPException(status_code=404, detail="Admin tidak ditemukan")
    return {"message": f"Admin {id_admin} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# RESET PASSWORD
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/reset-password/", response_model=schemas.ResetPasswordOut, status_code=201, tags=["Reset Password"])
def create_reset_password(rp: schemas.ResetPasswordCreate, db: Session = Depends(get_db)):
    """Buat pertanyaan keamanan untuk reset password. (Tidak perlu login — untuk flow registrasi)"""
    if not crud.get_akun(db, rp.id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return crud.create_reset_password(db=db, rp=rp)

@app.get("/reset-password/", response_model=List[schemas.ResetPasswordOut], tags=["Reset Password"])
def list_reset_password(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    _: models.Akun = Depends(require_admin),
):
    """Ambil semua data pertanyaan reset password. (Hanya admin)"""
    return crud.get_all_reset_password(db, skip=skip, limit=limit)

@app.get("/reset-password/{id_pertanyaan}", response_model=schemas.ResetPasswordOut, tags=["Reset Password"])
def get_reset_password(
    id_pertanyaan: int,
    db: Session = Depends(get_db),
    _: models.Akun = Depends(get_current_user),
):
    """Ambil pertanyaan reset password berdasarkan ID."""
    db_rp = crud.get_reset_password(db, id_pertanyaan)
    if not db_rp:
        raise HTTPException(status_code=404, detail="Pertanyaan tidak ditemukan")
    return db_rp

@app.get("/reset-password/akun/{id_akun}", response_model=schemas.ResetPasswordOut, tags=["Reset Password"])
def get_reset_password_by_akun(id_akun: int, db: Session = Depends(get_db)):
    """Ambil pertanyaan reset password berdasarkan ID akun. (Publik — untuk flow lupa password)"""
    if not crud.get_akun(db, id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    db_rp = crud.get_reset_password_by_akun(db, id_akun)
    if not db_rp:
        raise HTTPException(status_code=404, detail="Pertanyaan tidak ditemukan")
    return db_rp

@app.put("/reset-password/{id_pertanyaan}", response_model=schemas.ResetPasswordOut, tags=["Reset Password"])
def update_reset_password(
    id_pertanyaan: int,
    rp: schemas.ResetPasswordUpdate,
    db: Session = Depends(get_db),
    _: models.Akun = Depends(get_current_user),
):
    """Update pertanyaan dan jawaban keamanan."""
    db_rp = crud.update_reset_password(db, id_pertanyaan, rp)
    if not db_rp:
        raise HTTPException(status_code=404, detail="Pertanyaan tidak ditemukan")
    return db_rp

@app.delete("/reset-password/{id_pertanyaan}", tags=["Reset Password"])
def delete_reset_password(
    id_pertanyaan: int,
    db: Session = Depends(get_db),
    _: models.Akun = Depends(require_admin),
):
    """Hapus pertanyaan reset password. (Hanya admin)"""
    if not crud.delete_reset_password(db, id_pertanyaan):
        raise HTTPException(status_code=404, detail="Pertanyaan tidak ditemukan")
    return {"message": f"Pertanyaan {id_pertanyaan} berhasil dihapus"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)