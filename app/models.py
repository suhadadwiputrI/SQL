from sqlalchemy import (
    Boolean, Column, ForeignKey, Integer, String,
    Enum, TIMESTAMP, Date, DateTime, Text
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.mysql import INTEGER
import enum

from app.database import Base


class RoleEnum(str, enum.Enum):
    admin          = "admin"
    guru           = "guru"
    wali_siswa     = "wali_siswa"
    kepala_sekolah = "kepala_sekolah"


class JenisKelaminEnum(str, enum.Enum):
    laki_laki = "laki_laki"
    perempuan = "perempuan"


class StatusPesanEnum(str, enum.Enum):
    terkirim = "terkirim"
    diterima = "diterima"
    dibaca   = "dibaca"


# ─── Akun ─────────────────────────────────────────────────────────────────────

class Akun(Base):
    __tablename__ = "akun"

    id_akun     = Column(INTEGER(13), primary_key=True, index=True, autoincrement=True)
    username    = Column(String(100), unique=True, index=True, nullable=False)
    password    = Column(String(255), nullable=False)
    nama        = Column(String(100), nullable=False)
    role        = Column(Enum(RoleEnum), default=RoleEnum.admin, nullable=False)
    first_login = Column(Boolean, default=True, nullable=False)
    device_id   = Column(String(64), nullable=True)
    created_at  = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at  = Column(TIMESTAMP, onupdate=func.now(), nullable=True)

    reset_password = relationship("ResetPassword", back_populates="akun", cascade="all, delete-orphan")
    guru           = relationship("Guru",          back_populates="akun", uselist=False, cascade="all, delete-orphan")
    admin          = relationship("Admin",         back_populates="akun", uselist=False, cascade="all, delete-orphan")
    kepala_sekolah = relationship("KepalaSekolah", back_populates="akun", uselist=False, cascade="all, delete-orphan")
    wali_siswa     = relationship("WaliSiswa",     back_populates="akun", uselist=False, cascade="all, delete-orphan")

    pesan_terkirim = relationship("Pesan", foreign_keys="[Pesan.id_pengirim]",
                                  back_populates="pengirim", cascade="all, delete-orphan")
    pesan_diterima = relationship("Pesan", foreign_keys="[Pesan.id_penerima]",
                                  back_populates="penerima", cascade="all, delete-orphan")


# ─── Reset Password ───────────────────────────────────────────────────────────

class ResetPassword(Base):
    __tablename__ = "reset_password"

    id_pertanyaan  = Column(INTEGER(13), primary_key=True, index=True, autoincrement=True)
    id_akun        = Column(INTEGER(13), ForeignKey("akun.id_akun", ondelete="CASCADE"), nullable=False)
    isi_pertanyaan = Column(String(50), nullable=False)
    jawaban        = Column(String(50), nullable=False)

    akun = relationship("Akun", back_populates="reset_password")


# ─── Kelas ────────────────────────────────────────────────────────────────────

class Kelas(Base):
    __tablename__ = "kelas"

    id_kelas   = Column(INTEGER(13), primary_key=True, index=True, autoincrement=True)
    nama_kelas = Column(String(30), nullable=False)


# ─── Guru ─────────────────────────────────────────────────────────────────────

class Guru(Base):
    __tablename__ = "guru"

    id_guru  = Column(INTEGER(13), primary_key=True, index=True, autoincrement=True)
    id_akun  = Column(INTEGER(13), ForeignKey("akun.id_akun", ondelete="CASCADE"), nullable=False, unique=True)
    id_kelas = Column(String(50), nullable=True)   # JSON string "[1,2]"
    nip      = Column(String(20), unique=True, nullable=True)

    akun    = relationship("Akun", back_populates="guru")
    # BUG DIPERBAIKI: back_populates="laporan" ditambahkan agar relasi Laporan tidak error
    laporan = relationship("Laporan", back_populates="guru", cascade="all, delete-orphan")


# ─── Admin ────────────────────────────────────────────────────────────────────

class Admin(Base):
    __tablename__ = "admin"

    id_admin = Column(INTEGER(13), primary_key=True, index=True, autoincrement=True)
    id_akun  = Column(INTEGER(13), ForeignKey("akun.id_akun", ondelete="CASCADE"), nullable=False, unique=True)

    akun = relationship("Akun", back_populates="admin")


# ─── Kepala Sekolah ───────────────────────────────────────────────────────────

class KepalaSekolah(Base):
    __tablename__ = "kepala_sekolah"

    id_kepsek = Column(INTEGER(13), primary_key=True, index=True, autoincrement=True)
    id_akun   = Column(INTEGER(13), ForeignKey("akun.id_akun", ondelete="CASCADE"), nullable=False, unique=True)
    nip       = Column(String(20), unique=True, nullable=True)

    akun = relationship("Akun", back_populates="kepala_sekolah")


# ─── Siswa ────────────────────────────────────────────────────────────────────

class Siswa(Base):
    __tablename__ = "siswa"

    id_siswa      = Column(INTEGER(13), primary_key=True, index=True, autoincrement=True)
    id_kelas      = Column(INTEGER(13), ForeignKey("kelas.id_kelas", ondelete="SET NULL"), nullable=True)
    id_wali_siswa = Column(INTEGER(13), ForeignKey("wali_siswa.id_wali_siswa", ondelete="SET NULL"), nullable=True)
    nisn          = Column(String(25), unique=True, nullable=False)
    nama_siswa    = Column(String(100), nullable=False)
    jenis_kelamin = Column(Enum(JenisKelaminEnum), nullable=False)
    tgl_lahir     = Column(Date, nullable=False)
    tahun_masuk   = Column(INTEGER(7), nullable=False)
    created_at    = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    updated_at    = Column(TIMESTAMP, onupdate=func.now(), nullable=True)

    kelas      = relationship("Kelas",     foreign_keys=[id_kelas])
    wali_siswa = relationship("WaliSiswa", back_populates="siswa", foreign_keys=[id_wali_siswa])


# ─── WaliSiswa ────────────────────────────────────────────────────────────────

class WaliSiswa(Base):
    __tablename__ = "wali_siswa"

    id_wali_siswa = Column(INTEGER(13), primary_key=True, index=True, autoincrement=True)
    id_akun       = Column(INTEGER(13), ForeignKey("akun.id_akun", ondelete="CASCADE"), nullable=False, unique=True)
    id_siswa      = Column(INTEGER(13), nullable=True)
    no_hp_telp    = Column(String(20), nullable=True)
    alamat        = Column(String(100), nullable=True)

    akun  = relationship("Akun",  back_populates="wali_siswa")
    siswa = relationship("Siswa", back_populates="wali_siswa",
                         foreign_keys="[Siswa.id_wali_siswa]",
                         uselist=False)


# ─── Pesan ────────────────────────────────────────────────────────────────────

class Pesan(Base):
    __tablename__ = "pesan"

    id_pesan    = Column(INTEGER(13), primary_key=True, index=True, autoincrement=True)
    id_pengirim = Column(INTEGER(13), ForeignKey("akun.id_akun", ondelete="CASCADE"),
                         nullable=False, index=True)
    id_penerima = Column(INTEGER(13), ForeignKey("akun.id_akun", ondelete="CASCADE"),
                         nullable=False, index=True)
    isi_pesan   = Column(Text, nullable=False)
    waktu       = Column(TIMESTAMP, server_default=func.now(), nullable=False)
    status      = Column(Enum(StatusPesanEnum),
                         default=StatusPesanEnum.terkirim, nullable=False)

    pengirim = relationship("Akun", foreign_keys=[id_pengirim], back_populates="pesan_terkirim")
    penerima = relationship("Akun", foreign_keys=[id_penerima], back_populates="pesan_diterima")


# ─── Absensi ──────────────────────────────────────────────────────────────────

class StatusAbsensiEnum(str, enum.Enum):
    hadir = "hadir"
    sakit = "sakit"
    izin  = "izin"
    alpha = "alpha"


class Absensi(Base):
    __tablename__ = "absensi"

    id_absensi = Column(INTEGER(13), primary_key=True, index=True, autoincrement=True)
    id_siswa   = Column(INTEGER(13), ForeignKey("siswa.id_siswa",  ondelete="CASCADE"),  nullable=False, index=True)
    id_guru    = Column(INTEGER(13), ForeignKey("guru.id_guru",    ondelete="SET NULL"), nullable=True,  index=True)
    tanggal    = Column(Date, nullable=False, index=True)
    status     = Column(Enum(StatusAbsensiEnum), nullable=False, default=StatusAbsensiEnum.hadir)
    keterangan = Column(String(100), nullable=True)

    siswa = relationship("Siswa", foreign_keys=[id_siswa])
    guru  = relationship("Guru",  foreign_keys=[id_guru])


# ─── Catatan Harian ───────────────────────────────────────────────────────────

class TargetCatatanEnum(str, enum.Enum):
    semua_kelas = "semua_kelas"
    satu_kelas  = "satu_kelas"
    satu_siswa  = "satu_siswa"


class CatatanHarian(Base):
    __tablename__ = "catatan_harian"

    id_catatan = Column(INTEGER(13), primary_key=True, index=True, autoincrement=True)
    id_guru    = Column(INTEGER(13), ForeignKey("guru.id_guru",   ondelete="SET NULL"), nullable=True,  index=True)
    id_siswa   = Column(INTEGER(13), ForeignKey("siswa.id_siswa", ondelete="CASCADE"),  nullable=True,  index=True)
    id_kelas   = Column(INTEGER(13), ForeignKey("kelas.id_kelas", ondelete="SET NULL"), nullable=True,  index=True)
    target     = Column(Enum(TargetCatatanEnum), nullable=False, default=TargetCatatanEnum.satu_siswa)
    judul      = Column(String(50), nullable=False)
    foto       = Column(String(50), nullable=True)
    isi        = Column(Text, nullable=False)
    tanggal    = Column(TIMESTAMP, server_default=func.now(), nullable=False, index=True)

    guru  = relationship("Guru",  foreign_keys=[id_guru])
    siswa = relationship("Siswa", foreign_keys=[id_siswa])
    kelas = relationship("Kelas", foreign_keys=[id_kelas])


# ─── Notifikasi ───────────────────────────────────────────────────────────────

class TipeNotifEnum(str, enum.Enum):
    pesan    = "pesan"
    absensi  = "absensi"
    catatan  = "catatan"
    laporan  = "laporan"


class StatusNotifEnum(str, enum.Enum):
    belum_dibaca = "belum_dibaca"
    sudah_dibaca = "sudah_dibaca"


class Notifikasi(Base):
    __tablename__ = "notifikasi"

    id_notif = Column(INTEGER(13), primary_key=True, index=True, autoincrement=True)
    id_akun  = Column(INTEGER(13), ForeignKey("akun.id_akun", ondelete="CASCADE"), nullable=False, index=True)
    judul    = Column(String(50),  nullable=False)
    pesan    = Column(String(100), nullable=False)
    tipe     = Column(Enum(TipeNotifEnum),   nullable=False)
    ref_id   = Column(INTEGER(13), nullable=True)
    tanggal  = Column(TIMESTAMP,  server_default=func.now(), nullable=False, index=True)
    status   = Column(Enum(StatusNotifEnum), default=StatusNotifEnum.belum_dibaca, nullable=False)

    akun = relationship("Akun", foreign_keys=[id_akun])


# ─── Laporan Manual Guru ──────────────────────────────────────────────────────

class StatusLaporanEnum(str, enum.Enum):
    menunggu_verifikasi = "menunggu_verifikasi"
    terverifikasi       = "terverifikasi"


class JenisLaporanEnum(str, enum.Enum):
    absensi = "absensi"
    catatan = "catatan"

class Laporan(Base):
    __tablename__ = "laporan"

    id_laporan     = Column(INTEGER(13), primary_key=True, index=True, autoincrement=True)
    id_kelas       = Column(INTEGER(13), ForeignKey("kelas.id_kelas", ondelete="SET NULL"), nullable=True, index=True)
    id_guru        = Column(INTEGER(13), ForeignKey("guru.id_guru",   ondelete="SET NULL"), nullable=True, index=True)
    periode        = Column(String(20),  nullable=False)
    tanggal_dibuat = Column(Date,        nullable=False)
    jenis_laporan  = Column(Enum(JenisLaporanEnum), nullable=False, default=JenisLaporanEnum.absensi)  # ✅
    status         = Column(Enum(StatusLaporanEnum), default=StatusLaporanEnum.menunggu_verifikasi, nullable=False)
    keterangan     = Column(String(100), nullable=True)
    created_at     = Column(TIMESTAMP,   server_default=func.now(), nullable=False)

    kelas = relationship("Kelas", foreign_keys=[id_kelas])
    guru  = relationship("Guru",  foreign_keys=[id_guru], back_populates="laporan")