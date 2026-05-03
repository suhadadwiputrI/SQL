from sqlalchemy.orm import Session
from passlib.context import CryptContext
from typing import Optional, List
from datetime import date

from app import models, schemas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


# ══════════════════════════════════════════════════════════════════════════════
# AKUN
# ══════════════════════════════════════════════════════════════════════════════

def get_akun(db: Session, id_akun: int) -> Optional[models.Akun]:
    return db.query(models.Akun).filter(models.Akun.id_akun == id_akun).first()

def get_akun_by_username(db: Session, username: str) -> Optional[models.Akun]:
    return db.query(models.Akun).filter(models.Akun.username == username).first()

def get_all_akun(db: Session, skip: int = 0, limit: int = 100) -> List[models.Akun]:
    return db.query(models.Akun).offset(skip).limit(limit).all()

def create_akun(db: Session, akun: schemas.AkunCreate) -> models.Akun:
    db_akun = models.Akun(
        username=akun.username,
        hashed_password=hash_password(akun.password),
        nama=akun.nama,
        role=akun.role,
    )
    db.add(db_akun)
    db.commit()
    db.refresh(db_akun)
    return db_akun

def update_akun(db: Session, id_akun: int, akun: schemas.AkunUpdate) -> Optional[models.Akun]:
    db_akun = get_akun(db, id_akun)
    if not db_akun:
        return None
    for key, value in akun.model_dump(exclude_unset=True).items():
        setattr(db_akun, key, value)
    db.commit()
    db.refresh(db_akun)
    return db_akun

def delete_akun(db: Session, id_akun: int) -> bool:
    db_akun = get_akun(db, id_akun)
    if not db_akun:
        return False
    db.delete(db_akun)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# KELAS
# ══════════════════════════════════════════════════════════════════════════════

def get_kelas(db: Session, id_kelas: int) -> Optional[models.Kelas]:
    return db.query(models.Kelas).filter(models.Kelas.id_kelas == id_kelas).first()

def get_all_kelas(db: Session, skip: int = 0, limit: int = 100) -> List[models.Kelas]:
    return db.query(models.Kelas).offset(skip).limit(limit).all()

def create_kelas(db: Session, kelas: schemas.KelasCreate) -> models.Kelas:
    db_kelas = models.Kelas(**kelas.model_dump())
    db.add(db_kelas)
    db.commit()
    db.refresh(db_kelas)
    return db_kelas

def update_kelas(db: Session, id_kelas: int, kelas: schemas.KelasUpdate) -> Optional[models.Kelas]:
    db_kelas = get_kelas(db, id_kelas)
    if not db_kelas:
        return None
    for key, value in kelas.model_dump(exclude_unset=True).items():
        setattr(db_kelas, key, value)
    db.commit()
    db.refresh(db_kelas)
    return db_kelas

def delete_kelas(db: Session, id_kelas: int) -> bool:
    db_kelas = get_kelas(db, id_kelas)
    if not db_kelas:
        return False
    db.delete(db_kelas)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# SISWA
# ══════════════════════════════════════════════════════════════════════════════

def get_siswa(db: Session, id_siswa: int) -> Optional[models.Siswa]:
    return db.query(models.Siswa).filter(models.Siswa.id_siswa == id_siswa).first()

def get_siswa_by_nisn(db: Session, nisn: str) -> Optional[models.Siswa]:
    return db.query(models.Siswa).filter(models.Siswa.nisn == nisn).first()

def get_all_siswa(db: Session, skip: int = 0, limit: int = 100) -> List[models.Siswa]:
    return db.query(models.Siswa).offset(skip).limit(limit).all()

def get_siswa_by_kelas(db: Session, id_kelas: int) -> List[models.Siswa]:
    return db.query(models.Siswa).filter(models.Siswa.id_kelas == id_kelas).all()

def create_siswa(db: Session, siswa: schemas.SiswaCreate) -> models.Siswa:
    db_siswa = models.Siswa(**siswa.model_dump())
    db.add(db_siswa)
    db.commit()
    db.refresh(db_siswa)
    return db_siswa

def update_siswa(db: Session, id_siswa: int, siswa: schemas.SiswaUpdate) -> Optional[models.Siswa]:
    db_siswa = get_siswa(db, id_siswa)
    if not db_siswa:
        return None
    for key, value in siswa.model_dump(exclude_unset=True).items():
        setattr(db_siswa, key, value)
    db.commit()
    db.refresh(db_siswa)
    return db_siswa

def delete_siswa(db: Session, id_siswa: int) -> bool:
    db_siswa = get_siswa(db, id_siswa)
    if not db_siswa:
        return False
    db.delete(db_siswa)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# WALI SISWA
# ══════════════════════════════════════════════════════════════════════════════

def get_wali_siswa(db: Session, id_wali_siswa: int) -> Optional[models.WaliSiswa]:
    return db.query(models.WaliSiswa).filter(models.WaliSiswa.id_wali_siswa == id_wali_siswa).first()

def get_all_wali_siswa(db: Session, skip: int = 0, limit: int = 100) -> List[models.WaliSiswa]:
    return db.query(models.WaliSiswa).offset(skip).limit(limit).all()

def create_wali_siswa(db: Session, wali: schemas.WaliSiswaCreate) -> models.WaliSiswa:
    db_wali = models.WaliSiswa(**wali.model_dump())
    db.add(db_wali)
    db.commit()
    db.refresh(db_wali)
    return db_wali

def update_wali_siswa(db: Session, id_wali_siswa: int, wali: schemas.WaliSiswaUpdate) -> Optional[models.WaliSiswa]:
    db_wali = get_wali_siswa(db, id_wali_siswa)
    if not db_wali:
        return None
    for key, value in wali.model_dump(exclude_unset=True).items():
        setattr(db_wali, key, value)
    db.commit()
    db.refresh(db_wali)
    return db_wali

def delete_wali_siswa(db: Session, id_wali_siswa: int) -> bool:
    db_wali = get_wali_siswa(db, id_wali_siswa)
    if not db_wali:
        return False
    db.delete(db_wali)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# GURU
# ══════════════════════════════════════════════════════════════════════════════

def get_guru(db: Session, id_guru: int) -> Optional[models.Guru]:
    return db.query(models.Guru).filter(models.Guru.id_guru == id_guru).first()

def get_guru_by_nip(db: Session, nip: str) -> Optional[models.Guru]:
    return db.query(models.Guru).filter(models.Guru.nip == nip).first()

def get_all_guru(db: Session, skip: int = 0, limit: int = 100) -> List[models.Guru]:
    return db.query(models.Guru).offset(skip).limit(limit).all()

def create_guru(db: Session, guru: schemas.GuruCreate) -> models.Guru:
    db_guru = models.Guru(**guru.model_dump())
    db.add(db_guru)
    db.commit()
    db.refresh(db_guru)
    return db_guru

def update_guru(db: Session, id_guru: int, guru: schemas.GuruUpdate) -> Optional[models.Guru]:
    db_guru = get_guru(db, id_guru)
    if not db_guru:
        return None
    for key, value in guru.model_dump(exclude_unset=True).items():
        setattr(db_guru, key, value)
    db.commit()
    db.refresh(db_guru)
    return db_guru

def delete_guru(db: Session, id_guru: int) -> bool:
    db_guru = get_guru(db, id_guru)
    if not db_guru:
        return False
    db.delete(db_guru)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# KEPALA SEKOLAH
# ══════════════════════════════════════════════════════════════════════════════

def get_kepsek(db: Session, id_kepsek: int) -> Optional[models.KepalaSekolah]:
    return db.query(models.KepalaSekolah).filter(models.KepalaSekolah.id_kepsek == id_kepsek).first()

def get_all_kepsek(db: Session, skip: int = 0, limit: int = 100) -> List[models.KepalaSekolah]:
    return db.query(models.KepalaSekolah).offset(skip).limit(limit).all()

def create_kepsek(db: Session, kepsek: schemas.KepalaSekolahCreate) -> models.KepalaSekolah:
    db_kepsek = models.KepalaSekolah(**kepsek.model_dump())
    db.add(db_kepsek)
    db.commit()
    db.refresh(db_kepsek)
    return db_kepsek

def update_kepsek(db: Session, id_kepsek: int, kepsek: schemas.KepalaSekolahUpdate) -> Optional[models.KepalaSekolah]:
    db_kepsek = get_kepsek(db, id_kepsek)
    if not db_kepsek:
        return None
    for key, value in kepsek.model_dump(exclude_unset=True).items():
        setattr(db_kepsek, key, value)
    db.commit()
    db.refresh(db_kepsek)
    return db_kepsek

def delete_kepsek(db: Session, id_kepsek: int) -> bool:
    db_kepsek = get_kepsek(db, id_kepsek)
    if not db_kepsek:
        return False
    db.delete(db_kepsek)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# ADMIN
# ══════════════════════════════════════════════════════════════════════════════

def get_admin(db: Session, id_admin: int) -> Optional[models.Admin]:
    return db.query(models.Admin).filter(models.Admin.id_admin == id_admin).first()

def get_all_admin(db: Session, skip: int = 0, limit: int = 100) -> List[models.Admin]:
    return db.query(models.Admin).offset(skip).limit(limit).all()

def create_admin(db: Session, admin: schemas.AdminCreate) -> models.Admin:
    db_admin = models.Admin(**admin.model_dump())
    db.add(db_admin)
    db.commit()
    db.refresh(db_admin)
    return db_admin

def delete_admin(db: Session, id_admin: int) -> bool:
    db_admin = get_admin(db, id_admin)
    if not db_admin:
        return False
    db.delete(db_admin)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# RESET PASSWORD
# ══════════════════════════════════════════════════════════════════════════════

def get_reset_password(db: Session, id_pertanyaan: int) -> Optional[models.ResetPassword]:
    return db.query(models.ResetPassword).filter(models.ResetPassword.id_pertanyaan == id_pertanyaan).first()

def get_reset_password_by_akun(db: Session, id_akun: int) -> Optional[models.ResetPassword]:
    return db.query(models.ResetPassword).filter(models.ResetPassword.id_akun == id_akun).first()

def create_reset_password(db: Session, rp: schemas.ResetPasswordCreate) -> models.ResetPassword:
    db_rp = models.ResetPassword(**rp.model_dump())
    db.add(db_rp)
    db.commit()
    db.refresh(db_rp)
    return db_rp

def update_reset_password(db: Session, id_pertanyaan: int, rp: schemas.ResetPasswordUpdate) -> Optional[models.ResetPassword]:
    db_rp = get_reset_password(db, id_pertanyaan)
    if not db_rp:
        return None
    for key, value in rp.model_dump(exclude_unset=True).items():
        setattr(db_rp, key, value)
    db.commit()
    db.refresh(db_rp)
    return db_rp

def delete_reset_password(db: Session, id_pertanyaan: int) -> bool:
    db_rp = get_reset_password(db, id_pertanyaan)
    if not db_rp:
        return False
    db.delete(db_rp)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# ABSENSI
# ══════════════════════════════════════════════════════════════════════════════

def get_absensi(db: Session, id_absensi: int) -> Optional[models.Absensi]:
    return db.query(models.Absensi).filter(models.Absensi.id_absensi == id_absensi).first()

def get_all_absensi(db: Session, skip: int = 0, limit: int = 100) -> List[models.Absensi]:
    return db.query(models.Absensi).offset(skip).limit(limit).all()

def get_absensi_by_siswa(db: Session, id_siswa: int) -> List[models.Absensi]:
    return db.query(models.Absensi).filter(models.Absensi.id_siswa == id_siswa).all()

def get_absensi_by_tanggal(db: Session, tanggal: date) -> List[models.Absensi]:
    return db.query(models.Absensi).filter(models.Absensi.tanggal == tanggal).all()

def create_absensi(db: Session, absensi: schemas.AbsensiCreate) -> models.Absensi:
    db_absensi = models.Absensi(**absensi.model_dump())
    db.add(db_absensi)
    db.commit()
    db.refresh(db_absensi)
    return db_absensi

def update_absensi(db: Session, id_absensi: int, absensi: schemas.AbsensiUpdate) -> Optional[models.Absensi]:
    db_absensi = get_absensi(db, id_absensi)
    if not db_absensi:
        return None
    for key, value in absensi.model_dump(exclude_unset=True).items():
        setattr(db_absensi, key, value)
    db.commit()
    db.refresh(db_absensi)
    return db_absensi

def delete_absensi(db: Session, id_absensi: int) -> bool:
    db_absensi = get_absensi(db, id_absensi)
    if not db_absensi:
        return False
    db.delete(db_absensi)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# CATATAN HARIAN
# ══════════════════════════════════════════════════════════════════════════════

def get_catatan(db: Session, id_catatan: int) -> Optional[models.CatatanHarian]:
    return db.query(models.CatatanHarian).filter(models.CatatanHarian.id_catatan == id_catatan).first()

def get_all_catatan(db: Session, skip: int = 0, limit: int = 100) -> List[models.CatatanHarian]:
    return db.query(models.CatatanHarian).offset(skip).limit(limit).all()

def get_catatan_by_siswa(db: Session, id_siswa: int) -> List[models.CatatanHarian]:
    return db.query(models.CatatanHarian).filter(models.CatatanHarian.id_siswa == id_siswa).all()

def create_catatan(db: Session, catatan: schemas.CatatanHarianCreate) -> models.CatatanHarian:
    db_catatan = models.CatatanHarian(**catatan.model_dump())
    db.add(db_catatan)
    db.commit()
    db.refresh(db_catatan)
    return db_catatan

def update_catatan(db: Session, id_catatan: int, catatan: schemas.CatatanHarianUpdate) -> Optional[models.CatatanHarian]:
    db_catatan = get_catatan(db, id_catatan)
    if not db_catatan:
        return None
    for key, value in catatan.model_dump(exclude_unset=True).items():
        setattr(db_catatan, key, value)
    db.commit()
    db.refresh(db_catatan)
    return db_catatan

def delete_catatan(db: Session, id_catatan: int) -> bool:
    db_catatan = get_catatan(db, id_catatan)
    if not db_catatan:
        return False
    db.delete(db_catatan)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# LAPORAN
# ══════════════════════════════════════════════════════════════════════════════

def get_laporan(db: Session, id_laporan: int) -> Optional[models.Laporan]:
    return db.query(models.Laporan).filter(models.Laporan.id_laporan == id_laporan).first()

def get_all_laporan(db: Session, skip: int = 0, limit: int = 100) -> List[models.Laporan]:
    return db.query(models.Laporan).offset(skip).limit(limit).all()

def get_laporan_by_siswa(db: Session, id_siswa: int) -> List[models.Laporan]:
    return db.query(models.Laporan).filter(models.Laporan.id_siswa == id_siswa).all()

def create_laporan(db: Session, laporan: schemas.LaporanCreate) -> models.Laporan:
    db_laporan = models.Laporan(**laporan.model_dump())
    db.add(db_laporan)
    db.commit()
    db.refresh(db_laporan)
    return db_laporan

def update_laporan(db: Session, id_laporan: int, laporan: schemas.LaporanUpdate) -> Optional[models.Laporan]:
    db_laporan = get_laporan(db, id_laporan)
    if not db_laporan:
        return None
    for key, value in laporan.model_dump(exclude_unset=True).items():
        setattr(db_laporan, key, value)
    db.commit()
    db.refresh(db_laporan)
    return db_laporan

def delete_laporan(db: Session, id_laporan: int) -> bool:
    db_laporan = get_laporan(db, id_laporan)
    if not db_laporan:
        return False
    db.delete(db_laporan)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# PESAN
# ══════════════════════════════════════════════════════════════════════════════

def get_pesan(db: Session, id_pesan: int) -> Optional[models.Pesan]:
    return db.query(models.Pesan).filter(models.Pesan.id_pesan == id_pesan).first()

def get_all_pesan(db: Session, skip: int = 0, limit: int = 100) -> List[models.Pesan]:
    return db.query(models.Pesan).offset(skip).limit(limit).all()

def get_pesan_by_akun(db: Session, id_akun: int) -> List[models.Pesan]:
    return db.query(models.Pesan).filter(
        (models.Pesan.id_pengirim == id_akun) | (models.Pesan.id_penerima == id_akun)
    ).all()

def create_pesan(db: Session, pesan: schemas.PesanCreate) -> models.Pesan:
    db_pesan = models.Pesan(**pesan.model_dump())
    db.add(db_pesan)
    db.commit()
    db.refresh(db_pesan)
    return db_pesan

def update_pesan(db: Session, id_pesan: int, pesan: schemas.PesanUpdate) -> Optional[models.Pesan]:
    db_pesan = get_pesan(db, id_pesan)
    if not db_pesan:
        return None
    for key, value in pesan.model_dump(exclude_unset=True).items():
        setattr(db_pesan, key, value)
    db.commit()
    db.refresh(db_pesan)
    return db_pesan

def delete_pesan(db: Session, id_pesan: int) -> bool:
    db_pesan = get_pesan(db, id_pesan)
    if not db_pesan:
        return False
    db.delete(db_pesan)
    db.commit()
    return True


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFIKASI
# ══════════════════════════════════════════════════════════════════════════════

def get_notifikasi(db: Session, id_notif: int) -> Optional[models.Notifikasi]:
    return db.query(models.Notifikasi).filter(models.Notifikasi.id_notif == id_notif).first()

def get_notifikasi_by_akun(db: Session, id_akun: int) -> List[models.Notifikasi]:
    return db.query(models.Notifikasi).filter(models.Notifikasi.id_akun == id_akun).all()

def get_all_notifikasi(db: Session, skip: int = 0, limit: int = 100) -> List[models.Notifikasi]:
    return db.query(models.Notifikasi).offset(skip).limit(limit).all()

def create_notifikasi(db: Session, notif: schemas.NotifikasiCreate) -> models.Notifikasi:
    db_notif = models.Notifikasi(**notif.model_dump())
    db.add(db_notif)
    db.commit()
    db.refresh(db_notif)
    return db_notif

def update_notifikasi(db: Session, id_notif: int, notif: schemas.NotifikasiUpdate) -> Optional[models.Notifikasi]:
    db_notif = get_notifikasi(db, id_notif)
    if not db_notif:
        return None
    for key, value in notif.model_dump(exclude_unset=True).items():
        setattr(db_notif, key, value)
    db.commit()
    db.refresh(db_notif)
    return db_notif

def delete_notifikasi(db: Session, id_notif: int) -> bool:
    db_notif = get_notifikasi(db, id_notif)
    if not db_notif:
        return False
    db.delete(db_notif)
    db.commit()
    return True