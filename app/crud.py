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
    
# ──────────────────────────────────────────────────────────────────────────────
# TAMBAHKAN KE crud.py — di bagian bawah file
# ──────────────────────────────────────────────────────────────────────────────

# ─── Catatan Harian ───────────────────────────────────────────────────────────

def create_catatan_harian(
    db: Session,
    data: "schemas.CatatanHarianCreate",
    id_guru: int,
) -> "models.CatatanHarian":
    """
    Buat catatan baru.
    id_guru diambil dari akun guru yang sedang login (bukan dari request body).
    """
    catatan = models.CatatanHarian(
        id_guru  = id_guru,
        id_siswa = data.id_siswa,
        id_kelas = data.id_kelas,
        target   = data.target,
        judul    = data.judul,
        foto     = data.foto,
        isi      = data.isi,
    )
    db.add(catatan)
    db.commit()
    db.refresh(catatan)
    return catatan


def get_catatan_harian(
    db: Session,
    id_catatan: int,
) -> Optional["models.CatatanHarian"]:
    return (
        db.query(models.CatatanHarian)
        .filter(models.CatatanHarian.id_catatan == id_catatan)
        .first()
    )


def get_catatan_by_siswa(
    db: Session,
    id_siswa: int,
    id_kelas: Optional[int] = None,
    skip: int = 0,
    limit: int = 50,
) -> List["models.CatatanHarian"]:
    """
    Ambil catatan yang VISIBLE untuk seorang wali siswa.
    Logika visibilitas (OR):
      1. target = semua_kelas  → semua wali bisa lihat
      2. target = satu_kelas   → wali bisa lihat jika id_kelas cocok dengan kelas siswa
      3. target = satu_siswa   → wali bisa lihat jika id_siswa cocok
    """
    from sqlalchemy import or_, and_

    conditions = [
        # 1. Broadcast semua kelas
        models.CatatanHarian.target == models.TargetCatatanEnum.semua_kelas,
        # 3. Khusus siswa ini
        and_(
            models.CatatanHarian.target   == models.TargetCatatanEnum.satu_siswa,
            models.CatatanHarian.id_siswa == id_siswa,
        ),
    ]

    # 2. Kelas siswa — hanya tambahkan jika id_kelas diketahui
    if id_kelas is not None:
        conditions.append(
            and_(
                models.CatatanHarian.target   == models.TargetCatatanEnum.satu_kelas,
                models.CatatanHarian.id_kelas == id_kelas,
            )
        )

    return (
        db.query(models.CatatanHarian)
        .filter(or_(*conditions))
        .order_by(models.CatatanHarian.tanggal.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_catatan_by_guru(
    db: Session,
    id_guru: int,
    skip: int = 0,
    limit: int = 50,
) -> List["models.CatatanHarian"]:
    """Ambil semua catatan yang dibuat oleh guru tertentu (untuk halaman riwayat guru)."""
    return (
        db.query(models.CatatanHarian)
        .filter(models.CatatanHarian.id_guru == id_guru)
        .order_by(models.CatatanHarian.tanggal.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def update_catatan_harian(
    db: Session,
    id_catatan: int,
    data: "schemas.CatatanHarianUpdate",
) -> Optional["models.CatatanHarian"]:
    catatan = get_catatan_harian(db, id_catatan)
    if not catatan:
        return None
    for key, value in data.model_dump(exclude_unset=True).items():
        setattr(catatan, key, value)
    db.commit()
    db.refresh(catatan)
    return catatan


def delete_catatan_harian(db: Session, id_catatan: int) -> bool:
    catatan = get_catatan_harian(db, id_catatan)
    if not catatan:
        return False
    db.delete(catatan)
    db.commit()
    return True


def _build_catatan_out(catatan: "models.CatatanHarian") -> "schemas.CatatanHarianOut":
    """
    Helper: konversi ORM object → CatatanHarianOut dengan JOIN manual.
    Dipanggil dari endpoint setelah query.
    """
    nama_guru  = catatan.guru.akun.nama  if catatan.guru  and catatan.guru.akun  else None
    nama_siswa = catatan.siswa.nama_siswa if catatan.siswa else None
    nama_kelas = catatan.kelas.nama_kelas if catatan.kelas else None

    return schemas.CatatanHarianOut(
        id_catatan = catatan.id_catatan,
        id_guru    = catatan.id_guru,
        id_siswa   = catatan.id_siswa,
        id_kelas   = catatan.id_kelas,
        target     = catatan.target,
        judul      = catatan.judul,
        foto       = catatan.foto,
        isi        = catatan.isi,
        tanggal    = catatan.tanggal,
        nama_guru  = nama_guru,
        nama_siswa = nama_siswa,
        nama_kelas = nama_kelas,
    )
        
# ─── TAMBAHKAN KE crud.py (di bagian bawah file) ─────────────────────────────


# ─── Notifikasi ───────────────────────────────────────────────────────────────

def _buat_notif(
    db: "Session",
    id_akun: int,
    judul: str,
    pesan: str,
    tipe: "models.TipeNotifEnum",
    ref_id: int,
) -> "models.Notifikasi":
    """
    Helper internal: buat satu baris notifikasi.
    Dipanggil dari fungsi-fungsi kirim_notif_* di bawah.
    Tidak melakukan db.commit() — commit dilakukan oleh caller.
    """
    notif = models.Notifikasi(
        id_akun = id_akun,
        judul   = judul,
        pesan   = pesan,
        tipe    = tipe,
        ref_id  = ref_id,
    )
    db.add(notif)
    return notif


def kirim_notif_pesan(
    db: "Session",
    id_akun_penerima: int,
    nama_pengirim: str,
    id_pesan: int,
) -> "models.Notifikasi":
    """
    Buat notifikasi tipe 'pesan' untuk penerima pesan.
    Dipanggil dari endpoint POST /pesan/ setelah pesan disimpan.

    Cocok untuk GURU (notif pesan masuk dari wali)
    dan WALI (notif pesan masuk dari guru).
    """
    notif = _buat_notif(
        db       = db,
        id_akun  = id_akun_penerima,
        judul    = "Pesan Baru",
        pesan    = f"Pesan baru dari {nama_pengirim}",
        tipe     = models.TipeNotifEnum.pesan,
        ref_id   = id_pesan,
    )
    db.commit()
    db.refresh(notif)
    return notif


def kirim_notif_absensi_batch(
    db: "Session",
    id_kelas: int,
    tanggal_str: str,
    nama_guru: str,
    id_absensi_ref: int,
) -> None:
    """
    Buat notifikasi tipe 'absensi' untuk SEMUA wali siswa di kelas tersebut.
    Dipanggil dari endpoint POST /absensi/batch setelah upsert selesai.

    id_absensi_ref = id_absensi pertama dari batch (sebagai ref_id).
    Satu notif per wali, bukan per siswa — agar tidak banjir notif.
    """
    # Ambil semua siswa di kelas ini yang punya wali
    siswa_list = (
        db.query(models.Siswa)
        .filter(
            models.Siswa.id_kelas      == id_kelas,
            models.Siswa.id_wali_siswa != None,  # noqa: E711
        )
        .all()
    )

    for siswa in siswa_list:
        wali = (
            db.query(models.WaliSiswa)
            .filter(models.WaliSiswa.id_wali_siswa == siswa.id_wali_siswa)
            .first()
        )
        if not wali:
            continue

        _buat_notif(
            db      = db,
            id_akun = wali.id_akun,
            judul   = "Absensi Diperbarui",
            pesan   = (
                f"Absensi {siswa.nama_siswa} tanggal {tanggal_str} "
                f"telah diisi oleh {nama_guru}"
            ),
            tipe    = models.TipeNotifEnum.absensi,
            ref_id  = id_absensi_ref,
        )

    db.commit()


def kirim_notif_catatan(
    db: "Session",
    catatan: "models.CatatanHarian",
    nama_guru: str,
) -> None:
    """
    Buat notifikasi tipe 'catatan' untuk wali yang berhak melihat catatan.
    Dipanggil dari endpoint POST /catatan/ setelah catatan disimpan.

    Logika penerima (sama dengan visibilitas catatan):
      - semua_kelas → semua wali siswa
      - satu_kelas  → wali siswa di kelas tersebut
      - satu_siswa  → wali siswa yang bersangkutan saja
    """
    wali_id_akun_list: list[int] = []

    if catatan.target == models.TargetCatatanEnum.semua_kelas:
        # Semua wali siswa
        wali_list = db.query(models.WaliSiswa).all()
        wali_id_akun_list = [w.id_akun for w in wali_list]

    elif catatan.target == models.TargetCatatanEnum.satu_kelas:
        # Wali siswa di kelas ini
        siswa_list = (
            db.query(models.Siswa)
            .filter(
                models.Siswa.id_kelas      == catatan.id_kelas,
                models.Siswa.id_wali_siswa != None,  # noqa: E711
            )
            .all()
        )
        for siswa in siswa_list:
            wali = (
                db.query(models.WaliSiswa)
                .filter(models.WaliSiswa.id_wali_siswa == siswa.id_wali_siswa)
                .first()
            )
            if wali:
                wali_id_akun_list.append(wali.id_akun)

    elif catatan.target == models.TargetCatatanEnum.satu_siswa:
        # Wali siswa yang bersangkutan saja
        siswa = (
            db.query(models.Siswa)
            .filter(models.Siswa.id_siswa == catatan.id_siswa)
            .first()
        )
        if siswa and siswa.id_wali_siswa:
            wali = (
                db.query(models.WaliSiswa)
                .filter(models.WaliSiswa.id_wali_siswa == siswa.id_wali_siswa)
                .first()
            )
            if wali:
                wali_id_akun_list.append(wali.id_akun)

    for id_akun in wali_id_akun_list:
        _buat_notif(
            db      = db,
            id_akun = id_akun,
            judul   = "Catatan Baru",
            pesan   = f"Catatan baru dari {nama_guru}: {catatan.judul}",
            tipe    = models.TipeNotifEnum.catatan,
            ref_id  = catatan.id_catatan,
        )

    db.commit()


# ─── Query notifikasi ─────────────────────────────────────────────────────────

def get_notifikasi_by_akun(
    db: "Session",
    id_akun: int,
    skip: int = 0,
    limit: int = 50,
) -> list["models.Notifikasi"]:
    """Ambil notifikasi milik satu akun, urut terbaru dulu."""
    return (
        db.query(models.Notifikasi)
        .filter(models.Notifikasi.id_akun == id_akun)
        .order_by(models.Notifikasi.tanggal.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def count_notif_belum_dibaca(db: "Session", id_akun: int) -> int:
    """Hitung notifikasi belum dibaca milik akun."""
    return (
        db.query(models.Notifikasi)
        .filter(
            models.Notifikasi.id_akun == id_akun,
            models.Notifikasi.status  == models.StatusNotifEnum.belum_dibaca,
        )
        .count()
    )


def tandai_notif_dibaca(
    db: "Session",
    id_akun: int,
    id_notif: int | None = None,
) -> int:
    """
    Tandai notifikasi sebagai sudah_dibaca.
    - id_notif diisi  → tandai hanya notif tersebut (jika milik id_akun)
    - id_notif = None → tandai SEMUA notif belum_dibaca milik id_akun
    Mengembalikan jumlah baris yang diupdate.
    """
    q = db.query(models.Notifikasi).filter(
        models.Notifikasi.id_akun == id_akun,
        models.Notifikasi.status  == models.StatusNotifEnum.belum_dibaca,
    )
    if id_notif is not None:
        q = q.filter(models.Notifikasi.id_notif == id_notif)

    rows = q.all()
    for n in rows:
        n.status = models.StatusNotifEnum.sudah_dibaca
    db.commit()
    return len(rows)        