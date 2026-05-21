import asyncio
import json
from typing import Optional, List

from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy import extract, func
from app import models, schemas
from datetime import date
from sqlalchemy import and_, func
 
 
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
DEFAULT_PASSWORD = "tkqoulansadid"


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


# ─── Akun ─────────────────────────────────────────────────────────────────────

def get_akun(db: Session, id_akun: int) -> Optional[models.Akun]:
    return db.get(models.Akun, id_akun)

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

def update_akun(db: Session, id_akun: int, data: schemas.AkunUpdate) -> Optional[models.Akun]:
    obj = get_akun(db, id_akun)
    if not obj:
        return None
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(obj, k, hash_password(v) if k == "password" and v else v)
    return _commit_refresh(db, obj)

def delete_akun(db: Session, id_akun: int) -> bool:
    obj = get_akun(db, id_akun)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True

def force_logout_akun(db: Session, id_akun: int) -> bool:
    obj = get_akun(db, id_akun)
    if not obj or obj.device_id is None:
        return False
    obj.device_id = None
    db.commit()
    return True


# ─── Reset Password ───────────────────────────────────────────────────────────

def get_reset_password(db: Session, id_pertanyaan: int) -> Optional[models.ResetPassword]:
    return db.get(models.ResetPassword, id_pertanyaan)

def get_reset_password_by_akun(db: Session, id_akun: int) -> Optional[models.ResetPassword]:
    return db.query(models.ResetPassword).filter(
        models.ResetPassword.id_akun == id_akun).first()

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

def verify_jawaban_reset(db: Session, id_akun: int, jawaban: str) -> bool:
    obj = get_reset_password_by_akun(db, id_akun)
    return bool(obj and obj.jawaban.strip().lower() == jawaban.strip().lower())

def ganti_password(db: Session, id_akun: int, password_baru: str) -> Optional[models.Akun]:
    obj = get_akun(db, id_akun)
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

def get_guru_by_akun(db: Session, id_akun: int) -> Optional[models.Guru]:
    return db.query(models.Guru).filter(models.Guru.id_akun == id_akun).first()

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
    obj = models.Guru(id_akun=akun.id_akun,
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

def get_admin_by_akun(db: Session, id_akun: int) -> Optional[models.Admin]:
    return db.query(models.Admin).filter(models.Admin.id_akun == id_akun).first()

def get_all_admin(db: Session, skip=0, limit=100):
    return db.query(models.Admin).offset(skip).limit(limit).all()

def create_admin_with_akun(db: Session, data: schemas.AdminCreate) -> models.Admin:
    akun = models.Akun(
        username=data.username, password=hash_password(DEFAULT_PASSWORD),
        nama=data.nama, role=models.RoleEnum.admin, first_login=True,
    )
    db.add(akun)
    db.flush()
    obj = models.Admin(id_akun=akun.id_akun)
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

def get_kepsek_by_akun(db: Session, id_akun: int) -> Optional[models.KepalaSekolah]:
    return db.query(models.KepalaSekolah).filter(
        models.KepalaSekolah.id_akun == id_akun).first()

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
    obj = models.KepalaSekolah(id_akun=akun.id_akun, nip=data.nip)
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

    wali = models.WaliSiswa(id_akun=akun.id_akun,
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

def get_wali_siswa_by_akun(db: Session, id_akun: int) -> Optional[models.WaliSiswa]:
    return db.query(models.WaliSiswa).filter(models.WaliSiswa.id_akun == id_akun).first()

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

def _buat_notif(db: Session, id_akun: int, judul: str, pesan: str,
                tipe: models.TipeNotifEnum, ref_id: int) -> models.Notifikasi:
    """Buat satu baris notifikasi tanpa commit."""
    obj = models.Notifikasi(id_akun=id_akun, judul=judul, pesan=pesan,
                            tipe=tipe, ref_id=ref_id)
    db.add(obj)
    return obj

def kirim_notif_pesan(db: Session, id_akun_penerima: int, nama_pengirim: str,
                      id_pesan: int, payload_ws: dict = None) -> models.Notifikasi:
    from app.websocket_manager import ws_manager
    notif = _buat_notif(db, id_akun_penerima, "Pesan Baru",
                        f"Pesan baru dari {nama_pengirim}",
                        models.TipeNotifEnum.pesan, id_pesan)
    db.commit()
    db.refresh(notif)

    if payload_ws and ws_manager.aktif(id_akun_penerima):
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(
                loop.create_task,
                ws_manager.kirim_ke_akun(id_akun_penerima, payload_ws))
        except RuntimeError:
            pass
    return notif

def kirim_notif_absensi_batch(
    db: Session,
    id_kelas: int,
    tanggal_str: str,
    nama_guru: str,
    id_absensi_ref: int,
    hasil_absensi: list = None,   # ← tambah parameter ini
) -> None:
    from app.websocket_manager import ws_manager

    siswa_list = (db.query(models.Siswa)
                  .filter(models.Siswa.id_kelas == id_kelas,
                          models.Siswa.id_wali_siswa.isnot(None)).all())
    id_wali_set = {s.id_wali_siswa for s in siswa_list}
    if not id_wali_set:
        return

    wali_map     = {w.id_wali_siswa: w for w in
                    db.query(models.WaliSiswa)
                      .filter(models.WaliSiswa.id_wali_siswa.in_(id_wali_set)).all()}
    siswa_by_wali = {s.id_wali_siswa: s for s in siswa_list}

    # Buat map id_siswa → absensi untuk lookup status per siswa
    absensi_by_siswa = {}
    if hasil_absensi:
        for ab in hasil_absensi:
            absensi_by_siswa[ab.id_siswa] = ab

    for id_ws, wali in wali_map.items():
        siswa = siswa_by_wali.get(id_ws)
        if not siswa:
            continue

        # ── Simpan notifikasi ke database ─────────────────────────────────
        _buat_notif(db, wali.id_akun, "Absensi Diperbarui",
                    f"Absensi {siswa.nama_siswa} tanggal {tanggal_str} "
                    f"telah diisi oleh {nama_guru}",
                    models.TipeNotifEnum.absensi, id_absensi_ref)

        # ── Kirim WebSocket event ke wali ─────────────────────────────────
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
                if loop.is_running():
                    loop.call_soon_threadsafe(
                        loop.create_task,
                        ws_manager.kirim_ke_akun(wali.id_akun, payload))
            except RuntimeError:
                pass

    db.commit()  # Bug #4 fix: flush() → commit() agar notifikasi absensi tersimpan



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
    Juga kirim WebSocket event catatan_baru agar client bisa update realtime.
    """
    from app.websocket_manager import ws_manager

    target = catatan.target
    pasangan = []

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
            wali_map = {w.id_wali_siswa: w for w in
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
        wali_map = {w.id_wali_siswa: w for w in
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
        _buat_notif(
            db, wali.id_akun,
            f"Catatan: {catatan.judul}",
            f"Guru {nama_guru} membuat catatan untuk {siswa.nama_siswa}",
            models.TipeNotifEnum.catatan,
            catatan.id_catatan,
        )
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
                loop.call_soon_threadsafe(
                    loop.create_task,
                    ws_manager.kirim_ke_akun(wali.id_akun, payload))
            except RuntimeError:
                pass

    db.flush() 

def get_notifikasi_by_akun(db: Session, id_akun: int,
                           skip=0, limit=50) -> List[models.Notifikasi]:
    return (db.query(models.Notifikasi).filter(models.Notifikasi.id_akun == id_akun)
            .order_by(models.Notifikasi.tanggal.desc()).offset(skip).limit(limit).all())

def count_notif_belum_dibaca(db: Session, id_akun: int) -> int:
    return (db.query(models.Notifikasi)
            .filter(models.Notifikasi.id_akun == id_akun,
                    models.Notifikasi.status == models.StatusNotifEnum.belum_dibaca)
            .count())

def tandai_notif_dibaca(db: Session, id_akun: int,
                        id_notif: Optional[int] = None) -> int:
    q = db.query(models.Notifikasi).filter(
        models.Notifikasi.id_akun == id_akun,
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
    """
    Hitung jumlah hadir/sakit/izin/alpha satu siswa dalam satu bulan.
    Return dict siap pakai (bukan ORM object).
    """
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
    """
    Gabungkan ringkasan absensi + catatan harian untuk satu siswa.
    Return LaporanSiswaOut atau None jika siswa tidak ditemukan.
    """
    siswa = db.get(models.Siswa, id_siswa)
    if not siswa:
        return None
 
    # Ambil kelas
    nama_kelas = siswa.kelas.nama_kelas if siswa.kelas else None
 
    # Ringkasan absensi
    rekap = get_ringkasan_absensi_siswa(db, id_siswa, bulan, tahun)
 
    # Catatan harian yang relevan (satu_siswa ATAU satu_kelas ATAU semua_kelas)
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
    """
    Ringkasan absensi semua siswa di satu kelas untuk satu bulan.
    Return LaporanKelasOut atau None jika kelas tidak ditemukan.
    """
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
    """Ambil semua laporan (untuk Admin)."""
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
    """
    Buat laporan baru oleh guru.
    - id_kelas   : dari request body
    - id_guru    : dari JWT (injected di endpoint)
    - status     : default 'menunggu_verifikasi'
    - created_at : diisi otomatis oleh DB (server_default)
    """
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
    """
    Admin memverifikasi laporan.
    - status       : diperbarui ke nilai dari request ('terverifikasi')
    - keterangan   : catatan admin (boleh None)
    - tanggal_dibuat: di-update ke hari ini agar mencatat tanggal verifikasi
    """
    obj = get_laporan(db, id_laporan)
    if not obj:
        return None
    obj.status         = data.status
    obj.keterangan     = data.keterangan
    obj.tanggal_dibuat = date.today()          # update tanggal saat diverifikasi
    return _commit_refresh(db, obj)


def kirim_notif_laporan_terverifikasi(
    db: Session,
    laporan: models.Laporan,
) -> None:
    """
    Kirim notifikasi ke semua wali siswa di kelas laporan setelah admin verifikasi.
    Juga kirim WebSocket event laporan_terverifikasi untuk update realtime.
    """
    from app.websocket_manager import ws_manager

    if not laporan.id_kelas:
        return

    jenis  = laporan.jenis_laporan.value if hasattr(laporan.jenis_laporan, "value") else str(laporan.jenis_laporan or "absensi")
    periode = laporan.periode or ""
    nama_kelas = laporan.kelas.nama_kelas if laporan.kelas else f"Kelas {laporan.id_kelas}"

    # Cari semua siswa aktif di kelas laporan yang punya wali
    siswa_list = (db.query(models.Siswa)
                  .filter(models.Siswa.id_kelas == laporan.id_kelas,
                          models.Siswa.id_wali_siswa.isnot(None)).all())
    if not siswa_list:
        return

    id_wali_set = {s.id_wali_siswa for s in siswa_list}
    wali_map    = {w.id_wali_siswa: w for w in
                   db.query(models.WaliSiswa)
                     .filter(models.WaliSiswa.id_wali_siswa.in_(id_wali_set)).all()}

    for siswa in siswa_list:
        wali = wali_map.get(siswa.id_wali_siswa)
        if not wali:
            continue

        label_jenis = "Catatan Harian" if jenis == "catatan" else "Absensi"
        _buat_notif(
            db,
            wali.id_akun,
            f"Laporan {label_jenis} Tersedia",
            f"Laporan {label_jenis.lower()} {nama_kelas} periode {periode} telah diverifikasi",
            models.TipeNotifEnum.laporan,
            laporan.id_laporan,
        )

        if ws_manager.aktif(wali.id_akun):
            payload = {
                "type": "laporan_terverifikasi",
                "data": {
                    "id_laporan":  laporan.id_laporan,
                    "jenis":       jenis,
                    "periode":     periode,
                    "nama_kelas":  nama_kelas,
                    "id_kelas":    laporan.id_kelas,
                },
            }
            try:
                loop = asyncio.get_running_loop()
                if loop.is_running():
                    loop.call_soon_threadsafe(
                        loop.create_task,
                        ws_manager.kirim_ke_akun(wali.id_akun, payload))
            except RuntimeError:
                pass

    db.commit()  # Bug #1 fix: flush() → commit() agar notifikasi benar-benar tersimpan


def delete_laporan(db: Session, id_laporan: int) -> bool:
    obj = get_laporan(db, id_laporan)
    if not obj:
        return False
    db.delete(obj)
    db.commit()
    return True


def _build_laporan_out(lap: models.Laporan) -> schemas.LaporanOut:
    """
    Bangun LaporanOut dari ORM object.
    nama_kelas diambil dari relasi lap.kelas (bukan kolom langsung di tabel laporan).
    """
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
        nama_kelas     = lap.kelas.nama_kelas if lap.kelas else None,
        nama_guru      = lap.guru.akun.nama if lap.guru and lap.guru.akun else None,
    )


def _hitung_statistik_laporan(data: list) -> dict:
    """Helper: hitung total_selesai dan total_belum dari list Laporan."""
    total_selesai = sum(
        1 for l in data
        if l.status == models.StatusLaporanEnum.terverifikasi
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
    """
    Hitung hadir/sakit/izin/alpha satu siswa dalam rentang tanggal.
    Return dict langsung (bukan ORM object).
    """
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
    """
    Ambil baris absensi satu siswa dalam rentang tanggal, urut ascending.
    Dipakai untuk PDF wali siswa (tampil per hari, bukan hanya rekap).
    """
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


# ─── Catatan Harian Siswa (range tanggal, hanya target satu_siswa) ────────────
 
def get_catatan_siswa_range(
    db: Session,
    id_siswa: int,
    tanggal_awal: date,
    tanggal_akhir: date,
) -> List[models.CatatanHarian]:
    """
    Ambil catatan harian satu siswa dalam rentang tanggal.
    Mencakup:
      - target = 'satu_siswa' AND id_siswa cocok
      - target = 'satu_kelas'  AND id_kelas cocok dengan kelas siswa
    Diurutkan ascending berdasarkan tanggal.
    """
    from sqlalchemy import or_, and_

    # Ambil kelas siswa untuk filter satu_kelas
    siswa = db.get(models.Siswa, id_siswa)
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
    """
    Ambil semua siswa dalam satu kelas, diurutkan berdasarkan nama.
    """
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
    """
    Rekap absensi seluruh siswa dalam satu kelas berdasarkan rentang tanggal.
    Return LaporanAbsensiKelasOut atau None jika kelas tidak ditemukan.
    """
    kelas = db.get(models.Kelas, id_kelas)
    if not kelas:
        return None
 
    siswa_list = get_siswa_by_kelas(db, id_kelas)
 
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
                # BUG FIX #2: isi nisn langsung dari model siswa
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
    """
    Ambil catatan harian (target=satu_siswa) untuk seluruh siswa dalam satu kelas.
    Return LaporanCatatanKelasOut atau None jika kelas tidak ditemukan.
    """
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
                # BUG FIX #2: isi nisn langsung dari model siswa
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