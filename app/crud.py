import asyncio
import json
import logging
from typing import Optional, List

from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from app import models, schemas
from datetime import date
from sqlalchemy import and_, func


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DEFAULT_PASSWORD = "tkqoulansadid"

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _commit_refresh(db: Session, obj):
    db.commit()
    db.refresh(obj)
    return obj

def encode_id_kelas(list_id: Optional[List[int]]) -> Optional[str]:
    if not list_id:
        return None
    return json.dumps(list(dict.fromkeys(list_id))[:2])

def decode_id_kelas(raw: Optional[str]) -> List[int]:
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
        return [int(x) for x in parsed] if isinstance(parsed, list) else [int(parsed)]
    except (ValueError, TypeError):
        return []

def hash_password(password: str) -> str:
    return pwd_context.hash(password)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)

def authenticate_akun(db: Session, username: str, password: str) -> Optional[models.Akun]:
    akun = get_akun_by_username(db, username)
    if akun and verify_password(password, akun.password):
        return akun
    return None




_firebase_initialized = False

def init_firebase():
    global _firebase_initialized
    if _firebase_initialized:
        return
    try:
        import firebase_admin
        from firebase_admin import credentials
        import os, json

        # Prioritas 1: env variable (untuk Railway/production)
        service_account_json = os.getenv("FIREBASE_SERVICE_ACCOUNT")
        if service_account_json:
            cred = credentials.Certificate(json.loads(service_account_json))
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            logger.info("Firebase init dari ENV berhasil")
            return

        # Prioritas 2: file lokal (untuk dev)
        if os.path.exists("serviceAccountKey.json"):
            cred = credentials.Certificate("serviceAccountKey.json")
            firebase_admin.initialize_app(cred)
            _firebase_initialized = True
            logger.info("Firebase init dari FILE berhasil")
            return

        logger.warning("FIREBASE_SERVICE_ACCOUNT tidak ditemukan — FCM dinonaktifkan")

    except Exception as e:
        logger.warning(f"Firebase init gagal: {e} — FCM dinonaktifkan")


def kirim_fcm(fcm_token: str, tipe: str, judul: str, isi: str,
              role: str = "") -> bool:
    if not _firebase_initialized:
        return False
    try:
        from firebase_admin import messaging
        message = messaging.Message(
            data={
                "tipe" : tipe,
                "judul": judul,
                "isi"  : isi,
                "role" : role,
            },
            topic=f"user_{fcm_token}",  # fcm_token di sini = id akun (angka)
            android=messaging.AndroidConfig(
                priority="high",
                ttl=86400,
            ),
        )
        messaging.send(message)
        return True
    except Exception as e:
        logger.warning(f"FCM gagal ke topic user_{fcm_token}: {e}")
        return False


# ─── Akun ─────────────────────────────────────────────────────────────────────

def get_akun(db: Session, id: int) -> Optional[models.Akun]:
    return db.get(models.Akun, id)

def get_akun_by_username(db: Session, username: str) -> Optional[models.Akun]:
    return db.query(models.Akun).filter(models.Akun.username == username).first()

def get_all_akun(db: Session, skip=0, limit=100) -> List[models.Akun]:
    return db.query(models.Akun).offset(skip).limit(limit).all()

def create_akun(db: Session, akun: schemas.AkunCreate) -> models.Akun:
    obj = models.Akun(
        username=akun.username,
        password=hash_password(akun.password),
        nama=akun.nama,
        role=akun.role,
        first_login=True,
    )
    db.add(obj)
    return _commit_refresh(db, obj)

def update_akun(db: Session, id: int, data: schemas.AkunUpdate) -> Optional[models.Akun]:
    obj = get_akun(db, id)
    if not obj:
        return None
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, hash_password(v) if k == "password" and v else v)
    return _commit_refresh(db, obj)

def delete_akun(db: Session, id: int) -> bool:
    obj = get_akun(db, id)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True

def force_logout_akun(db: Session, id: int) -> bool:
    obj = get_akun(db, id)
    if not obj or obj.device_id is None:
        return False
    obj.device_id = None
    db.commit()
    return True


# ─── Reset Password ───────────────────────────────────────────────────────────

def get_reset_password(db: Session, id_pertanyaan: int) -> Optional[models.ResetPassword]:
    return db.get(models.ResetPassword, id_pertanyaan)

def get_reset_password_by_akun(db: Session, id: int) -> Optional[models.ResetPassword]:
    return db.query(models.ResetPassword).filter(
        models.ResetPassword.id_akun == id).first()

def get_all_reset_password(db: Session, skip=0, limit=100):
    return db.query(models.ResetPassword).offset(skip).limit(limit).all()

def create_reset_password(db: Session, rp: schemas.ResetPasswordCreate) -> models.ResetPassword:
    obj = models.ResetPassword(**rp.model_dump())
    db.add(obj)
    return _commit_refresh(db, obj)

def update_reset_password(db: Session, id_pertanyaan: int,
                          rp: schemas.ResetPasswordUpdate) -> Optional[models.ResetPassword]:
    obj = get_reset_password(db, id_pertanyaan)
    if not obj:
        return None
    for k, v in rp.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    return _commit_refresh(db, obj)

def delete_reset_password(db: Session, id_pertanyaan: int) -> bool:
    obj = get_reset_password(db, id_pertanyaan)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True

def verify_jawaban_reset(db: Session, id: int, jawaban: str) -> bool:
    obj = get_reset_password_by_akun(db, id)
    return bool(obj and obj.jawaban.strip().lower() == jawaban.strip().lower())

def ganti_password(db: Session, id: int, password_baru: str) -> Optional[models.Akun]:
    obj = get_akun(db, id)
    if not obj:
        return None
    if verify_password(password_baru, obj.password):
        raise ValueError("Password baru tidak boleh sama dengan password lama")
    obj.password = hash_password(password_baru)
    obj.first_login = False
    return _commit_refresh(db, obj)


# ─── Kelas ────────────────────────────────────────────────────────────────────

def get_kelas(db: Session, id_kelas: int) -> Optional[models.Kelas]:
    return db.get(models.Kelas, id_kelas)

def get_all_kelas(db: Session, skip=0, limit=100):
    return db.query(models.Kelas).offset(skip).limit(limit).all()

def create_kelas(db: Session, kelas: schemas.KelasCreate) -> models.Kelas:
    obj = models.Kelas(nama_kelas=kelas.nama_kelas)
    db.add(obj)
    return _commit_refresh(db, obj)

def update_kelas(db: Session, id_kelas: int, kelas: schemas.KelasUpdate) -> Optional[models.Kelas]:
    obj = get_kelas(db, id_kelas)
    if not obj:
        return None
    for k, v in kelas.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    return _commit_refresh(db, obj)

def delete_kelas(db: Session, id_kelas: int) -> bool:
    obj = get_kelas(db, id_kelas)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


# ─── Guru ─────────────────────────────────────────────────────────────────────

def get_guru(db: Session, id_guru: int) -> Optional[models.Guru]:
    return db.get(models.Guru, id_guru)

def get_guru_by_akun(db: Session, id: int) -> Optional[models.Guru]:
    return db.query(models.Guru).filter(models.Guru.id_akun == id).first()

def get_guru_by_nip(db: Session, nip: str) -> Optional[models.Guru]:
    return db.query(models.Guru).filter(models.Guru.nip == nip).first()

def get_all_guru(db: Session, skip=0, limit=100):
    return db.query(models.Guru).offset(skip).limit(limit).all()

def create_guru_with_akun(db: Session, guru: schemas.GuruCreate) -> models.Guru:
    akun = models.Akun(
        username=guru.username, password=hash_password(DEFAULT_PASSWORD),
        nama=guru.nama, role=models.RoleEnum.guru, first_login=True,
    )
    db.add(akun)
    db.flush()
    obj = models.Guru(id_akun=akun.id,
                      id_kelas=encode_id_kelas(guru.list_id_kelas), nip=guru.nip)
    db.add(obj)
    return _commit_refresh(db, obj)

def update_guru(db: Session, id_guru: int, data) -> Optional[models.Guru]:
    obj = get_guru(db, id_guru)
    if not obj:
        return None
    if data.nip is not None:
        obj.nip = data.nip
    if data.list_id_kelas is not None:
        obj.id_kelas = encode_id_kelas(data.list_id_kelas)
    return _commit_refresh(db, obj)

def delete_guru(db: Session, id_guru: int) -> bool:
    obj = get_guru(db, id_guru)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


# ─── Admin ────────────────────────────────────────────────────────────────────

def get_admin_by_akun(db: Session, id: int) -> Optional[models.Admin]:
    return db.query(models.Admin).filter(models.Admin.id_akun == id).first()

def get_all_admin(db: Session, skip=0, limit=100):
    return db.query(models.Admin).offset(skip).limit(limit).all()

def create_admin_with_akun(db: Session, data: schemas.AdminCreate) -> models.Admin:
    akun = models.Akun(
        username=data.username, password=hash_password(DEFAULT_PASSWORD),
        nama=data.nama, role=models.RoleEnum.admin, first_login=True,
    )
    db.add(akun)
    db.flush()
    obj = models.Admin(id_akun=akun.id)
    db.add(obj)
    return _commit_refresh(db, obj)

def delete_admin(db: Session, id_admin: int) -> bool:
    obj = db.get(models.Admin, id_admin)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


# ─── Kepala Sekolah ───────────────────────────────────────────────────────────

def get_kepsek(db: Session, id_kepsek: int) -> Optional[models.KepalaSekolah]:
    return db.get(models.KepalaSekolah, id_kepsek)

def get_kepsek_by_akun(db: Session, id: int) -> Optional[models.KepalaSekolah]:
    return db.query(models.KepalaSekolah).filter(
        models.KepalaSekolah.id_akun == id).first()

def get_kepsek_by_nip(db: Session, nip: str) -> Optional[models.KepalaSekolah]:
    return db.query(models.KepalaSekolah).filter(models.KepalaSekolah.nip == nip).first()

def get_all_kepsek(db: Session, skip=0, limit=100):
    return db.query(models.KepalaSekolah).offset(skip).limit(limit).all()

def create_kepsek_with_akun(db: Session, data: schemas.KepsekCreate) -> models.KepalaSekolah:
    akun = models.Akun(
        username=data.username, password=hash_password(DEFAULT_PASSWORD),
        nama=data.nama, role=models.RoleEnum.kepala_sekolah, first_login=True,
    )
    db.add(akun)
    db.flush()
    obj = models.KepalaSekolah(id_akun=akun.id, nip=data.nip)
    db.add(obj)
    return _commit_refresh(db, obj)

def update_kepsek(db: Session, id_kepsek: int, data: schemas.KepsekUpdate) -> Optional[models.KepalaSekolah]:
    obj = get_kepsek(db, id_kepsek)
    if not obj:
        return None
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    return _commit_refresh(db, obj)

def delete_kepsek(db: Session, id_kepsek: int) -> bool:
    obj = get_kepsek(db, id_kepsek)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


# ─── Siswa ────────────────────────────────────────────────────────────────────

def get_siswa(db: Session, id_siswa: int) -> Optional[models.Siswa]:
    return db.get(models.Siswa, id_siswa)

def get_siswa_by_nisn(db: Session, nisn: str) -> Optional[models.Siswa]:
    return db.query(models.Siswa).filter(models.Siswa.nisn == nisn).first()

def get_all_siswa(db: Session, skip=0, limit=100):
    return db.query(models.Siswa).offset(skip).limit(limit).all()

def create_siswa_with_wali(db: Session, data: schemas.SiswaCreate) -> models.Siswa:
    akun = models.Akun(
        username=data.username_wali, password=hash_password(DEFAULT_PASSWORD),
        nama=data.nama_wali, role=models.RoleEnum.wali_siswa, first_login=True,
    )
    db.add(akun)
    db.flush()

    wali = models.WaliSiswa(id_akun=akun.id,
                            no_hp_telp=data.no_hp_telp, alamat=data.alamat)
    db.add(wali)
    db.flush()

    siswa = models.Siswa(
        nisn=data.nisn, nama_siswa=data.nama_siswa,
        jenis_kelamin=data.jenis_kelamin, tgl_lahir=data.tgl_lahir,
        tahun_masuk=data.tahun_masuk, id_kelas=data.id_kelas,
        id_wali_siswa=wali.id_wali_siswa,
    )
    db.add(siswa)
    db.flush()

    wali.id_siswa = siswa.id_siswa
    return _commit_refresh(db, siswa)

def update_siswa(db: Session, id_siswa: int, data: schemas.SiswaUpdate) -> Optional[models.Siswa]:
    obj = get_siswa(db, id_siswa)
    if not obj:
        return None
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    return _commit_refresh(db, obj)

def delete_siswa(db: Session, id_siswa: int) -> bool:
    obj = get_siswa(db, id_siswa)
    if not obj:
        return False
    if obj.id_wali_siswa:
        wali = db.get(models.WaliSiswa, obj.id_wali_siswa)
        if wali:
            wali.id_siswa = None
    db.delete(obj)
    db.commit()
    return True


# ─── WaliSiswa ────────────────────────────────────────────────────────────────

def get_wali_siswa(db: Session, id_wali_siswa: int) -> Optional[models.WaliSiswa]:
    return db.get(models.WaliSiswa, id_wali_siswa)

def get_wali_siswa_by_akun(db: Session, id: int) -> Optional[models.WaliSiswa]:
    return db.query(models.WaliSiswa).filter(models.WaliSiswa.id_akun == id).first()

def update_wali_siswa(db: Session, id_wali_siswa: int,
                      data: schemas.WaliSiswaUpdate) -> Optional[models.WaliSiswa]:
    obj = get_wali_siswa(db, id_wali_siswa)
    if not obj:
        return None
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    return _commit_refresh(db, obj)


# ─── Catatan Harian ───────────────────────────────────────────────────────────

def create_catatan_harian(db: Session, data: schemas.CatatanHarianCreate,
                          id_guru: int) -> models.CatatanHarian:
    obj = models.CatatanHarian(
        id_guru=id_guru, id_siswa=data.id_siswa, id_kelas=data.id_kelas,
        target=data.target, judul=data.judul, foto=data.foto, isi=data.isi,
    )
    db.add(obj)
    return _commit_refresh(db, obj)

def get_catatan_harian(db: Session, id_catatan: int) -> Optional[models.CatatanHarian]:
    return db.get(models.CatatanHarian, id_catatan)

def get_catatan_by_siswa(db: Session, id_siswa: int,
                         id_kelas: Optional[int] = None,
                         skip=0, limit=50) -> List[models.CatatanHarian]:
    from sqlalchemy import or_, and_
    conds = [
        models.CatatanHarian.target == models.TargetCatatanEnum.semua_kelas,
        and_(models.CatatanHarian.target == models.TargetCatatanEnum.satu_siswa,
             models.CatatanHarian.id_siswa == id_siswa),
    ]
    if id_kelas is not None:
        conds.append(and_(models.CatatanHarian.target == models.TargetCatatanEnum.satu_kelas,
                          models.CatatanHarian.id_kelas == id_kelas))
    return (db.query(models.CatatanHarian).filter(or_(*conds))
            .order_by(models.CatatanHarian.tanggal.desc()).offset(skip).limit(limit).all())

def get_catatan_by_guru(db: Session, id_guru: int, skip=0, limit=50) -> List[models.CatatanHarian]:
    return (db.query(models.CatatanHarian).filter(models.CatatanHarian.id_guru == id_guru)
            .order_by(models.CatatanHarian.tanggal.desc()).offset(skip).limit(limit).all())

def update_catatan_harian(db: Session, id_catatan: int,
                          data: schemas.CatatanHarianUpdate) -> Optional[models.CatatanHarian]:
    obj = get_catatan_harian(db, id_catatan)
    if not obj:
        return None
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, v)
    return _commit_refresh(db, obj)

def delete_catatan_harian(db: Session, id_catatan: int) -> bool:
    obj = get_catatan_harian(db, id_catatan)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True

def _build_catatan_out(catatan: models.CatatanHarian) -> schemas.CatatanHarianOut:
    return schemas.CatatanHarianOut(
        id_catatan=catatan.id_catatan, id_guru=catatan.id_guru,
        id_siswa=catatan.id_siswa, id_kelas=catatan.id_kelas,
        target=catatan.target, judul=catatan.judul, foto=catatan.foto,
        isi=catatan.isi, tanggal=catatan.tanggal,
        nama_guru=catatan.guru.akun.nama if catatan.guru and catatan.guru.akun else None,
        nama_siswa=catatan.siswa.nama_siswa if catatan.siswa else None,
        nama_kelas=catatan.kelas.nama_kelas if catatan.kelas else None,
    )


# ─── Absensi ──────────────────────────────────────────────────────────────────

def get_absensi(db: Session, id_absensi: int) -> Optional[models.Absensi]:
    return db.get(models.Absensi, id_absensi)

def get_absensi_by_siswa_tanggal(db: Session, id_siswa: int,
                                  tanggal) -> Optional[models.Absensi]:
    return db.query(models.Absensi).filter(
        models.Absensi.id_siswa == id_siswa,
        models.Absensi.tanggal == tanggal,
    ).first()

def get_absensi_by_kelas_tanggal(db: Session, id_kelas: int,
                                  tanggal) -> list:
    siswa_ids = [s.id_siswa for s in db.query(models.Siswa)
                 .filter(models.Siswa.id_kelas == id_kelas).all()]
    if not siswa_ids:
        return []
    return db.query(models.Absensi).filter(
        models.Absensi.id_siswa.in_(siswa_ids),
        models.Absensi.tanggal == tanggal,
    ).all()

def delete_absensi(db: Session, id_absensi: int) -> bool:
    obj = get_absensi(db, id_absensi)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


# ─── Notifikasi ───────────────────────────────────────────────────────────────

def _buat_notif(db: Session, id: int, judul: str, pesan: str,
                tipe: models.TipeNotifEnum, ref_id: int) -> models.Notifikasi:
    """Buat satu baris notifikasi tanpa commit."""
    obj = models.Notifikasi(id_akun=id, judul=judul, pesan=pesan,
                            tipe=tipe, ref_id=ref_id)
    db.add(obj)
    return obj


# ─── Titik 1: Notif Pesan ─────────────────────────────────────────────────────

def kirim_notif_pesan(
    db: Session,
    id_akun_penerima: int,
    nama_pengirim: str,
    id_pengirim: int,
    id_pesan: int,
    payload_ws: dict = None,
) -> models.Notifikasi:
    from app.websocket_manager import ws_manager

    notif = _buat_notif(
        db,
        id_akun_penerima,
        f"Pesan dari {nama_pengirim}",
        f"Pesan baru dari {nama_pengirim}",
        models.TipeNotifEnum.pesan,
        id_pengirim,
    )
    db.commit()
    db.refresh(notif)

    # ── WebSocket (app online) ────────────────────────────────────────────────
    if payload_ws and ws_manager.aktif(id_akun_penerima):
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(ws_manager.kirim_ke_akun(id_akun_penerima, payload_ws))
        except RuntimeError:
            pass

    # ── FCM (app offline) ─────────────────────────────────────────────────────
    akun_penerima = get_akun(db, id_akun_penerima)
    if akun_penerima and akun_penerima.device_id:
        isi_pesan = payload_ws.get("isi_pesan", "") if payload_ws else ""
        role_penerima = akun_penerima.role.value if akun_penerima.role else ""
        kirim_fcm(
            fcm_token = akun_penerima.device_id,
            tipe      = "pesan",
            judul     = f"Pesan dari {nama_pengirim}",
            isi       = isi_pesan,
            role      = role_penerima,
        )

    return notif


# ─── Titik 2: Notif Absensi Batch ────────────────────────────────────────────

def kirim_notif_absensi_batch(
    db: Session,
    id_kelas: int,
    tanggal_str: str,
    nama_guru: str,
    id_absensi_ref: int,
    hasil_absensi: list = None,
) -> None:
    from app.websocket_manager import ws_manager

    siswa_list = (db.query(models.Siswa)
                  .filter(models.Siswa.id_kelas == id_kelas,
                          models.Siswa.id_wali_siswa.isnot(None)).all())
    id_wali_set = {s.id_wali_siswa for s in siswa_list}
    if not id_wali_set:
        return

    wali_map      = {w.id_wali_siswa: w for w in
                     db.query(models.WaliSiswa)
                       .filter(models.WaliSiswa.id_wali_siswa.in_(id_wali_set)).all()}
    siswa_by_wali = {s.id_wali_siswa: s for s in siswa_list}

    absensi_by_siswa = {}
    if hasil_absensi:
        for ab in hasil_absensi:
            absensi_by_siswa[ab.id_siswa] = ab

    for id_ws, wali in wali_map.items():
        siswa = siswa_by_wali.get(id_ws)
        if not siswa:
            continue

        # ── DB notif ──────────────────────────────────────────────────────────
        _buat_notif(db, wali.id_akun, "Absensi Diperbarui",
                    f"Absensi {siswa.nama_siswa} tanggal {tanggal_str} "
                    f"telah diperbarui.",
                    models.TipeNotifEnum.absensi, id_absensi_ref)

        # ── WebSocket (app online) ────────────────────────────────────────────
        ab = absensi_by_siswa.get(siswa.id_siswa)
        if ab and ws_manager.aktif(wali.id_akun):
            payload = {
                "type": "absensi_update",
                "data": {
                    "tanggal":    tanggal_str,
                    "id_siswa":   siswa.id_siswa,
                    "status":     ab.status.value,
                    "keterangan": ab.keterangan or "",
                    "nama_guru":  nama_guru,
                }
            }
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(ws_manager.kirim_ke_akun(wali.id_akun, payload))
            except RuntimeError:
                pass

        # ── FCM (app offline) ─────────────────────────────────────────────────
        akun_wali = get_akun(db, wali.id_akun)
        if akun_wali and akun_wali.device_id:
            kirim_fcm(
                fcm_token = akun_wali.device_id,
                tipe      = "absensi",
                judul     = "Absensi Diperbarui",
                isi       = (f"Absensi {siswa.nama_siswa} tanggal {tanggal_str} "
                             f"telah diperbarui"),
                role      = "wali_siswa",
            )

    db.commit()


# ─── Titik 3: Notif Catatan ───────────────────────────────────────────────────

def kirim_notif_catatan(
    db: Session,
    catatan: models.CatatanHarian,
    nama_guru: str,
) -> None:
    """
    Kirim notifikasi catatan ke wali yang relevan berdasarkan target catatan.
    - semua_kelas : semua wali siswa aktif
    - satu_kelas  : semua wali siswa di kelas tersebut
    - satu_siswa  : satu wali dari siswa tersebut
    """
    from app.websocket_manager import ws_manager

    target   = catatan.target
    pasangan = []  # list of (wali, siswa)

    if target == models.TargetCatatanEnum.satu_siswa:
        if catatan.id_siswa:
            siswa = db.get(models.Siswa, catatan.id_siswa)
            if siswa and siswa.id_wali_siswa:
                wali = db.get(models.WaliSiswa, siswa.id_wali_siswa)
                if wali:
                    pasangan.append((wali, siswa))

    elif target == models.TargetCatatanEnum.satu_kelas:
        if catatan.id_kelas:
            siswa_list = (db.query(models.Siswa)
                          .filter(models.Siswa.id_kelas == catatan.id_kelas,
                                  models.Siswa.id_wali_siswa.isnot(None)).all())
            id_wali_set = {s.id_wali_siswa for s in siswa_list}
            wali_map    = {w.id_wali_siswa: w for w in
                           db.query(models.WaliSiswa)
                             .filter(models.WaliSiswa.id_wali_siswa.in_(id_wali_set)).all()}
            siswa_by_wali = {s.id_wali_siswa: s for s in siswa_list}
            for id_ws, wali in wali_map.items():
                siswa = siswa_by_wali.get(id_ws)
                if siswa:
                    pasangan.append((wali, siswa))

    else:  # semua_kelas
        siswa_list = (db.query(models.Siswa)
                      .filter(models.Siswa.id_wali_siswa.isnot(None)).all())
        id_wali_set = {s.id_wali_siswa for s in siswa_list}
        wali_map    = {w.id_wali_siswa: w for w in
                       db.query(models.WaliSiswa)
                         .filter(models.WaliSiswa.id_wali_siswa.in_(id_wali_set)).all()}
        siswa_by_wali = {s.id_wali_siswa: s for s in siswa_list}
        for id_ws, wali in wali_map.items():
            siswa = siswa_by_wali.get(id_ws)
            if siswa:
                pasangan.append((wali, siswa))

    if not pasangan:
        return

    for wali, siswa in pasangan:
        judul_notif = f"Catatan: {catatan.judul}"
        isi_notif   = f"Guru {nama_guru} membuat catatan untuk {siswa.nama_siswa}"

        # ── DB notif ──────────────────────────────────────────────────────────
        _buat_notif(
            db, wali.id_akun,
            judul_notif,
            isi_notif,
            models.TipeNotifEnum.catatan,
            catatan.id_catatan,
        )

        # ── WebSocket (app online) ────────────────────────────────────────────
        if ws_manager.aktif(wali.id_akun):
            payload = {
                "type": "catatan_baru",
                "data": {
                    "id_catatan": catatan.id_catatan,
                    "judul":      catatan.judul,
                    "nama_guru":  nama_guru,
                    "id_siswa":   siswa.id_siswa,
                    "tanggal":    str(catatan.tanggal),
                },
            }
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(ws_manager.kirim_ke_akun(wali.id_akun, payload))
            except RuntimeError:
                pass

        # ── FCM (app offline) ─────────────────────────────────────────────────
        akun_wali = get_akun(db, wali.id_akun)
        if akun_wali and akun_wali.device_id:
            kirim_fcm(
                fcm_token = akun_wali.device_id,
                tipe      = "catatan",
                judul     = judul_notif,
                isi       = isi_notif,
                role      = "wali_siswa",
            )

    db.commit()


# ─── Titik 4: Notif Laporan Terverifikasi ─────────────────────────────────────

def kirim_notif_laporan_terverifikasi(
    db: "Session",
    laporan: "models.Laporan",
    nama_admin: str,
) -> None:
    from app.websocket_manager import ws_manager
    from app import models

    if laporan.id_kelas is None:
        return

    # Kirim HANYA jika kedua jenis laporan (absensi + catatan) sudah verif
    semua_periode = (
        db.query(models.Laporan)
        .filter(
            models.Laporan.id_kelas == laporan.id_kelas,
            models.Laporan.periode  == laporan.periode,
            models.Laporan.status   == models.StatusLaporanEnum.verifikasi,
        )
        .all()
    )
    jenis_terverif = {l.jenis_laporan.value for l in semua_periode}
    if "absensi" not in jenis_terverif or "catatan" not in jenis_terverif:
        return

    try:
        nama_guru = laporan.guru.akun.nama if laporan.guru and laporan.guru.akun else "Guru"
    except Exception:
        nama_guru = "Guru"

    siswa_list = (
        db.query(models.Siswa)
        .filter(
            models.Siswa.id_kelas == laporan.id_kelas,
            models.Siswa.id_wali_siswa.isnot(None),
        )
        .all()
    )
    if not siswa_list:
        return

    id_wali_set = {s.id_wali_siswa for s in siswa_list}
    wali_map    = {
        w.id_wali_siswa: w
        for w in db.query(models.WaliSiswa)
        .filter(models.WaliSiswa.id_wali_siswa.in_(id_wali_set))
        .all()
    }

    from datetime import datetime, timezone, timedelta
    now_wib     = datetime.now(timezone(timedelta(hours=7)))
    tanggal_str = now_wib.strftime("%Y-%m-%dT%H:%M:%S")

    ws_payload = {
        "type": "laporan_verified",
        "data": {
            "id_laporan"   : laporan.id_laporan,
            "jenis_laporan": laporan.jenis_laporan.value,
            "periode"      : laporan.periode,
            "nama_guru"    : nama_guru,
            "nama_admin"   : nama_admin,
            "keterangan"   : laporan.keterangan,
            "tanggal"      : tanggal_str,
        }
    }

    judul_notif = f"Laporan {laporan.periode} Tersedia"
    isi_notif   = f"Laporan absensi & catatan bulan {laporan.periode} telah dibuat"

    for id_ws, wali in wali_map.items():
        # ── DB notif ──────────────────────────────────────────────────────────
        _buat_notif(
            db,
            wali.id_akun,
            judul_notif,
            isi_notif,
            models.TipeNotifEnum.laporan,
            laporan.id_laporan,
        )

        # ── WebSocket (app online) ────────────────────────────────────────────
        if ws_manager.aktif(wali.id_akun):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(ws_manager.kirim_ke_akun(wali.id_akun, ws_payload))
            except RuntimeError:
                pass

        # ── FCM (app offline) ─────────────────────────────────────────────────
        akun_wali = get_akun(db, wali.id_akun)
        if akun_wali and akun_wali.device_id:
            kirim_fcm(
                fcm_token = akun_wali.device_id,
                tipe      = "laporan",
                judul     = judul_notif,
                isi       = isi_notif,
                role      = "wali_siswa",
            )

    db.commit()


# ─── Notifikasi DB helpers ────────────────────────────────────────────────────

def get_notifikasi_by_akun(db: Session, id: int,
                           skip=0, limit=50) -> List[models.Notifikasi]:
    return (db.query(models.Notifikasi).filter(models.Notifikasi.id_akun == id)
            .order_by(models.Notifikasi.tanggal.desc()).offset(skip).limit(limit).all())

def count_notif_belum_dibaca(db: Session, id: int) -> int:
    return (db.query(models.Notifikasi)
            .filter(models.Notifikasi.id_akun == id,
                    models.Notifikasi.status == models.StatusNotifEnum.belum_dibaca)
            .count())

def tandai_notif_dibaca(db: Session, id: int,
                        id_notif: Optional[int] = None) -> int:
    q = db.query(models.Notifikasi).filter(
        models.Notifikasi.id_akun == id,
        models.Notifikasi.status == models.StatusNotifEnum.belum_dibaca,
    )
    if id_notif is not None:
        q = q.filter(models.Notifikasi.id_notif == id_notif)
    rows = q.all()
    for n in rows:
        n.status = models.StatusNotifEnum.sudah_dibaca
    db.commit()
    return len(rows)


# ─── Laporan Otomatis ─────────────────────────────────────────────────────────

def get_ringkasan_absensi_siswa(
    db: Session,
    id_siswa: int,
    bulan: int,
    tahun: int,
) -> dict:
    rows = (
        db.query(models.Absensi.status, func.count(models.Absensi.id_absensi))
        .filter(
            models.Absensi.id_siswa == id_siswa,
            extract("month", models.Absensi.tanggal) == bulan,
            extract("year",  models.Absensi.tanggal) == tahun,
        )
        .group_by(models.Absensi.status)
        .all()
    )
    result = {"hadir": 0, "sakit": 0, "izin": 0, "alpha": 0}
    for status, jumlah in rows:
        result[status.value] = jumlah
    result["total_hari"] = sum(result.values())
    return result


def get_laporan_otomatis_siswa(
    db: Session,
    id_siswa: int,
    bulan: int,
    tahun: int,
    limit_catatan: int = 20,
) -> Optional[schemas.LaporanSiswaOut]:
    siswa = db.get(models.Siswa, id_siswa)
    if not siswa:
        return None

    nama_kelas = siswa.kelas.nama_kelas if siswa.kelas else None
    rekap      = get_ringkasan_absensi_siswa(db, id_siswa, bulan, tahun)

    from sqlalchemy import or_, and_
    conds = [
        models.CatatanHarian.target == models.TargetCatatanEnum.semua_kelas,
        and_(
            models.CatatanHarian.target == models.TargetCatatanEnum.satu_siswa,
            models.CatatanHarian.id_siswa == id_siswa,
        ),
    ]
    if siswa.id_kelas:
        conds.append(
            and_(
                models.CatatanHarian.target == models.TargetCatatanEnum.satu_kelas,
                models.CatatanHarian.id_kelas == siswa.id_kelas,
            )
        )

    catatan_list = (
        db.query(models.CatatanHarian)
        .filter(
            or_(*conds),
            extract("month", models.CatatanHarian.tanggal) == bulan,
            extract("year",  models.CatatanHarian.tanggal) == tahun,
        )
        .order_by(models.CatatanHarian.tanggal.desc())
        .limit(limit_catatan)
        .all()
    )

    total_catatan = (
        db.query(func.count(models.CatatanHarian.id_catatan))
        .filter(
            or_(*conds),
            extract("month", models.CatatanHarian.tanggal) == bulan,
            extract("year",  models.CatatanHarian.tanggal) == tahun,
        )
        .scalar()
    )

    catatan_out = [_build_catatan_out(c) for c in catatan_list]

    return schemas.LaporanSiswaOut(
        id_siswa=siswa.id_siswa,
        nama_siswa=siswa.nama_siswa,
        nama_kelas=nama_kelas,
        bulan=bulan,
        tahun=tahun,
        **rekap,
        catatan=catatan_out,
        total_catatan=total_catatan or 0,
    )


def get_laporan_otomatis_kelas(
    db: Session,
    id_kelas: int,
    bulan: int,
    tahun: int,
) -> Optional[schemas.LaporanKelasOut]:
    kelas = db.get(models.Kelas, id_kelas)
    if not kelas:
        return None

    siswa_list = (
        db.query(models.Siswa)
        .filter(models.Siswa.id_kelas == id_kelas)
        .order_by(models.Siswa.nama_siswa)
        .all()
    )

    detail_siswa = []
    total_hadir = total_sakit = total_izin = total_alpha = 0

    for siswa in siswa_list:
        rekap = get_ringkasan_absensi_siswa(db, siswa.id_siswa, bulan, tahun)
        total_hadir += rekap["hadir"]
        total_sakit += rekap["sakit"]
        total_izin  += rekap["izin"]
        total_alpha += rekap["alpha"]

        detail_siswa.append(
            schemas.RingkasanAbsensiSiswaOut(
                id_siswa=siswa.id_siswa,
                nama_siswa=siswa.nama_siswa,
                **rekap,
            )
        )

    return schemas.LaporanKelasOut(
        id_kelas=id_kelas,
        nama_kelas=kelas.nama_kelas,
        bulan=bulan,
        tahun=tahun,
        total_siswa=len(siswa_list),
        total_hadir=total_hadir,
        total_sakit=total_sakit,
        total_izin=total_izin,
        total_alpha=total_alpha,
        siswa=detail_siswa,
    )


# ─── Laporan Manual Guru ──────────────────────────────────────────────────────

def get_laporan(db: Session, id_laporan: int) -> Optional[models.Laporan]:
    return db.get(models.Laporan, id_laporan)


def get_laporan_by_guru(
    db: Session,
    id_guru: int,
    skip: int = 0,
    limit: int = 50,
) -> List[models.Laporan]:
    return (
        db.query(models.Laporan)
        .filter(models.Laporan.id_guru == id_guru)
        .order_by(models.Laporan.tanggal_dibuat.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_all_laporan(
    db: Session,
    skip: int = 0,
    limit: int = 100,
) -> List[models.Laporan]:
    return (
        db.query(models.Laporan)
        .order_by(models.Laporan.tanggal_dibuat.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )


def create_laporan(
    db: Session,
    data: schemas.LaporanCreate,
    id_guru: int,
) -> models.Laporan:
    obj = models.Laporan(
        id_kelas       = data.id_kelas,
        id_guru        = id_guru,
        periode        = data.periode,
        tanggal_dibuat = data.tanggal_dibuat,
        jenis_laporan  = data.jenis_laporan,
        keterangan     = data.keterangan,
        status         = models.StatusLaporanEnum.menunggu_verifikasi,
    )
    db.add(obj)
    return _commit_refresh(db, obj)


def verifikasi_laporan(
    db: Session,
    id_laporan: int,
    data: schemas.LaporanVerifikasi,
) -> Optional[models.Laporan]:
    from sqlalchemy.orm import joinedload

    obj = db.query(models.Laporan).filter(
        models.Laporan.id_laporan == id_laporan
    ).first()

    if not obj:
        return None
    obj.status     = data.status
    obj.keterangan = data.keterangan if data.keterangan else None
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise e

    return db.query(models.Laporan).options(
        joinedload(models.Laporan.kelas),
        joinedload(models.Laporan.guru).joinedload(models.Guru.akun),
    ).filter(models.Laporan.id_laporan == id_laporan).first()


def delete_laporan(db: Session, id_laporan: int) -> bool:
    obj = get_laporan(db, id_laporan)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


def _build_laporan_out(lap: models.Laporan) -> schemas.LaporanOut:
    try:
        nama_guru = lap.guru.akun.nama if lap.guru and lap.guru.akun else None
    except Exception:
        nama_guru = None
    try:
        nama_kelas = lap.kelas.nama_kelas if lap.kelas else None
    except Exception:
        nama_kelas = None

    return schemas.LaporanOut(
        id_laporan     = lap.id_laporan,
        id_kelas       = lap.id_kelas,
        id_guru        = lap.id_guru,
        periode        = lap.periode,
        tanggal_dibuat = lap.tanggal_dibuat,
        jenis_laporan  = lap.jenis_laporan,
        status         = lap.status,
        keterangan     = lap.keterangan,
        created_at     = lap.created_at,
        nama_kelas     = nama_kelas,
        nama_guru      = nama_guru,
    )


def _hitung_statistik_laporan(data: list) -> dict:
    total_selesai = sum(
        1 for l in data
        if l.status == models.StatusLaporanEnum.verifikasi
    )
    return {
        "total":         len(data),
        "total_selesai": total_selesai,
        "total_belum":   len(data) - total_selesai,
    }


# ─── Rekap Absensi Siswa (range tanggal) ──────────────────────────────────────

def get_rekap_absensi_siswa_range(
    db: Session,
    id_siswa: int,
    tanggal_awal: date,
    tanggal_akhir: date,
) -> dict:
    rows = (
        db.query(models.Absensi.status, func.count(models.Absensi.id_absensi))
        .filter(
            models.Absensi.id_siswa == id_siswa,
            models.Absensi.tanggal >= tanggal_awal,
            models.Absensi.tanggal <= tanggal_akhir,
        )
        .group_by(models.Absensi.status)
        .all()
    )
    result = {"hadir": 0, "sakit": 0, "izin": 0, "alpha": 0}
    for status_val, jumlah in rows:
        result[status_val.value] = jumlah
    result["total_hari"] = sum(result.values())
    return result


# ─── Detail Absensi Harian Siswa (range tanggal) ─────────────────────────────

def get_detail_absensi_siswa_range(
    db: Session,
    id_siswa: int,
    tanggal_awal: date,
    tanggal_akhir: date,
) -> List[models.Absensi]:
    return (
        db.query(models.Absensi)
        .filter(
            models.Absensi.id_siswa == id_siswa,
            models.Absensi.tanggal  >= tanggal_awal,
            models.Absensi.tanggal  <= tanggal_akhir,
        )
        .order_by(models.Absensi.tanggal.asc())
        .all()
    )


# ─── Catatan Harian Siswa (range tanggal) ─────────────────────────────────────

def get_catatan_siswa_range(
    db: Session,
    id_siswa: int,
    tanggal_awal: date,
    tanggal_akhir: date,
) -> List[models.CatatanHarian]:
    from sqlalchemy import or_, and_

    siswa    = db.get(models.Siswa, id_siswa)
    id_kelas = siswa.id_kelas if siswa else None

    conds = [
        and_(
            models.CatatanHarian.target == models.TargetCatatanEnum.satu_siswa,
            models.CatatanHarian.id_siswa == id_siswa,
        ),
    ]
    if id_kelas is not None:
        conds.append(
            and_(
                models.CatatanHarian.target == models.TargetCatatanEnum.satu_kelas,
                models.CatatanHarian.id_kelas == id_kelas,
            )
        )

    return (
        db.query(models.CatatanHarian)
        .filter(
            or_(*conds),
            models.CatatanHarian.tanggal >= tanggal_awal,
            models.CatatanHarian.tanggal <= tanggal_akhir,
        )
        .order_by(models.CatatanHarian.tanggal.asc())
        .all()
    )


# ─── Daftar Siswa dalam Kelas ──────────────────────────────────────────────────

def get_siswa_by_kelas(
    db: Session,
    id_kelas: int,
) -> List[models.Siswa]:
    return (
        db.query(models.Siswa)
        .filter(models.Siswa.id_kelas == id_kelas)
        .order_by(models.Siswa.nama_siswa)
        .all()
    )


# ─── Laporan Absensi Kelas (range tanggal) ────────────────────────────────────

def get_laporan_absensi_kelas_range(
    db: Session,
    id_kelas: int,
    tanggal_awal: date,
    tanggal_akhir: date,
) -> Optional[schemas.LaporanAbsensiKelasOut]:
    kelas = db.get(models.Kelas, id_kelas)
    if not kelas:
        return None

    siswa_list  = get_siswa_by_kelas(db, id_kelas)
    detail_siswa = []
    total_hadir = total_sakit = total_izin = total_alpha = 0

    for siswa in siswa_list:
        rekap = get_rekap_absensi_siswa_range(
            db, siswa.id_siswa, tanggal_awal, tanggal_akhir
        )
        total_hadir += rekap["hadir"]
        total_sakit += rekap["sakit"]
        total_izin  += rekap["izin"]
        total_alpha += rekap["alpha"]

        detail_siswa.append(
            schemas.RingkasanAbsensiSiswaRangeOut(
                id_siswa   = siswa.id_siswa,
                nama_siswa = siswa.nama_siswa,
                nisn       = siswa.nisn or "",
                hadir      = rekap["hadir"],
                sakit      = rekap["sakit"],
                izin       = rekap["izin"],
                alpha      = rekap["alpha"],
                total_hari = rekap["total_hari"],
            )
        )

    return schemas.LaporanAbsensiKelasOut(
        id_kelas      = id_kelas,
        nama_kelas    = kelas.nama_kelas,
        tanggal_awal  = tanggal_awal,
        tanggal_akhir = tanggal_akhir,
        total_siswa   = len(siswa_list),
        total_hadir   = total_hadir,
        total_sakit   = total_sakit,
        total_izin    = total_izin,
        total_alpha   = total_alpha,
        siswa         = detail_siswa,
    )


# ─── Laporan Catatan Kelas (range tanggal, per siswa) ─────────────────────────

def get_laporan_catatan_kelas_range(
    db: Session,
    id_kelas: int,
    tanggal_awal: date,
    tanggal_akhir: date,
) -> Optional[schemas.LaporanCatatanKelasOut]:
    kelas = db.get(models.Kelas, id_kelas)
    if not kelas:
        return None

    siswa_list = get_siswa_by_kelas(db, id_kelas)
    data_siswa = []

    for siswa in siswa_list:
        catatan_list = get_catatan_siswa_range(
            db, siswa.id_siswa, tanggal_awal, tanggal_akhir
        )
        catatan_out = [
            schemas.CatatanRangeOut(
                id_catatan = c.id_catatan,
                tanggal    = c.tanggal.date() if hasattr(c.tanggal, 'date') else c.tanggal,
                judul      = c.judul,
                isi        = c.isi,
            )
            for c in catatan_list
        ]
        data_siswa.append(
            schemas.LaporanCatatanSiswaOut(
                id_siswa       = siswa.id_siswa,
                nama_siswa     = siswa.nama_siswa,
                nisn           = siswa.nisn or "",
                jumlah_catatan = len(catatan_out),
                catatan        = catatan_out,
            )
        )

    return schemas.LaporanCatatanKelasOut(
        id_kelas      = id_kelas,
        nama_kelas    = kelas.nama_kelas,
        tanggal_awal  = tanggal_awal,
        tanggal_akhir = tanggal_akhir,
        total_siswa   = len(siswa_list),
        siswa         = data_siswa,
    )