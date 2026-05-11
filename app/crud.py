from sqlalchemy.orm import Session
from passlib.context import CryptContext
from typing import Optional, List
import json

from app import models, schemas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

DEFAULT_PASSWORD = "tkqoulansadid"  # password default untuk semua akun baru


# ─── Helper: encode / decode id_kelas (JSON string ↔ List[int]) ──────────────

def encode_id_kelas(list_id: Optional[List[int]]) -> Optional[str]:
    if not list_id:
        return None
    unique = list(dict.fromkeys(list_id))   
    return json.dumps(unique[:2])          

def decode_id_kelas(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return [int(x) for x in parsed]
        return [int(parsed)]              
    except (ValueError, TypeError):
        return []


# ─── Password ─────────────────────────────────────────────────────────────────

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def authenticate_akun(db: Session, username: str, password: str) -> Optional[models.Akun]:
    akun = get_akun_by_username(db, username)
    if not akun or not verify_password(password, akun.password):
        return None
    return akun


# ─── Akun ─────────────────────────────────────────────────────────────────────

def get_akun(db: Session, id_akun: int) -> Optional[models.Akun]:
    return db.query(models.Akun).filter(models.Akun.id_akun == id_akun).first()

def get_akun_by_username(db: Session, username: str) -> Optional[models.Akun]:
    return db.query(models.Akun).filter(models.Akun.username == username).first()

def get_all_akun(db: Session, skip: int = 0, limit: int = 100) -> List[models.Akun]:
    return db.query(models.Akun).offset(skip).limit(limit).all()

def create_akun(db: Session, akun: schemas.AkunCreate) -> models.Akun:
    db_akun = models.Akun(
        username=akun.username,
        password=hash_password(akun.password),
        nama=akun.nama,
        role=akun.role,
        first_login=True,
    )
    db.add(db_akun)
    db.commit()
    db.refresh(db_akun)
    return db_akun

def update_akun(db: Session, id_akun: int, data: schemas.AkunUpdate) -> Optional[models.Akun]:
    db_akun = get_akun(db, id_akun)
    if not db_akun:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        if key == "password" and value:
            setattr(db_akun, key, hash_password(value))
        else:
            setattr(db_akun, key, value)
    db.commit()
    db.refresh(db_akun)
    return db_akun

def update_guru(db: Session, id_guru: int, guru_data) -> Optional[models.Guru]:
    db_guru = db.query(models.Guru).filter(models.Guru.id_guru == id_guru).first()
    if not db_guru:
        return None

    if guru_data.nip is not None:
        db_guru.nip = guru_data.nip

    if guru_data.list_id_kelas is not None:
        db_guru.id_kelas = encode_id_kelas(guru_data.list_id_kelas)

    db.commit()
    db.refresh(db_guru)
    return db_guru

def delete_akun(db: Session, id_akun: int) -> bool:
    db_akun = get_akun(db, id_akun)
    if not db_akun:
        return False
    db.delete(db_akun)
    db.commit()
    return True


# ─── Reset Password ───────────────────────────────────────────────────────────

def get_reset_password(db: Session, id_pertanyaan: int) -> Optional[models.ResetPassword]:
    return db.query(models.ResetPassword).filter(
        models.ResetPassword.id_pertanyaan == id_pertanyaan).first()

def get_reset_password_by_akun(db: Session, id_akun: int) -> Optional[models.ResetPassword]:
    return db.query(models.ResetPassword).filter(
        models.ResetPassword.id_akun == id_akun).first()

def get_all_reset_password(db: Session, skip: int = 0, limit: int = 100) -> List[models.ResetPassword]:
    return db.query(models.ResetPassword).offset(skip).limit(limit).all()

def create_reset_password(db: Session, rp: schemas.ResetPasswordCreate) -> models.ResetPassword:
    db_rp = models.ResetPassword(**rp.model_dump())
    db.add(db_rp)
    db.commit()
    db.refresh(db_rp)
    return db_rp

def update_reset_password(db: Session, id_pertanyaan: int,
                        rp: schemas.ResetPasswordUpdate) -> Optional[models.ResetPassword]:
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

def verify_jawaban_reset(db: Session, id_akun: int, jawaban: str) -> bool:
    db_rp = get_reset_password_by_akun(db, id_akun)
    if not db_rp:
        return False
    return db_rp.jawaban.strip().lower() == jawaban.strip().lower()

def ganti_password(db: Session, id_akun: int, password_baru: str) -> Optional[models.Akun]:
    db_akun = get_akun(db, id_akun)
    if not db_akun:
        return None
    if verify_password(password_baru, db_akun.password):
        raise ValueError("Password baru tidak boleh sama dengan password lama")
    db_akun.password    = hash_password(password_baru)
    db_akun.first_login = False
    db.commit()
    db.refresh(db_akun)
    return db_akun


# ─── Kelas ────────────────────────────────────────────────────────────────────

def get_kelas(db: Session, id_kelas: int) -> Optional[models.Kelas]:
    return db.query(models.Kelas).filter(models.Kelas.id_kelas == id_kelas).first()

def get_all_kelas(db: Session, skip: int = 0, limit: int = 100) -> List[models.Kelas]:
    return db.query(models.Kelas).offset(skip).limit(limit).all()

def create_kelas(db: Session, kelas: schemas.KelasCreate) -> models.Kelas:
    db_kelas = models.Kelas(nama_kelas=kelas.nama_kelas)
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


# ─── Guru ─────────────────────────────────────────────────────────────────────

def get_guru(db: Session, id_guru: int) -> Optional[models.Guru]:
    return db.query(models.Guru).filter(models.Guru.id_guru == id_guru).first()

def get_guru_by_akun(db: Session, id_akun: int) -> Optional[models.Guru]:
    return db.query(models.Guru).filter(models.Guru.id_akun == id_akun).first()

def get_guru_by_nip(db: Session, nip: str) -> Optional[models.Guru]:
    return db.query(models.Guru).filter(models.Guru.nip == nip).first()

def get_all_guru(db: Session, skip: int = 0, limit: int = 100) -> List[models.Guru]:
    return db.query(models.Guru).offset(skip).limit(limit).all()

def create_guru_with_akun(db: Session, guru: schemas.GuruCreate) -> models.Guru:
    db_akun = models.Akun(
        username=guru.username,
        password=hash_password(DEFAULT_PASSWORD),
        nama=guru.nama,
        role=models.RoleEnum.guru,   
        first_login=True,
    )
    db.add(db_akun)
    db.flush()

    db_guru = models.Guru(
        id_akun=db_akun.id_akun,
        id_kelas=encode_id_kelas(guru.list_id_kelas),
        nip=guru.nip,
    )
    db.add(db_guru)
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


# ─── Admin ────────────────────────────────────────────────────────────────────

def get_admin_by_akun(db: Session, id_akun: int) -> Optional[models.Admin]:
    return db.query(models.Admin).filter(models.Admin.id_akun == id_akun).first()

def get_all_admin(db: Session, skip: int = 0, limit: int = 100) -> List[models.Admin]:
    return db.query(models.Admin).offset(skip).limit(limit).all()

def create_admin_with_akun(db: Session, data: schemas.AdminCreate) -> models.Admin:
    db_akun = models.Akun(
        username=data.username,
        password=hash_password(DEFAULT_PASSWORD),
        nama=data.nama,
        role=models.RoleEnum.admin,
        first_login=True,
    )
    db.add(db_akun)
    db.flush()

    db_admin = models.Admin(id_akun=db_akun.id_akun)
    db.add(db_admin)
    db.commit()
    db.refresh(db_admin)
    return db_admin

def delete_admin(db: Session, id_admin: int) -> bool:
    db_admin = db.query(models.Admin).filter(models.Admin.id_admin == id_admin).first()
    if not db_admin:
        return False
    db.delete(db_admin)
    db.commit()
    return True


# ─── Kepala Sekolah ───────────────────────────────────────────────────────────

def get_kepsek(db: Session, id_kepsek: int) -> Optional[models.KepalaSekolah]:
    return db.query(models.KepalaSekolah).filter(
        models.KepalaSekolah.id_kepsek == id_kepsek).first()

def get_kepsek_by_akun(db: Session, id_akun: int) -> Optional[models.KepalaSekolah]:
    return db.query(models.KepalaSekolah).filter(
        models.KepalaSekolah.id_akun == id_akun).first()

def get_kepsek_by_nip(db: Session, nip: str) -> Optional[models.KepalaSekolah]:
    return db.query(models.KepalaSekolah).filter(
        models.KepalaSekolah.nip == nip).first()

def get_all_kepsek(db: Session, skip: int = 0, limit: int = 100) -> List[models.KepalaSekolah]:
    return db.query(models.KepalaSekolah).offset(skip).limit(limit).all()

def create_kepsek_with_akun(db: Session, data: schemas.KepsekCreate) -> models.KepalaSekolah:
    db_akun = models.Akun(
        username=data.username,
        password=hash_password(DEFAULT_PASSWORD),
        nama=data.nama,
        role=models.RoleEnum.kepala_sekolah,
        first_login=True,
    )
    db.add(db_akun)
    db.flush()

    db_kepsek = models.KepalaSekolah(id_akun=db_akun.id_akun, nip=data.nip)
    db.add(db_kepsek)
    db.commit()
    db.refresh(db_kepsek)
    return db_kepsek

def update_kepsek(db: Session, id_kepsek: int,
                data: schemas.KepsekUpdate) -> Optional[models.KepalaSekolah]:
    db_kepsek = get_kepsek(db, id_kepsek)
    if not db_kepsek:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
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


# ─── Siswa ────────────────────────────────────────────────────────────────────

def get_siswa(db: Session, id_siswa: int) -> Optional[models.Siswa]:
    return db.query(models.Siswa).filter(models.Siswa.id_siswa == id_siswa).first()

def get_siswa_by_nisn(db: Session, nisn: str) -> Optional[models.Siswa]:
    return db.query(models.Siswa).filter(models.Siswa.nisn == nisn).first()

def get_all_siswa(db: Session, skip: int = 0, limit: int = 100) -> List[models.Siswa]:
    return db.query(models.Siswa).offset(skip).limit(limit).all()

def create_siswa_with_wali(db: Session, data: schemas.SiswaCreate) -> models.Siswa:
    db_akun = models.Akun(
        username=data.username_wali, password=hash_password(DEFAULT_PASSWORD),
        nama=data.nama_wali, role=models.RoleEnum.wali_siswa, first_login=True,
    )
    db.add(db_akun)
    db.flush()

    db_wali = models.WaliSiswa(
        id_akun=db_akun.id_akun, no_hp_telp=data.no_hp_telp,
        alamat=data.alamat, id_siswa=None,
    )
    db.add(db_wali)
    db.flush()

    db_siswa = models.Siswa(
        nisn=data.nisn, nama_siswa=data.nama_siswa,
        jenis_kelamin=data.jenis_kelamin, tgl_lahir=data.tgl_lahir,
        tahun_masuk=data.tahun_masuk, id_kelas=data.id_kelas,
        id_wali_siswa=db_wali.id_wali_siswa,
    )
    db.add(db_siswa)
    db.flush()

    db_wali.id_siswa = db_siswa.id_siswa
    db.commit()
    db.refresh(db_siswa)
    return db_siswa

def update_siswa(db: Session, id_siswa: int, data: schemas.SiswaUpdate) -> Optional[models.Siswa]:
    db_siswa = get_siswa(db, id_siswa)
    if not db_siswa:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(db_siswa, key, value)
    db.commit()
    db.refresh(db_siswa)
    return db_siswa

def delete_siswa(db: Session, id_siswa: int) -> bool:
    db_siswa = get_siswa(db, id_siswa)
    if not db_siswa:
        return False
    if db_siswa.id_wali_siswa:
        db_wali = db.query(models.WaliSiswa).filter(
            models.WaliSiswa.id_wali_siswa == db_siswa.id_wali_siswa).first()
        if db_wali:
            db_wali.id_siswa = None
    db.delete(db_siswa)
    db.commit()
    return True


# ─── WaliSiswa ────────────────────────────────────────────────────────────────

def get_wali_siswa(db: Session, id_wali_siswa: int) -> Optional[models.WaliSiswa]:
    return db.query(models.WaliSiswa).filter(
        models.WaliSiswa.id_wali_siswa == id_wali_siswa).first()

def update_wali_siswa(db: Session, id_wali_siswa: int,
                    data: schemas.WaliSiswaUpdate) -> Optional[models.WaliSiswa]:
    db_wali = get_wali_siswa(db, id_wali_siswa)
    if not db_wali:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(db_wali, key, value)
    db.commit()
    db.refresh(db_wali)
    return db_wali

def get_wali_siswa_by_akun(db: Session, id_akun: int) -> Optional[models.WaliSiswa]:
    return db.query(models.WaliSiswa).filter(
        models.WaliSiswa.id_akun == id_akun
    ).first()
    
    