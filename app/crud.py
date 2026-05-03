from sqlalchemy.orm import Session
from passlib.context import CryptContext
from typing import Optional, List

from app import models, schemas

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def authenticate_akun(db: Session, username: str, password: str) -> Optional[models.Akun]:
    akun = get_akun_by_username(db, username)
    if not akun:
        return None
    if not verify_password(password, akun.hashed_password):
        return None
    return akun


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
# ADMIN
# ══════════════════════════════════════════════════════════════════════════════

def get_admin(db: Session, id_admin: int) -> Optional[models.Admin]:
    return db.query(models.Admin).filter(models.Admin.id_admin == id_admin).first()

def get_admin_by_akun(db: Session, id_akun: int) -> Optional[models.Admin]:
    return db.query(models.Admin).filter(models.Admin.id_akun == id_akun).first()

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
    return db.query(models.ResetPassword).filter(
        models.ResetPassword.id_pertanyaan == id_pertanyaan
    ).first()

def get_reset_password_by_akun(db: Session, id_akun: int) -> Optional[models.ResetPassword]:
    return db.query(models.ResetPassword).filter(
        models.ResetPassword.id_akun == id_akun
    ).first()

def get_all_reset_password(db: Session, skip: int = 0, limit: int = 100) -> List[models.ResetPassword]:
    return db.query(models.ResetPassword).offset(skip).limit(limit).all()

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