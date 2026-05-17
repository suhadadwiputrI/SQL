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
ACCESS_TOKEN_EXPIRE_MINUTES = 1440

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MainApp")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Smart School API Backend", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=UPLOAD_DIR), name="static")

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")


# ─── Auth Dependency ──────────────────────────────────────────────────────────

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)) -> models.Akun:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid atau kedaluwarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except jwt.PyJWTError:
        raise credentials_exception

    akun = crud.get_akun_by_username(db, username=username)
    if akun is None:
        raise credentials_exception
    return akun


def _get_guru_or_403(db: Session, id_akun: int) -> models.Guru:
    guru = crud.get_guru_by_akun(db, id_akun)
    if not guru:
        raise HTTPException(status_code=404, detail="Data guru tidak ditemukan")
    return guru

def _cek_guru_boleh_akses_kelas(guru: models.Guru, id_kelas: int):
    """
    BUG FIX: Validasi bahwa guru hanya boleh mengakses kelas yang ada
    di list id_kelas mereka. Jika id_kelas NULL atau kosong, guru tidak
    boleh mengakses kelas apapun (bukan malah bisa mengakses semua).
    """
    from app.crud import decode_id_kelas
    kelas_guru = decode_id_kelas(guru.id_kelas)   # [] jika NULL
    if not kelas_guru or id_kelas not in kelas_guru:
        raise HTTPException(
            status_code=403,
            detail=f"Anda tidak memiliki akses ke kelas {id_kelas}"
        )


# ─── Auth Router ──────────────────────────────────────────────────────────────

@app.post("/login", response_model=schemas.LoginResponse)
def login(payload: schemas.LoginRequest, db: Session = Depends(get_db)):
    akun = crud.authenticate_user(db, payload.username, payload.password)
    if not akun:
        raise HTTPException(status_code=400, detail="Username atau password salah")

    access_token = jwt.encode({"sub": akun.username}, SECRET_KEY, algorithm=ALGORITHM)

    profile_nama = ""
    id_entitas = None

    if akun.role == models.RoleEnum.admin:
        profile_nama = "Administrator"
    elif akun.role == models.RoleEnum.guru:
        guru = crud.get_guru_by_akun(db, akun.id_akun)
        if guru:
            profile_nama = guru.nama_guru
            id_entitas = guru.id_guru
    elif akun.role == models.RoleEnum.ortu:
        ortu = crud.get_ortu_by_akun(db, akun.id_akun)
        if ortu:
            profile_nama = ortu.nama_ortu
            id_entitas = ortu.id_ortu

    res_akun = schemas.AkunResponse(
        id_akun=akun.id_akun,
        username=akun.username,
        role=akun.role.value,
        profile_nama=profile_nama,
        id_entitas=id_entitas
    )
    return {"token": access_token, "akun": res_akun}


# ─── Admin Router (Kelola Akun, Guru, Ortu, Kelas, Siswa) ─────────────────────

@app.get("/akun", response_model=List[schemas.AkunResponse])
def read_all_akun(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    raw_list = crud.get_all_akun(db, skip, limit)
    res = []
    for a in raw_list:
        p_nama = ""
        id_ent = None
        if a.role == models.RoleEnum.guru:
            g = crud.get_guru_by_akun(db, a.id_akun)
            if g:
                p_nama = g.nama_guru
                id_ent = g.id_guru
        elif a.role == models.RoleEnum.ortu:
            o = crud.get_ortu_by_akun(db, a.id_akun)
            if o:
                p_nama = o.nama_ortu
                id_ent = o.id_ortu
        elif a.role == models.RoleEnum.admin:
            p_nama = "Administrator"

        res.append(schemas.AkunResponse(
            id_akun=a.id_akun,
            username=a.username,
            role=a.role.value,
            profile_nama=p_nama,
            id_entitas=id_ent
        ))
    return res


@app.post("/akun/guru", response_model=schemas.GuruResponse)
def create_guru_dan_akun(payload: schemas.GuruCreateWithAkun, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    if crud.get_akun_by_username(db, payload.username):
        raise HTTPException(status_code=400, detail="Username sudah terdaftar")
    return crud.create_guru_with_akun(db, payload)


@app.get("/guru", response_model=List[schemas.GuruResponse])
def read_all_guru(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    return crud.get_all_guru(db, skip, limit)


@app.put("/guru/{id_guru}", response_model=schemas.GuruResponse)
def update_guru(id_guru: int, payload: schemas.GuruUpdate, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    g = crud.update_guru(db, id_guru, payload)
    if not g:
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return g


@app.delete("/guru/{id_guru}")
def delete_guru(id_guru: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    if crud.delete_guru(db, id_guru):
        return {"detail": "Guru dan akun berhasil dihapus"}
    raise HTTPException(status_code=404, detail="Guru tidak ditemukan")


@app.post("/akun/ortu", response_model=schemas.OrtuResponse)
def create_ortu_dan_akun(payload: schemas.OrtuCreateWithAkun, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    if crud.get_akun_by_username(db, payload.username):
        raise HTTPException(status_code=400, detail="Username sudah terdaftar")
    return crud.create_ortu_with_akun(db, payload)


@app.get("/ortu", response_model=List[schemas.OrtuResponse])
def read_all_ortu(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    return crud.get_all_ortu(db, skip, limit)


@app.put("/ortu/{id_ortu}", response_model=schemas.OrtuResponse)
def update_ortu(id_ortu: int, payload: schemas.OrtuUpdate, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    o = crud.update_ortu(db, id_ortu, payload)
    if not o:
        raise HTTPException(status_code=404, detail="Ortu tidak ditemukan")
    return o


@app.delete("/ortu/{id_ortu}")
def delete_ortu(id_ortu: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    if crud.delete_ortu(db, id_ortu):
        return {"detail": "Ortu dan akun berhasil dihapus"}
    raise HTTPException(status_code=404, detail="Ortu tidak ditemukan")


@app.post("/kelas", response_model=schemas.KelasResponse)
def create_kelas(payload: schemas.KelasCreate, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    return crud.create_kelas(db, payload)


@app.get("/kelas", response_model=List[schemas.KelasResponse])
def read_all_kelas(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    return crud.get_all_kelas(db, skip, limit)


@app.put("/kelas/{id_kelas}", response_model=schemas.KelasResponse)
def update_kelas(id_kelas: int, payload: schemas.KelasUpdate, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    k = crud.update_kelas(db, id_kelas, payload)
    if not k:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return k


@app.delete("/kelas/{id_kelas}")
def delete_kelas(id_kelas: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    if crud.delete_kelas(db, id_kelas):
        return {"detail": "Kelas berhasil dihapus"}
    raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")


@app.post("/siswa", response_model=schemas.SiswaResponse)
def create_siswa(payload: schemas.SiswaCreate, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    return crud.create_siswa(db, payload)


@app.get("/siswa", response_model=List[schemas.SiswaResponse])
def read_all_siswa(skip: int = 0, limit: int = 100, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    return crud.get_all_siswa(db, skip, limit)


@app.put("/siswa/{id_siswa}", response_model=schemas.SiswaResponse)
def update_siswa(id_siswa: int, payload: schemas.SiswaUpdate, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    s = crud.update_siswa(db, id_siswa, payload)
    if not s:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return s


@app.delete("/siswa/{id_siswa}")
def delete_siswa(id_siswa: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Hanya admin yang dapat mengakses")
    if crud.delete_siswa(db, id_siswa):
        return {"detail": "Siswa berhasil dihapus"}
    raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")


# ─── Guru / Absensi Router ────────────────────────────────────────────────────

@app.get("/absensi/kelas/{id_kelas}", response_model=List[schemas.SiswaAbsensiItem])
def get_siswa_absensi(id_kelas: int, tanggal: date, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")
    if not crud.get_kelas(db, id_kelas):
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    # BUG FIX: validasi guru hanya bisa akses kelas yang ditugaskan
    guru = _get_guru_or_403(db, current_user.id_akun)
    _cek_guru_boleh_akses_kelas(guru, id_kelas)

    siswa_list = db.query(models.Siswa).filter(models.Siswa.id_kelas == id_kelas).order_by(models.Siswa.nama_siswa.asc()).all()
    res = []
    for s in siswa_list:
        absensi = db.query(models.Absensi).filter(models.Absensi.id_siswa == s.id_siswa, models.Absensi.tanggal == tanggal).first()
        status_val = absensi.status.value if absensi else None
        keterangan_val = absensi.keterangan if absensi else None
        res.append(schemas.SiswaAbsensiItem(
            id_siswa=s.id_siswa,
            nama_siswa=s.nama_siswa,
            nisn=s.nisn,
            status=status_val,
            keterangan=keterangan_val
        ))
    return res


@app.post("/absensi/batch")
def simpan_absensi_batch(payload: schemas.AbsensiBatchRequest, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat mengakses")
    guru = _get_guru_or_403(db, current_user.id_akun)
    # BUG FIX: validasi guru hanya bisa simpan absensi ke kelas yang ditugaskan
    _cek_guru_boleh_akses_kelas(guru, payload.id_kelas)
    hasil = []

    for item in payload.items:
        absensi = db.query(models.Absensi).filter(
            models.Absensi.id_siswa == item.id_siswa,
            models.Absensi.tanggal == payload.tanggal
        ).first()

        if absensi:
            absensi.status = models.StatusAbsensiEnum(item.status)
            absensi.keterangan = item.keterangan
        else:
            absensi = models.Absensi(
                id_siswa=item.id_siswa,
                tanggal=payload.tanggal,
                status=models.StatusAbsensiEnum(item.status),
                keterangan=item.keterangan
            )
            db.add(absensi)
        hasil.append(absensi)

    db.commit()
    return {"detail": f"Berhasil menyimpan {len(hasil)} absensi kelas {payload.id_kelas}"}


# ─── Guru / Catatan Harian Router ─────────────────────────────────────────────

@app.post("/catatan/", response_model=schemas.CatatanHarianResponse)
def buat_catatan(payload: schemas.CatatanHarianCreate, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat membuat catatan")
    guru = _get_guru_or_403(db, current_user.id_akun)
    if payload.target == models.TargetCatatanEnum.satu_kelas:
        if not crud.get_kelas(db, payload.id_kelas):
            raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
        # BUG FIX: validasi guru hanya bisa buat catatan untuk kelas yang ditugaskan
        _cek_guru_boleh_akses_kelas(guru, payload.id_kelas)
    if payload.target == models.TargetCatatanEnum.satu_siswa:
        siswa = crud.get_siswa(db, payload.id_siswa)
        if not siswa:
            raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
        # BUG FIX: validasi siswa yang dituju ada di kelas guru yang bersangkutan
        if siswa.id_kelas is not None:
            _cek_guru_boleh_akses_kelas(guru, siswa.id_kelas)

    catatan = models.CatatanHarian(
        id_guru=guru.id_guru,
        judul=payload.judul,
        isi=payload.isi,
        target=models.TargetCatatanEnum(payload.target),
        id_kelas=payload.id_kelas,
        id_siswa=payload.id_siswa,
        tanggal=date.today()
    )
    db.add(catatan)
    db.commit()
    db.refresh(catatan)

    # Push Notification via WebSocket secara Async
    asyncio.create_task(notifikasi_push_catatan(db, catatan))

    return catatan


async def notifikasi_push_catatan(db: Session, catatan: models.CatatanHarian):
    try:
        targets_id_akun = []
        if catatan.target == models.TargetCatatanEnum.semua:
            ortu_list = db.query(models.Ortu).all()
            targets_id_akun = [o.id_akun for o in ortu_list if o.id_akun]
        elif catatan.target == models.TargetCatatanEnum.satu_kelas:
            siswa_list = db.query(models.Siswa).filter(models.Siswa.id_kelas == catatan.id_kelas).all()
            id_siswa_arr = [s.id_siswa for s in siswa_list]
            ortu_list = db.query(models.Ortu).filter(models.Ortu.id_siswa.in_(id_siswa_arr)).all()
            targets_id_akun = [o.id_akun for o in ortu_list if o.id_akun]
        elif catatan.target == models.TargetCatatanEnum.satu_siswa:
            ortu_list = db.query(models.Ortu).filter(models.Ortu.id_siswa == catatan.id_siswa).all()
            targets_id_akun = [o.id_akun for o in ortu_list if o.id_akun]

        for id_ak in targets_id_akun:
            notif = models.Notifikasi(
                id_akun=id_ak,
                judul=f"Catatan Baru: {catatan.judul}",
                isi=catatan.isi,
                tipe="catatan",
                referensi_id=catatan.id_catatan,
                sudah_dibaca=False,
                tanggal=datetime.now()
            )
            db.add(notif)
        db.commit()

        for id_ak in targets_id_akun:
            await ws_manager.send_personal_message(
                id_ak,
                json.dumps({
                    "tipe": "catatan",
                    "judul": f"Catatan Baru: {catatan.judul}",
                    "isi": catatan.isi,
                    "referensi_id": catatan.id_catatan
                })
            )
    except Exception as e:
        logger.error(f"Gagal memproses notifikasi push: {str(e)}")


@app.post("/catatan/{id_catatan}/foto")
async def upload_foto_catatan(id_catatan: int, file: UploadFile = File(...), db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Akses ditolak")
    catatan = db.query(models.CatatanHarian).filter(models.CatatanHarian.id_catatan == id_catatan).first()
    if not catatan:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")

    ext = os.path.splitext(file.filename)[1]
    filename = f"catatan_{id_catatan}_{uuid.uuid4().hex}{ext}"
    filepath = os.path.join(UPLOAD_DIR, filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    catatan.foto_url = f"/static/{filename}"
    db.commit()
    return {"foto_url": catatan.foto_url}


# ─── Ortu / Dashboard Home & Detail Siswa ────────────────────────────────────

@app.get("/ortu/siswa/dashboard", response_model=schemas.OrtuSiswaDashboardResponse)
def get_dashboard_siswa_ortu(db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.ortu:
        raise HTTPException(status_code=403, detail="Hanya orang tua yang dapat mengakses")
    ortu = crud.get_ortu_by_akun(db, current_user.id_akun)
    if not ortu or not ortu.id_siswa:
        raise HTTPException(status_code=404, detail="Siswa belum terikat ke akun orang tua ini")

    siswa = db.query(models.Siswa).filter(models.Siswa.id_siswa == ortu.id_siswa).first()
    if not siswa:
        raise HTTPException(status_code=404, detail="Data siswa tidak ditemukan")

    kelas_nama = siswa.kelas.nama_kelas if siswa.kelas else "-"

    today = date.today()
    absensi_today = db.query(models.Absensi).filter(models.Absensi.id_siswa == siswa.id_siswa, models.Absensi.tanggal == today).first()
    status_absensi_hari_ini = absensi_today.status.value if absensi_today else "Belum Absen"

    # Hitung rekap bulanan (bulan berjalan saat ini)
    current_month = today.month
    current_year = today.year
    absensi_bulan_ini = db.query(models.Absensi).filter(
        models.Absensi.id_siswa == siswa.id_siswa,
        extract('month', models.Absensi.tanggal) == current_month,
        extract('year', models.Absensi.tanggal) == current_year
    ).all()

    hadir, sakit, izin, alpha = 0, 0, 0, 0
    for a in absensi_bulan_ini:
        if a.status == models.StatusAbsensiEnum.hadir: hadir += 1
        elif a.status == models.StatusAbsensiEnum.sakit: sakit += 1
        elif a.status == models.StatusAbsensiEnum.izin: izin += 1
        elif a.status == models.StatusAbsensiEnum.alpha: alpha += 1

    rekap_bulan_ini = schemas.RekapAbsensiBulanan(
        hadir=hadir, sakit=sakit, izin=izin, alpha=alpha,
        total_hari=len(absensi_bulan_ini)
    )

    # Ambil catatan harian yang relevan (Target semua, Target kelas siswa ini, atau khusus Target siswa ini)
    catatan_list = db.query(models.CatatanHarian).filter(
        or_(
            models.CatatanHarian.target == models.TargetCatatanEnum.semua,
            and_(models.CatatanHarian.target == models.TargetCatatanEnum.satu_kelas, models.CatatanHarian.id_kelas == siswa.id_kelas),
            and_(models.CatatanHarian.target == models.TargetCatatanEnum.satu_siswa, models.CatatanHarian.id_siswa == siswa.id_siswa)
        )
    ).order_by(models.CatatanHarian.id_catatan.desc()).limit(20).all()

    catatan_res = []
    for c in catatan_list:
        catatan_res.append(schemas.CatatanHarianResponse(
            id_catatan=c.id_catatan,
            id_guru=c.id_guru,
            nama_guru=c.guru.nama_guru if c.guru else "Guru",
            judul=c.judul,
            isi=c.isi,
            target=c.target.value,
            id_kelas=c.id_kelas,
            id_siswa=c.id_siswa,
            foto_url=c.foto_url,
            tanggal=c.tanggal
        ))

    return schemas.OrtuSiswaDashboardResponse(
        id_siswa=siswa.id_siswa,
        nama_siswa=siswa.nama_siswa,
        nisn=siswa.nisn,
        kelas_nama=kelas_nama,
        status_absensi_hari_ini=status_absensi_hari_ini,
        rekap_bulan_ini=rekap_bulan_ini,
        catatan_harian=catatan_res
    )


# ─── Notifikasi List & Real-time Update ───────────────────────────────────────

@app.get("/notifikasi", response_model=schemas.NotifikasiListResponse)
def get_notifikasi_list(skip: int = 0, limit: int = 50, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    items = db.query(models.Notifikasi).filter(models.Notifikasi.id_akun == current_user.id_akun).order_by(models.Notifikasi.tanggal.desc()).offset(skip).limit(limit).all()
    total_belum_dibaca = db.query(models.Notifikasi).filter(models.Notifikasi.id_akun == current_user.id_akun, models.Notifikasi.sudah_dibaca == False).count()

    res_items = []
    for i in items:
        res_items.append(schemas.NotifikasiItem(
            id_notifikasi=i.id_notifikasi,
            judul=i.judul,
            isi=i.isi,
            tipe=i.tipe,
            referensi_id=i.referensi_id,
            sudah_dibaca=i.sudah_dibaca,
            tanggal=i.tanggal
        ))
    return schemas.NotifikasiListResponse(total_belum_dibaca=total_belum_dibaca, items=res_items)


@app.post("/notifikasi/baca-semua")
def tandai_semua_notifikasi_dibaca(db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    db.query(models.Notifikasi).filter(models.Notifikasi.id_akun == current_user.id_akun, models.Notifikasi.sudah_dibaca == False).update({"sudah_dibaca": True}, synchronize_session=False)
    db.commit()
    return {"detail": "Semua notifikasi berhasil ditandai telah dibaca"}


# ─── Percakapan (Pesan / Chatting) Router ──────────────────────────────────────

@app.get("/percakapan/kontak", response_model=List[schemas.KontakResponse])
def get_daftar_kontak_chat(db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    res = []
    if current_user.role == models.RoleEnum.guru:
        ortu_list = db.query(models.Ortu).all()
        for o in ortu_list:
            if not o.id_akun: continue
            siswa_nama = o.siswa.nama_siswa if o.siswa else "Siswa"
            kelas_nama = o.siswa.kelas.nama_kelas if (o.siswa and o.siswa.kelas) else ""
            sub_label = f"Wali Murid dari {siswa_nama} ({kelas_nama})" if kelas_nama else f"Wali Murid dari {siswa_nama}"
            res.append(schemas.KontakResponse(
                id_akun_tujuan=o.id_akun,
                nama_tujuan=o.nama_ortu,
                sub_label=sub_label,
                role_tujuan="ortu"
            ))
    elif current_user.role == models.RoleEnum.ortu:
        guru_list = db.query(models.Guru).all()
        for g in guru_list:
            if not g.id_akun: continue
            from app.crud import decode_id_kelas
            arr_id = decode_id_kelas(g.id_kelas)
            kelas_names = []
            if arr_id:
                k_models = db.query(models.Kelas).filter(models.Kelas.id_kelas.in_(arr_id)).all()
                kelas_names = [km.nama_kelas for km in k_models]
            sub = f"Guru Kelas: {', '.join(kelas_names)}" if kelas_names else "Guru Sekolah"
            res.append(schemas.KontakResponse(
                id_akun_tujuan=g.id_akun,
                nama_tujuan=g.nama_guru,
                sub_label=sub,
                role_tujuan="guru"
            ))
    return res


@app.get("/percakapan/riwayat/{id_lawan}", response_model=List[schemas.PesanResponse])
def get_riwayat_chat(id_lawan: int, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    pesan_list = db.query(models.Pesan).filter(
        or_(
            and_(models.Pesan.id_pengirim == current_user.id_akun, models.Pesan.id_penerima == id_lawan),
            and_(models.Pesan.id_pengirim == id_lawan, models.Pesan.id_penerima == current_user.id_akun)
        )
    ).order_by(models.Pesan.id_pesan.asc()).all()

    res = []
    for p in pesan_list:
        res.append(schemas.PesanResponse(
            id_pesan=p.id_pesan,
            id_pengirim=p.id_pengirim,
            id_penerima=p.id_penerima,
            isi_pesan=p.isi_pesan,
            sudah_dibaca=p.sudah_dibaca,
            tanggal=p.tanggal
        ))

    db.query(models.Pesan).filter(
        models.Pesan.id_pengirim == id_lawan,
        models.Pesan.id_penerima == current_user.id_akun,
        models.Pesan.sudah_dibaca == False
    ).update({"sudah_dibaca": True}, synchronize_session=False)
    db.commit()

    return res


@app.post("/percakapan/kirim", response_model=schemas.PesanResponse)
async def kirim_pesan_chat(payload: schemas.PesanKirimRequest, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    pesan = models.Pesan(
        id_pengirim=current_user.id_akun,
        id_penerima=payload.id_penerima,
        isi_pesan=payload.isi_pesan,
        sudah_dibaca=False,
        tanggal=datetime.now()
    )
    db.add(pesan)
    db.commit()
    db.refresh(pesan)

    # Kirim real-time jika websocket tujuan aktif terhubung
    await ws_manager.send_personal_message(
        payload.id_penerima,
        json.dumps({
            "tipe": "chat",
            "id_pesan": pesan.id_pesan,
            "id_pengirim": pesan.id_pengirim,
            "isi_pesan": pesan.isi_pesan,
            "tanggal": pesan.tanggal.isoformat()
        })
    )
    return pesan


# ─── Laporan Summary / Cetak Router ──────────────────────────────────────────

router_laporan = APIRouter(prefix="/laporan", tags=["Laporan"])

@router_laporan.get("/absensi", response_model=schemas.LaporanAbsensiKelasResponse)
def get_laporan_absensi(
    id_kelas: int = Query(..., description="ID kelas"),
    tanggal_awal: date = Query(..., description="Format: yyyy-MM-dd"),
    tanggal_akhir: date = Query(..., description="Format: yyyy-MM-dd"),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if tanggal_awal > tanggal_akhir:
        raise HTTPException(status_code=400, detail="tanggal_awal tidak boleh lebih besar dari tanggal_akhir")
    # BUG FIX: validasi guru hanya bisa lihat laporan kelas yang ditugaskan
    if current_user.role == models.RoleEnum.guru:
        guru = _get_guru_or_403(db, current_user.id_akun)
        _cek_guru_boleh_akses_kelas(guru, id_kelas)
    result = crud.get_laporan_absensi_kelas_range(db, id_kelas, tanggal_awal, tanggal_akhir)
    if not result:
        raise HTTPException(status_code=404, detail="Data kelas tidak ditemukan")
    return result


@router_laporan.get("/catatan", response_model=schemas.LaporanCatatanKelasResponse)
def get_laporan_catatan(
    id_kelas: int = Query(..., description="ID kelas"),
    tanggal_awal: date = Query(..., description="Format: yyyy-MM-dd"),
    tanggal_akhir: date = Query(..., description="Format: yyyy-MM-dd"),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if tanggal_awal > tanggal_akhir:
        raise HTTPException(status_code=400, detail="tanggal_awal tidak boleh lebih besar dari tanggal_akhir")
    # BUG FIX: validasi guru hanya bisa lihat laporan kelas yang ditugaskan
    if current_user.role == models.RoleEnum.guru:
        guru = _get_guru_or_403(db, current_user.id_akun)
        _cek_guru_boleh_akses_kelas(guru, id_kelas)
    result = crud.get_laporan_catatan_kelas_range(db, id_kelas, tanggal_awal, tanggal_akhir)
    if not result:
        raise HTTPException(status_code=404, detail="Data kelas tidak ditemukan")
    return result


@router_laporan.post("/buat")
def buat_laporan(payload: schemas.LaporanCreateRequest, db: Session = Depends(get_db), current_user: models.Akun = Depends(get_current_user)):
    if current_user.role != models.RoleEnum.guru:
        raise HTTPException(status_code=403, detail="Hanya guru yang dapat membuat laporan")

    # Validasi duplikasi laporan berdasarkan id_siswa dan periode
    exist = db.query(models.Laporan).filter(
        models.Laporan.id_siswa == payload.id_siswa,
        models.Laporan.periode == payload.periode
    ).first()
    if exist:
        raise HTTPException(status_code=409, detail=f"Laporan siswa ID {payload.id_siswa} untuk periode {payload.periode} sudah ada")

    laporan = models.Laporan(
        id_siswa=payload.id_siswa,
        periode=payload.periode,
        tanggal_dibuat=payload.tanggal_dibuat,
        keterangan=payload.keterangan
    )
    db.add(laporan)
    db.commit()
    db.refresh(laporan)
    return laporan


@router_laporan.get("/pdf/absensi")
def download_pdf_absensi(
    id_kelas: int = Query(..., description="ID kelas"),
    tanggal_awal: date = Query(..., description="Format: yyyy-MM-dd"),
    tanggal_akhir: date = Query(..., description="Format: yyyy-MM-dd"),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if tanggal_awal > tanggal_akhir:
        raise HTTPException(status_code=400, detail="tanggal_awal > tanggal_akhir")
    # BUG FIX: validasi guru hanya bisa download PDF kelas yang ditugaskan
    if current_user.role == models.RoleEnum.guru:
        guru = _get_guru_or_403(db, current_user.id_akun)
        _cek_guru_boleh_akses_kelas(guru, id_kelas)
    data = crud.get_laporan_absensi_kelas_range(db, id_kelas, tanggal_awal, tanggal_akhir)
    if not data:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")

    pdf_bytes = generate_pdf_absensi_kelas(data)
    filename = f"laporan_absensi_{data.nama_kelas}_{tanggal_awal}_to_{tanggal_akhir}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router_laporan.get("/pdf/catatan-siswa")
def download_pdf_catatan_siswa(
    id_siswa: int = Query(..., description="ID Siswa"),
    tanggal_awal: date = Query(..., description="Format: yyyy-MM-dd"),
    tanggal_akhir: date = Query(..., description="Format: yyyy-MM-dd"),
    db: Session = Depends(get_db),
    current_user: models.Akun = Depends(get_current_user),
):
    if tanggal_awal > tanggal_akhir:
        raise HTTPException(status_code=400, detail="tanggal_awal > tanggal_akhir")

    siswa = crud.get_siswa(db, id_siswa)
    if not siswa:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")

    if current_user.role == models.RoleEnum.guru:
        guru = _get_guru_or_403(db, current_user.id_akun)
        if siswa.id_kelas is not None:
            _cek_guru_boleh_akses_kelas(guru, siswa.id_kelas)

    data = crud.get_laporan_catatan_siswa_range(db, id_siswa, tanggal_awal, tanggal_akhir)
    pdf_bytes = generate_pdf_catatan_siswa(data)
    filename = f"catatan_harian_{data.nama_siswa.replace(' ', '_')}_{tanggal_awal}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


def generate_pdf_absensi_kelas(data: schemas.LaporanAbsensiKelasResponse) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=landscape(A4),
        rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=1.5*cm, bottomMargin=1.5*cm
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "TitleStyle", parent=styles["Heading1"], fontSize=16,
        leading=20, alignment=TA_CENTER, textColor=colors.HexColor("#2C3E50")
    )
    sub_style = ParagraphStyle(
        "SubStyle", parent=styles["Normal"], fontSize=10,
        leading=14, alignment=TA_CENTER, textColor=colors.HexColor("#7F8C8D")
    )
    cell_style = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=9, leading=11)
    header_style = ParagraphStyle("HeaderCell", parent=styles["Normal"], fontSize=9, leading=11, textColor=colors.white)

    elements = []
    elements.append(Paragraph(f"LAPORAN REKAPITULASI ABSENSI SISWA", title_style))
    elements.append(Paragraph(f"Kelas: {data.nama_kelas}  |  Periode: {data.rentang_tanggal}", sub_style))
    elements.append(Spacer(1, 0.5*cm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#BDC3C7"), spaceAfter=15))

    table_data = [[
        Paragraph("<b>No</b>", header_style),
        Paragraph("<b>Nama Siswa</b>", header_style),
        Paragraph("<b>NISN</b>", header_style),
        Paragraph("<b>Hadir</b>", header_style),
        Paragraph("<b>Sakit</b>", header_style),
        Paragraph("<b>Izin</b>", header_style),
        Paragraph("<b>Alpha</b>", header_style),
        Paragraph("<b>Total Hari</b>", header_style),
    ]]

    for idx, s in enumerate(data.siswa, 1):
        table_data.append([
            Paragraph(str(idx), cell_style),
            Paragraph(s.nama_siswa, cell_style),
            Paragraph(s.nisn or "-", cell_style),
            Paragraph(f"{s.hadir} hari", cell_style),
            Paragraph(f"{s.sakit} hari", cell_style),
            Paragraph(f"{s.izin} hari", cell_style),
            Paragraph(f"{s.alpha} hari", cell_style),
            Paragraph(f"{s.total_hari} hari", cell_style),
        ])

    tbl = Table(table_data, colWidths=[1*cm, 7*cm, 3*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 2.5*cm])
    tbl.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#F9F9F9")]),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(tbl)
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


def generate_pdf_catatan_siswa(data: schemas.LaporanCatatanSiswaResponse) -> bytes:
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("T", parent=styles["Heading1"], fontSize=15, leading=18, alignment=TA_CENTER, textColor=colors.HexColor("#16A085"))
    sub_style = ParagraphStyle("S", parent=styles["Normal"], fontSize=10, leading=14, alignment=TA_CENTER, textColor=colors.grey)
    cell_style = ParagraphStyle("C", parent=styles["Normal"], fontSize=9, leading=12)
    header_style = ParagraphStyle("H", parent=styles["Normal"], fontSize=9, leading=12, textColor=colors.white)

    elements = []
    elements.append(Paragraph("LAPORAN CATATAN HARIAN PERKEMBANGAN SISWA", title_style))
    elements.append(Paragraph(f"Nama: {data.nama_siswa} ({data.nisn or '-'})  |  Kelas: {data.nama_kelas}", sub_style))
    elements.append(Paragraph(f"Periode Evaluasi: {data.rentang_tanggal}", sub_style))
    elements.append(Spacer(1, 0.4*cm))
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#BDC3C7"), spaceAfter=12))

    if not data.catatan:
        elements.append(Paragraph("<i>Tidak ada rekaman catatan harian guru pada periode ini.</i>", cell_style))
    else:
        table_data = [[
            Paragraph("<b>No</b>", header_style),
            Paragraph("<b>Tanggal</b>", header_style),
            Paragraph("<b>Judul Catatan / Materi Evaluasi</b>", header_style),
            Paragraph("<b>Isi Keterangan Perkembangan</b>", header_style),
            Paragraph("<b>Saran Masukan Guru</b>", header_style),
        ]]
        for idx, c in enumerate(data.catatan, 1):
            table_data.append([
                Paragraph(str(idx), cell_style),
                Paragraph(c.tanggal.strftime("%d/%m/%Y"), cell_style),
                Paragraph(f"<b>{c.judul}</b>", cell_style),
                Paragraph(c.isi, cell_style),
                Paragraph("", cell_style)
            ])
        tbl = Table(table_data, colWidths=[1*cm, 2.2*cm, 4.3*cm, 6.5*cm, 3.5*cm])
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#16A085")),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#BDC3C7")),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#FDFDFD")]),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
        ]))
        elements.append(tbl)
        elements.append(Spacer(1, 0.4*cm))
        style_note = ParagraphStyle("Note", parent=styles["Normal"], fontSize=8, textColor=colors.HexColor("#777777"))
        elements.append(Paragraph("* Kolom Saran dikosongkan dan dapat diisi secara manual setelah dicetak.", style_note))
        elements.append(Paragraph(f"* Total catatan: {data.jumlah_catatan} catatan", style_note))
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()


# ─── Daftarkan router laporan ─────────────────────────────────────────────────
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
    except WebSocketDisconnect:
        ws_manager.disconnect(id_akun)
    except Exception as e:
        logger.error(f"Error pada WS Client {id_akun}: {str(e)}")
        ws_manager.disconnect(id_akun)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)