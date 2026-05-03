from sqlalchemy import (
    Boolean, Column, ForeignKey, Integer, String,
    DateTime, Date, Text, Enum, TIMESTAMP
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum

from app.database import Base


# ─── Enums ────────────────────────────────────────────────────────────────────

class JenisKelaminEnum(str, enum.Enum):
    L = "L"
    P = "P"

class RoleEnum(str, enum.Enum):
    admin = "admin"
    guru = "guru"
    wali_siswa = "wali_siswa"
    kepala_sekolah = "kepala_sekolah"

class StatusAbsensiEnum(str, enum.Enum):
    hadir = "hadir"
    sakit = "sakit"
    izin = "izin"
    alpha = "alpha"

class StatusPesanEnum(str, enum.Enum):
    terkirim = "terkirim"
    dibaca = "dibaca"

class TipeNotifEnum(str, enum.Enum):
    absensi = "absensi"
    laporan = "laporan"
    pesan = "pesan"
    catatan = "catatan"

class StatusNotifEnum(str, enum.Enum):
    belum_dibaca = "belum_dibaca"
    sudah_dibaca = "sudah_dibaca"


# ─── Tabel Akun ───────────────────────────────────────────────────────────────

class Akun(Base):
    __tablename__ = "akun"

    id_akun      = Column(Integer, primary_key=True, index=True)
    username     = Column(String(100), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    nama         = Column(String(100), nullable=False)
    role         = Column(Enum(RoleEnum), default=RoleEnum.admin, nullable=False)
    first_login  = Column(Boolean, default=True)
    created_at   = Column(TIMESTAMP, server_default=func.now())
    updated_at   = Column(TIMESTAMP, onupdate=func.now())

    # Relationships
    wali_siswa   = relationship("WaliSiswa", back_populates="akun", uselist=False)
    guru         = relationship("Guru", back_populates="akun", uselist=False)
    kepala_sekolah = relationship("KepalaSekolah", back_populates="akun", uselist=False)
    admin        = relationship("Admin", back_populates="akun", uselist=False)
    notifikasi   = relationship("Notifikasi", back_populates="akun")
    reset_password = relationship("ResetPassword", back_populates="akun")

    def __repr__(self):
        return f"<Akun id={self.id_akun} username={self.username}>"


# ─── Tabel Kelas ──────────────────────────────────────────────────────────────

class Kelas(Base):
    __tablename__ = "kelas"

    id_kelas   = Column(Integer, primary_key=True, index=True)
    nama_kelas = Column(String(30), nullable=False)

    # Relationships
    siswa = relationship("Siswa", back_populates="kelas")
    guru  = relationship("Guru", back_populates="kelas")

    def __repr__(self):
        return f"<Kelas id={self.id_kelas} nama={self.nama_kelas}>"


# ─── Tabel Siswa ──────────────────────────────────────────────────────────────

class Siswa(Base):
    __tablename__ = "siswa"

    id_siswa      = Column(Integer, primary_key=True, index=True)
    id_kelas      = Column(Integer, ForeignKey("kelas.id_kelas"), nullable=False)
    id_wali_siswa = Column(Integer, ForeignKey("wali_siswa.id_wali_siswa"), nullable=True)
    nisn          = Column(String(25), unique=True, index=True, nullable=False)
    nama_siswa    = Column(String(100), nullable=False)
    jenis_kelamin = Column(Enum(JenisKelaminEnum), nullable=False)
    tgl_lahir     = Column(Date, nullable=False)
    tahun_masuk   = Column(Integer, nullable=False)
    created_at    = Column(TIMESTAMP, server_default=func.now())
    updated_at    = Column(TIMESTAMP, onupdate=func.now())

    # Relationships
    kelas       = relationship("Kelas", back_populates="siswa")
    wali_siswa  = relationship("WaliSiswa", back_populates="siswa", foreign_keys=[id_wali_siswa])
    absensi     = relationship("Absensi", back_populates="siswa")
    catatan     = relationship("CatatanHarian", back_populates="siswa")
    laporan     = relationship("Laporan", back_populates="siswa")

    def __repr__(self):
        return f"<Siswa id={self.id_siswa} nama={self.nama_siswa}>"


# ─── Tabel Wali Siswa ─────────────────────────────────────────────────────────

class WaliSiswa(Base):
    __tablename__ = "wali_siswa"

    id_wali_siswa = Column(Integer, primary_key=True, index=True)
    id_akun       = Column(Integer, ForeignKey("akun.id_akun"), nullable=False)
    id_siswa      = Column(Integer, ForeignKey("siswa.id_siswa"), nullable=True)
    no_hp_telp    = Column(String(20), nullable=False)
    alamat        = Column(String(100), nullable=True)

    # Relationships
    akun  = relationship("Akun", back_populates="wali_siswa")
    siswa = relationship("Siswa", back_populates="wali_siswa",
                         foreign_keys=[id_siswa], primaryjoin="WaliSiswa.id_siswa == Siswa.id_siswa")

    def __repr__(self):
        return f"<WaliSiswa id={self.id_wali_siswa}>"


# ─── Tabel Guru ───────────────────────────────────────────────────────────────

class Guru(Base):
    __tablename__ = "guru"

    id_guru   = Column(Integer, primary_key=True, index=True)
    id_akun   = Column(Integer, ForeignKey("akun.id_akun"), nullable=False)
    id_kelas  = Column(Integer, ForeignKey("kelas.id_kelas"), nullable=True)
    nip       = Column(String(20), unique=True, index=True, nullable=False)

    # Relationships
    akun    = relationship("Akun", back_populates="guru")
    kelas   = relationship("Kelas", back_populates="guru")
    absensi = relationship("Absensi", back_populates="guru")
    catatan = relationship("CatatanHarian", back_populates="guru")
    laporan = relationship("Laporan", back_populates="guru")

    def __repr__(self):
        return f"<Guru id={self.id_guru} nip={self.nip}>"


# ─── Tabel Kepala Sekolah ─────────────────────────────────────────────────────

class KepalaSekolah(Base):
    __tablename__ = "kepala_sekolah"

    id_kepsek = Column(Integer, primary_key=True, index=True)
    id_akun   = Column(Integer, ForeignKey("akun.id_akun"), nullable=False)
    nip       = Column(String(20), unique=True, index=True, nullable=False)

    # Relationships
    akun = relationship("Akun", back_populates="kepala_sekolah")

    def __repr__(self):
        return f"<KepalaSekolah id={self.id_kepsek} nip={self.nip}>"


# ─── Tabel Admin ──────────────────────────────────────────────────────────────

class Admin(Base):
    __tablename__ = "admin"

    id_admin = Column(Integer, primary_key=True, index=True)
    id_akun  = Column(Integer, ForeignKey("akun.id_akun"), nullable=False)

    # Relationships
    akun = relationship("Akun", back_populates="admin")

    def __repr__(self):
        return f"<Admin id={self.id_admin}>"


# ─── Tabel Reset Password ─────────────────────────────────────────────────────

class ResetPassword(Base):
    __tablename__ = "reset_password"

    id_pertanyaan  = Column(Integer, primary_key=True, index=True)
    id_akun        = Column(Integer, ForeignKey("akun.id_akun"), nullable=False)
    isi_pertanyaan = Column(String(50), nullable=False)
    jawaban        = Column(String(50), nullable=False)

    # Relationships
    akun = relationship("Akun", back_populates="reset_password")

    def __repr__(self):
        return f"<ResetPassword id={self.id_pertanyaan}>"


# ─── Tabel Absensi ────────────────────────────────────────────────────────────

class Absensi(Base):
    __tablename__ = "absensi"

    id_absensi = Column(Integer, primary_key=True, index=True)
    id_siswa   = Column(Integer, ForeignKey("siswa.id_siswa"), nullable=False)
    id_guru    = Column(Integer, ForeignKey("guru.id_guru"), nullable=False)
    tanggal    = Column(Date, nullable=False)
    status     = Column(Enum(StatusAbsensiEnum), nullable=False)
    keterangan = Column(String(100), nullable=True)

    # Relationships
    siswa = relationship("Siswa", back_populates="absensi")
    guru  = relationship("Guru", back_populates="absensi")

    def __repr__(self):
        return f"<Absensi id={self.id_absensi} tanggal={self.tanggal}>"


# ─── Tabel Catatan Harian ─────────────────────────────────────────────────────

class CatatanHarian(Base):
    __tablename__ = "catatan_harian"

    id_catatan = Column(Integer, primary_key=True, index=True)
    id_siswa   = Column(Integer, ForeignKey("siswa.id_siswa"), nullable=False)
    id_guru    = Column(Integer, ForeignKey("guru.id_guru"), nullable=False)
    judul      = Column(String(50), nullable=False)
    foto       = Column(String(50), nullable=True)
    isi        = Column(Text, nullable=False)

    # Relationships
    siswa = relationship("Siswa", back_populates="catatan")
    guru  = relationship("Guru", back_populates="catatan")

    def __repr__(self):
        return f"<CatatanHarian id={self.id_catatan} judul={self.judul}>"


# ─── Tabel Laporan ────────────────────────────────────────────────────────────

class Laporan(Base):
    __tablename__ = "laporan"

    id_laporan    = Column(Integer, primary_key=True, index=True)
    id_siswa      = Column(Integer, ForeignKey("siswa.id_siswa"), nullable=False)
    id_guru       = Column(Integer, ForeignKey("guru.id_guru"), nullable=False)
    periode       = Column(String(20), nullable=False)
    tanggal_dibuat = Column(Date, nullable=False)
    status        = Column(Boolean, default=False)
    keterangan    = Column(String(100), nullable=True)
    created_at    = Column(TIMESTAMP, server_default=func.now())

    # Relationships
    siswa = relationship("Siswa", back_populates="laporan")
    guru  = relationship("Guru", back_populates="laporan")

    def __repr__(self):
        return f"<Laporan id={self.id_laporan} periode={self.periode}>"


# ─── Tabel Pesan ──────────────────────────────────────────────────────────────

class Pesan(Base):
    __tablename__ = "pesan"

    id_pesan    = Column(Integer, primary_key=True, index=True)
    id_pengirim = Column(Integer, ForeignKey("akun.id_akun"), nullable=False)
    id_penerima = Column(Integer, ForeignKey("akun.id_akun"), nullable=False)
    isi_pesan   = Column(Text, nullable=False)
    waktu       = Column(TIMESTAMP, server_default=func.now())
    status      = Column(Enum(StatusPesanEnum), default=StatusPesanEnum.terkirim)

    # Relationships
    pengirim = relationship("Akun", foreign_keys=[id_pengirim], backref="pesan_terkirim")
    penerima = relationship("Akun", foreign_keys=[id_penerima], backref="pesan_diterima")

    def __repr__(self):
        return f"<Pesan id={self.id_pesan}>"


# ─── Tabel Notifikasi ─────────────────────────────────────────────────────────

class Notifikasi(Base):
    __tablename__ = "notifikasi"

    id_notif = Column(Integer, primary_key=True, index=True)
    id_akun  = Column(Integer, ForeignKey("akun.id_akun"), nullable=False)
    judul    = Column(String(50), nullable=False)
    pesan    = Column(String(100), nullable=False)
    tipe     = Column(Enum(TipeNotifEnum), nullable=False)
    ref_id   = Column(Integer, nullable=True)
    tanggal  = Column(DateTime, server_default=func.now())
    status   = Column(Enum(StatusNotifEnum), default=StatusNotifEnum.belum_dibaca)

    # Relationships
    akun = relationship("Akun", back_populates="notifikasi")

    def __repr__(self):
        return f"<Notifikasi id={self.id_notif} judul={self.judul}>"