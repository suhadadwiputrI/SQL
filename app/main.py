from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from typing import List
from datetime import date
import uvicorn

from app.database import engine, get_db, Base
from app import models, schemas, crud

# Create all tables
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Sistem Informasi Sekolah API",
    description="REST API untuk sistem absensi, catatan harian, laporan, dan komunikasi sekolah.",
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
# AUTH
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/login", tags=["Auth"])
def login(request: schemas.LoginRequest, db: Session = Depends(get_db)):
    """Login dengan username dan password. Mengembalikan data akun jika berhasil."""
    akun = crud.get_akun_by_username(db, request.username)
    if not akun or not crud.verify_password(request.password, akun.hashed_password):
        raise HTTPException(status_code=401, detail="Username atau password salah!")
    return {
        "message": "Login berhasil",
        "data": schemas.AkunOut.model_validate(akun)
    }


# ══════════════════════════════════════════════════════════════════════════════
# AKUN
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/akun/", response_model=schemas.AkunOut, status_code=201, tags=["Akun"])
def create_akun(akun: schemas.AkunCreate, db: Session = Depends(get_db)):
    existing = crud.get_akun_by_username(db, akun.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username sudah digunakan")
    return crud.create_akun(db=db, akun=akun)

@app.get("/akun/", response_model=List[schemas.AkunOut], tags=["Akun"])
def list_akun(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_all_akun(db, skip=skip, limit=limit)

@app.get("/akun/{id_akun}", response_model=schemas.AkunOut, tags=["Akun"])
def get_akun(id_akun: int, db: Session = Depends(get_db)):
    db_akun = crud.get_akun(db, id_akun)
    if not db_akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return db_akun

@app.put("/akun/{id_akun}", response_model=schemas.AkunOut, tags=["Akun"])
def update_akun(id_akun: int, akun: schemas.AkunUpdate, db: Session = Depends(get_db)):
    db_akun = crud.update_akun(db, id_akun, akun)
    if not db_akun:
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return db_akun

@app.delete("/akun/{id_akun}", tags=["Akun"])
def delete_akun(id_akun: int, db: Session = Depends(get_db)):
    if not crud.delete_akun(db, id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return {"message": f"Akun {id_akun} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# KELAS
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/kelas/", response_model=schemas.KelasOut, status_code=201, tags=["Kelas"])
def create_kelas(kelas: schemas.KelasCreate, db: Session = Depends(get_db)):
    return crud.create_kelas(db=db, kelas=kelas)

@app.get("/kelas/", response_model=List[schemas.KelasOut], tags=["Kelas"])
def list_kelas(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_all_kelas(db, skip=skip, limit=limit)

@app.get("/kelas/{id_kelas}", response_model=schemas.KelasOut, tags=["Kelas"])
def get_kelas(id_kelas: int, db: Session = Depends(get_db)):
    db_kelas = crud.get_kelas(db, id_kelas)
    if not db_kelas:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return db_kelas

@app.put("/kelas/{id_kelas}", response_model=schemas.KelasOut, tags=["Kelas"])
def update_kelas(id_kelas: int, kelas: schemas.KelasUpdate, db: Session = Depends(get_db)):
    db_kelas = crud.update_kelas(db, id_kelas, kelas)
    if not db_kelas:
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return db_kelas

@app.delete("/kelas/{id_kelas}", tags=["Kelas"])
def delete_kelas(id_kelas: int, db: Session = Depends(get_db)):
    if not crud.delete_kelas(db, id_kelas):
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return {"message": f"Kelas {id_kelas} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# SISWA
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/siswa/", response_model=schemas.SiswaOut, status_code=201, tags=["Siswa"])
def create_siswa(siswa: schemas.SiswaCreate, db: Session = Depends(get_db)):
    if crud.get_siswa_by_nisn(db, siswa.nisn):
        raise HTTPException(status_code=400, detail="NISN sudah terdaftar")
    if not crud.get_kelas(db, siswa.id_kelas):
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return crud.create_siswa(db=db, siswa=siswa)

@app.get("/siswa/", response_model=List[schemas.SiswaOut], tags=["Siswa"])
def list_siswa(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_all_siswa(db, skip=skip, limit=limit)

@app.get("/siswa/{id_siswa}", response_model=schemas.SiswaOut, tags=["Siswa"])
def get_siswa(id_siswa: int, db: Session = Depends(get_db)):
    db_siswa = crud.get_siswa(db, id_siswa)
    if not db_siswa:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return db_siswa

@app.get("/kelas/{id_kelas}/siswa", response_model=List[schemas.SiswaOut], tags=["Siswa"])
def list_siswa_by_kelas(id_kelas: int, db: Session = Depends(get_db)):
    if not crud.get_kelas(db, id_kelas):
        raise HTTPException(status_code=404, detail="Kelas tidak ditemukan")
    return crud.get_siswa_by_kelas(db, id_kelas)

@app.put("/siswa/{id_siswa}", response_model=schemas.SiswaOut, tags=["Siswa"])
def update_siswa(id_siswa: int, siswa: schemas.SiswaUpdate, db: Session = Depends(get_db)):
    db_siswa = crud.update_siswa(db, id_siswa, siswa)
    if not db_siswa:
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return db_siswa

@app.delete("/siswa/{id_siswa}", tags=["Siswa"])
def delete_siswa(id_siswa: int, db: Session = Depends(get_db)):
    if not crud.delete_siswa(db, id_siswa):
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return {"message": f"Siswa {id_siswa} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# WALI SISWA
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/wali-siswa/", response_model=schemas.WaliSiswaOut, status_code=201, tags=["Wali Siswa"])
def create_wali_siswa(wali: schemas.WaliSiswaCreate, db: Session = Depends(get_db)):
    if not crud.get_akun(db, wali.id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return crud.create_wali_siswa(db=db, wali=wali)

@app.get("/wali-siswa/", response_model=List[schemas.WaliSiswaOut], tags=["Wali Siswa"])
def list_wali_siswa(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_all_wali_siswa(db, skip=skip, limit=limit)

@app.get("/wali-siswa/{id_wali_siswa}", response_model=schemas.WaliSiswaOut, tags=["Wali Siswa"])
def get_wali_siswa(id_wali_siswa: int, db: Session = Depends(get_db)):
    db_wali = crud.get_wali_siswa(db, id_wali_siswa)
    if not db_wali:
        raise HTTPException(status_code=404, detail="Wali siswa tidak ditemukan")
    return db_wali

@app.put("/wali-siswa/{id_wali_siswa}", response_model=schemas.WaliSiswaOut, tags=["Wali Siswa"])
def update_wali_siswa(id_wali_siswa: int, wali: schemas.WaliSiswaUpdate, db: Session = Depends(get_db)):
    db_wali = crud.update_wali_siswa(db, id_wali_siswa, wali)
    if not db_wali:
        raise HTTPException(status_code=404, detail="Wali siswa tidak ditemukan")
    return db_wali

@app.delete("/wali-siswa/{id_wali_siswa}", tags=["Wali Siswa"])
def delete_wali_siswa(id_wali_siswa: int, db: Session = Depends(get_db)):
    if not crud.delete_wali_siswa(db, id_wali_siswa):
        raise HTTPException(status_code=404, detail="Wali siswa tidak ditemukan")
    return {"message": f"Wali siswa {id_wali_siswa} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# GURU
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/guru/", response_model=schemas.GuruOut, status_code=201, tags=["Guru"])
def create_guru(guru: schemas.GuruCreate, db: Session = Depends(get_db)):
    if not crud.get_akun(db, guru.id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    if crud.get_guru_by_nip(db, guru.nip):
        raise HTTPException(status_code=400, detail="NIP sudah terdaftar")
    return crud.create_guru(db=db, guru=guru)

@app.get("/guru/", response_model=List[schemas.GuruOut], tags=["Guru"])
def list_guru(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_all_guru(db, skip=skip, limit=limit)

@app.get("/guru/{id_guru}", response_model=schemas.GuruOut, tags=["Guru"])
def get_guru(id_guru: int, db: Session = Depends(get_db)):
    db_guru = crud.get_guru(db, id_guru)
    if not db_guru:
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return db_guru

@app.put("/guru/{id_guru}", response_model=schemas.GuruOut, tags=["Guru"])
def update_guru(id_guru: int, guru: schemas.GuruUpdate, db: Session = Depends(get_db)):
    db_guru = crud.update_guru(db, id_guru, guru)
    if not db_guru:
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return db_guru

@app.delete("/guru/{id_guru}", tags=["Guru"])
def delete_guru(id_guru: int, db: Session = Depends(get_db)):
    if not crud.delete_guru(db, id_guru):
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return {"message": f"Guru {id_guru} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# KEPALA SEKOLAH
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/kepala-sekolah/", response_model=schemas.KepalaSekolahOut, status_code=201, tags=["Kepala Sekolah"])
def create_kepsek(kepsek: schemas.KepalaSekolahCreate, db: Session = Depends(get_db)):
    if not crud.get_akun(db, kepsek.id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return crud.create_kepsek(db=db, kepsek=kepsek)

@app.get("/kepala-sekolah/", response_model=List[schemas.KepalaSekolahOut], tags=["Kepala Sekolah"])
def list_kepsek(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_all_kepsek(db, skip=skip, limit=limit)

@app.get("/kepala-sekolah/{id_kepsek}", response_model=schemas.KepalaSekolahOut, tags=["Kepala Sekolah"])
def get_kepsek(id_kepsek: int, db: Session = Depends(get_db)):
    db_kepsek = crud.get_kepsek(db, id_kepsek)
    if not db_kepsek:
        raise HTTPException(status_code=404, detail="Kepala sekolah tidak ditemukan")
    return db_kepsek

@app.put("/kepala-sekolah/{id_kepsek}", response_model=schemas.KepalaSekolahOut, tags=["Kepala Sekolah"])
def update_kepsek(id_kepsek: int, kepsek: schemas.KepalaSekolahUpdate, db: Session = Depends(get_db)):
    db_kepsek = crud.update_kepsek(db, id_kepsek, kepsek)
    if not db_kepsek:
        raise HTTPException(status_code=404, detail="Kepala sekolah tidak ditemukan")
    return db_kepsek

@app.delete("/kepala-sekolah/{id_kepsek}", tags=["Kepala Sekolah"])
def delete_kepsek(id_kepsek: int, db: Session = Depends(get_db)):
    if not crud.delete_kepsek(db, id_kepsek):
        raise HTTPException(status_code=404, detail="Kepala sekolah tidak ditemukan")
    return {"message": f"Kepala sekolah {id_kepsek} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# RESET PASSWORD
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/reset-password/", response_model=schemas.ResetPasswordOut, status_code=201, tags=["Reset Password"])
def create_reset_password(rp: schemas.ResetPasswordCreate, db: Session = Depends(get_db)):
    if not crud.get_akun(db, rp.id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return crud.create_reset_password(db=db, rp=rp)

@app.get("/reset-password/{id_pertanyaan}", response_model=schemas.ResetPasswordOut, tags=["Reset Password"])
def get_reset_password(id_pertanyaan: int, db: Session = Depends(get_db)):
    db_rp = crud.get_reset_password(db, id_pertanyaan)
    if not db_rp:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")
    return db_rp

@app.put("/reset-password/{id_pertanyaan}", response_model=schemas.ResetPasswordOut, tags=["Reset Password"])
def update_reset_password(id_pertanyaan: int, rp: schemas.ResetPasswordUpdate, db: Session = Depends(get_db)):
    db_rp = crud.update_reset_password(db, id_pertanyaan, rp)
    if not db_rp:
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")
    return db_rp

@app.delete("/reset-password/{id_pertanyaan}", tags=["Reset Password"])
def delete_reset_password(id_pertanyaan: int, db: Session = Depends(get_db)):
    if not crud.delete_reset_password(db, id_pertanyaan):
        raise HTTPException(status_code=404, detail="Data tidak ditemukan")
    return {"message": f"Reset password {id_pertanyaan} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# ABSENSI
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/absensi/", response_model=schemas.AbsensiOut, status_code=201, tags=["Absensi"])
def create_absensi(absensi: schemas.AbsensiCreate, db: Session = Depends(get_db)):
    if not crud.get_siswa(db, absensi.id_siswa):
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    if not crud.get_guru(db, absensi.id_guru):
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return crud.create_absensi(db=db, absensi=absensi)

@app.get("/absensi/", response_model=List[schemas.AbsensiOut], tags=["Absensi"])
def list_absensi(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_all_absensi(db, skip=skip, limit=limit)

@app.get("/absensi/{id_absensi}", response_model=schemas.AbsensiOut, tags=["Absensi"])
def get_absensi(id_absensi: int, db: Session = Depends(get_db)):
    db_absensi = crud.get_absensi(db, id_absensi)
    if not db_absensi:
        raise HTTPException(status_code=404, detail="Absensi tidak ditemukan")
    return db_absensi

@app.get("/absensi/siswa/{id_siswa}", response_model=List[schemas.AbsensiOut], tags=["Absensi"])
def list_absensi_by_siswa(id_siswa: int, db: Session = Depends(get_db)):
    if not crud.get_siswa(db, id_siswa):
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return crud.get_absensi_by_siswa(db, id_siswa)

@app.get("/absensi/tanggal/{tanggal}", response_model=List[schemas.AbsensiOut], tags=["Absensi"])
def list_absensi_by_tanggal(tanggal: date, db: Session = Depends(get_db)):
    return crud.get_absensi_by_tanggal(db, tanggal)

@app.put("/absensi/{id_absensi}", response_model=schemas.AbsensiOut, tags=["Absensi"])
def update_absensi(id_absensi: int, absensi: schemas.AbsensiUpdate, db: Session = Depends(get_db)):
    db_absensi = crud.update_absensi(db, id_absensi, absensi)
    if not db_absensi:
        raise HTTPException(status_code=404, detail="Absensi tidak ditemukan")
    return db_absensi

@app.delete("/absensi/{id_absensi}", tags=["Absensi"])
def delete_absensi(id_absensi: int, db: Session = Depends(get_db)):
    if not crud.delete_absensi(db, id_absensi):
        raise HTTPException(status_code=404, detail="Absensi tidak ditemukan")
    return {"message": f"Absensi {id_absensi} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# CATATAN HARIAN
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/catatan-harian/", response_model=schemas.CatatanHarianOut, status_code=201, tags=["Catatan Harian"])
def create_catatan(catatan: schemas.CatatanHarianCreate, db: Session = Depends(get_db)):
    if not crud.get_siswa(db, catatan.id_siswa):
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    if not crud.get_guru(db, catatan.id_guru):
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return crud.create_catatan(db=db, catatan=catatan)

@app.get("/catatan-harian/", response_model=List[schemas.CatatanHarianOut], tags=["Catatan Harian"])
def list_catatan(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_all_catatan(db, skip=skip, limit=limit)

@app.get("/catatan-harian/{id_catatan}", response_model=schemas.CatatanHarianOut, tags=["Catatan Harian"])
def get_catatan(id_catatan: int, db: Session = Depends(get_db)):
    db_catatan = crud.get_catatan(db, id_catatan)
    if not db_catatan:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    return db_catatan

@app.get("/catatan-harian/siswa/{id_siswa}", response_model=List[schemas.CatatanHarianOut], tags=["Catatan Harian"])
def list_catatan_by_siswa(id_siswa: int, db: Session = Depends(get_db)):
    if not crud.get_siswa(db, id_siswa):
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return crud.get_catatan_by_siswa(db, id_siswa)

@app.put("/catatan-harian/{id_catatan}", response_model=schemas.CatatanHarianOut, tags=["Catatan Harian"])
def update_catatan(id_catatan: int, catatan: schemas.CatatanHarianUpdate, db: Session = Depends(get_db)):
    db_catatan = crud.update_catatan(db, id_catatan, catatan)
    if not db_catatan:
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    return db_catatan

@app.delete("/catatan-harian/{id_catatan}", tags=["Catatan Harian"])
def delete_catatan(id_catatan: int, db: Session = Depends(get_db)):
    if not crud.delete_catatan(db, id_catatan):
        raise HTTPException(status_code=404, detail="Catatan tidak ditemukan")
    return {"message": f"Catatan {id_catatan} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# LAPORAN
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/laporan/", response_model=schemas.LaporanOut, status_code=201, tags=["Laporan"])
def create_laporan(laporan: schemas.LaporanCreate, db: Session = Depends(get_db)):
    if not crud.get_siswa(db, laporan.id_siswa):
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    if not crud.get_guru(db, laporan.id_guru):
        raise HTTPException(status_code=404, detail="Guru tidak ditemukan")
    return crud.create_laporan(db=db, laporan=laporan)

@app.get("/laporan/", response_model=List[schemas.LaporanOut], tags=["Laporan"])
def list_laporan(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_all_laporan(db, skip=skip, limit=limit)

@app.get("/laporan/{id_laporan}", response_model=schemas.LaporanOut, tags=["Laporan"])
def get_laporan(id_laporan: int, db: Session = Depends(get_db)):
    db_laporan = crud.get_laporan(db, id_laporan)
    if not db_laporan:
        raise HTTPException(status_code=404, detail="Laporan tidak ditemukan")
    return db_laporan

@app.get("/laporan/siswa/{id_siswa}", response_model=List[schemas.LaporanOut], tags=["Laporan"])
def list_laporan_by_siswa(id_siswa: int, db: Session = Depends(get_db)):
    if not crud.get_siswa(db, id_siswa):
        raise HTTPException(status_code=404, detail="Siswa tidak ditemukan")
    return crud.get_laporan_by_siswa(db, id_siswa)

@app.put("/laporan/{id_laporan}", response_model=schemas.LaporanOut, tags=["Laporan"])
def update_laporan(id_laporan: int, laporan: schemas.LaporanUpdate, db: Session = Depends(get_db)):
    db_laporan = crud.update_laporan(db, id_laporan, laporan)
    if not db_laporan:
        raise HTTPException(status_code=404, detail="Laporan tidak ditemukan")
    return db_laporan

@app.delete("/laporan/{id_laporan}", tags=["Laporan"])
def delete_laporan(id_laporan: int, db: Session = Depends(get_db)):
    if not crud.delete_laporan(db, id_laporan):
        raise HTTPException(status_code=404, detail="Laporan tidak ditemukan")
    return {"message": f"Laporan {id_laporan} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# PESAN
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/pesan/", response_model=schemas.PesanOut, status_code=201, tags=["Pesan"])
def create_pesan(pesan: schemas.PesanCreate, db: Session = Depends(get_db)):
    if not crud.get_akun(db, pesan.id_pengirim):
        raise HTTPException(status_code=404, detail="Akun pengirim tidak ditemukan")
    if not crud.get_akun(db, pesan.id_penerima):
        raise HTTPException(status_code=404, detail="Akun penerima tidak ditemukan")
    return crud.create_pesan(db=db, pesan=pesan)

@app.get("/pesan/", response_model=List[schemas.PesanOut], tags=["Pesan"])
def list_pesan(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_all_pesan(db, skip=skip, limit=limit)

@app.get("/pesan/{id_pesan}", response_model=schemas.PesanOut, tags=["Pesan"])
def get_pesan(id_pesan: int, db: Session = Depends(get_db)):
    db_pesan = crud.get_pesan(db, id_pesan)
    if not db_pesan:
        raise HTTPException(status_code=404, detail="Pesan tidak ditemukan")
    return db_pesan

@app.get("/pesan/akun/{id_akun}", response_model=List[schemas.PesanOut], tags=["Pesan"])
def list_pesan_by_akun(id_akun: int, db: Session = Depends(get_db)):
    if not crud.get_akun(db, id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return crud.get_pesan_by_akun(db, id_akun)

@app.put("/pesan/{id_pesan}", response_model=schemas.PesanOut, tags=["Pesan"])
def update_pesan(id_pesan: int, pesan: schemas.PesanUpdate, db: Session = Depends(get_db)):
    db_pesan = crud.update_pesan(db, id_pesan, pesan)
    if not db_pesan:
        raise HTTPException(status_code=404, detail="Pesan tidak ditemukan")
    return db_pesan

@app.delete("/pesan/{id_pesan}", tags=["Pesan"])
def delete_pesan(id_pesan: int, db: Session = Depends(get_db)):
    if not crud.delete_pesan(db, id_pesan):
        raise HTTPException(status_code=404, detail="Pesan tidak ditemukan")
    return {"message": f"Pesan {id_pesan} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFIKASI
# ══════════════════════════════════════════════════════════════════════════════

@app.post("/notifikasi/", response_model=schemas.NotifikasiOut, status_code=201, tags=["Notifikasi"])
def create_notifikasi(notif: schemas.NotifikasiCreate, db: Session = Depends(get_db)):
    if not crud.get_akun(db, notif.id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return crud.create_notifikasi(db=db, notif=notif)

@app.get("/notifikasi/", response_model=List[schemas.NotifikasiOut], tags=["Notifikasi"])
def list_notifikasi(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return crud.get_all_notifikasi(db, skip=skip, limit=limit)

@app.get("/notifikasi/{id_notif}", response_model=schemas.NotifikasiOut, tags=["Notifikasi"])
def get_notifikasi(id_notif: int, db: Session = Depends(get_db)):
    db_notif = crud.get_notifikasi(db, id_notif)
    if not db_notif:
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
    return db_notif

@app.get("/notifikasi/akun/{id_akun}", response_model=List[schemas.NotifikasiOut], tags=["Notifikasi"])
def list_notifikasi_by_akun(id_akun: int, db: Session = Depends(get_db)):
    if not crud.get_akun(db, id_akun):
        raise HTTPException(status_code=404, detail="Akun tidak ditemukan")
    return crud.get_notifikasi_by_akun(db, id_akun)

@app.put("/notifikasi/{id_notif}", response_model=schemas.NotifikasiOut, tags=["Notifikasi"])
def update_notifikasi(id_notif: int, notif: schemas.NotifikasiUpdate, db: Session = Depends(get_db)):
    db_notif = crud.update_notifikasi(db, id_notif, notif)
    if not db_notif:
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
    return db_notif

@app.delete("/notifikasi/{id_notif}", tags=["Notifikasi"])
def delete_notifikasi(id_notif: int, db: Session = Depends(get_db)):
    if not crud.delete_notifikasi(db, id_notif):
        raise HTTPException(status_code=404, detail="Notifikasi tidak ditemukan")
    return {"message": f"Notifikasi {id_notif} berhasil dihapus"}


# ══════════════════════════════════════════════════════════════════════════════
# STARTUP EVENT — seed akun admin default
# ══════════════════════════════════════════════════════════════════════════════

@app.on_event("startup")
def seed_default_admin():
    """Otomatis buat akun admin default saat server pertama kali jalan."""
    db = next(get_db())
    try:
        existing = crud.get_akun_by_username(db, "admin")
        if not existing:
            akun_data = schemas.AkunCreate(
                username="admin",
                password="admin123",
                nama="Administrator",
                role=schemas.RoleEnum.admin
            )
            crud.create_akun(db=db, akun=akun_data)
            print("✅ Akun admin default berhasil dibuat (username: admin, password: admin123)")
        else:
            print("ℹ️  Akun admin sudah ada, skip seeding.")
    finally:
        db.close()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)