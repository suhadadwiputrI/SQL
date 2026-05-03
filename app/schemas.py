from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import date, datetime
from enum import Enum


# ─── Enums ────────────────────────────────────────────────────────────────────

class JenisKelaminEnum(str, Enum):
    L = "L"
    P = "P"

class RoleEnum(str, Enum):
    admin = "admin"
    guru = "guru"
    wali_siswa = "wali_siswa"
    kepala_sekolah = "kepala_sekolah"

class StatusAbsensiEnum(str, Enum):
    hadir = "hadir"
    sakit = "sakit"
    izin = "izin"
    alpha = "alpha"

class StatusPesanEnum(str, Enum):
    terkirim = "terkirim"
    dibaca = "dibaca"

class TipeNotifEnum(str, Enum):
    absensi = "absensi"
    laporan = "laporan"
    pesan = "pesan"
    catatan = "catatan"

class StatusNotifEnum(str, Enum):
    belum_dibaca = "belum_dibaca"
    sudah_dibaca = "sudah_dibaca"


# ─── Akun ─────────────────────────────────────────────────────────────────────

class AkunBase(BaseModel):
    username: str = Field(..., max_length=100, example="budi123")
    nama: str = Field(..., max_length=100, example="Budi Santoso")
    role: RoleEnum = Field(default=RoleEnum.admin)

class AkunCreate(AkunBase):
    password: str = Field(..., min_length=6, example="rahasia123")

class AkunUpdate(BaseModel):
    username: Optional[str] = Field(None, max_length=100)
    nama: Optional[str] = Field(None, max_length=100)
    role: Optional[RoleEnum] = None
    first_login: Optional[bool] = None

class AkunOut(AkunBase):
    id_akun: int
    first_login: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── Kelas ────────────────────────────────────────────────────────────────────

class KelasBase(BaseModel):
    nama_kelas: str = Field(..., max_length=30, example="6A")

class KelasCreate(KelasBase):
    pass

class KelasUpdate(BaseModel):
    nama_kelas: Optional[str] = Field(None, max_length=30)

class KelasOut(KelasBase):
    id_kelas: int

    class Config:
        from_attributes = True


# ─── Siswa ────────────────────────────────────────────────────────────────────

class SiswaBase(BaseModel):
    id_kelas: int
    nisn: str = Field(..., max_length=25, example="0012345678")
    nama_siswa: str = Field(..., max_length=100, example="Andi Pratama")
    jenis_kelamin: JenisKelaminEnum
    tgl_lahir: date = Field(..., example="2010-05-15")
    tahun_masuk: int = Field(..., example=2022)

class SiswaCreate(SiswaBase):
    id_wali_siswa: Optional[int] = None

class SiswaUpdate(BaseModel):
    id_kelas: Optional[int] = None
    id_wali_siswa: Optional[int] = None
    nisn: Optional[str] = Field(None, max_length=25)
    nama_siswa: Optional[str] = Field(None, max_length=100)
    jenis_kelamin: Optional[JenisKelaminEnum] = None
    tgl_lahir: Optional[date] = None
    tahun_masuk: Optional[int] = None

class SiswaOut(SiswaBase):
    id_siswa: int
    id_wali_siswa: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── Wali Siswa ───────────────────────────────────────────────────────────────

class WaliSiswaBase(BaseModel):
    no_hp_telp: str = Field(..., max_length=20, example="081234567890")
    alamat: Optional[str] = Field(None, max_length=100, example="Jl. Merdeka No. 1")

class WaliSiswaCreate(WaliSiswaBase):
    id_akun: int
    id_siswa: Optional[int] = None

class WaliSiswaUpdate(BaseModel):
    no_hp_telp: Optional[str] = Field(None, max_length=20)
    alamat: Optional[str] = Field(None, max_length=100)
    id_siswa: Optional[int] = None

class WaliSiswaOut(WaliSiswaBase):
    id_wali_siswa: int
    id_akun: int
    id_siswa: Optional[int] = None

    class Config:
        from_attributes = True


# ─── Guru ─────────────────────────────────────────────────────────────────────

class GuruBase(BaseModel):
    nip: str = Field(..., max_length=20, example="198501012010011001")
    id_kelas: Optional[int] = None

class GuruCreate(GuruBase):
    id_akun: int

class GuruUpdate(BaseModel):
    nip: Optional[str] = Field(None, max_length=20)
    id_kelas: Optional[int] = None

class GuruOut(GuruBase):
    id_guru: int
    id_akun: int

    class Config:
        from_attributes = True


# ─── Kepala Sekolah ───────────────────────────────────────────────────────────

class KepalaSekolahBase(BaseModel):
    nip: str = Field(..., max_length=20, example="196501011990011001")

class KepalaSekolahCreate(KepalaSekolahBase):
    id_akun: int

class KepalaSekolahUpdate(BaseModel):
    nip: Optional[str] = Field(None, max_length=20)

class KepalaSekolahOut(KepalaSekolahBase):
    id_kepsek: int
    id_akun: int

    class Config:
        from_attributes = True


# ─── Admin ────────────────────────────────────────────────────────────────────

class AdminCreate(BaseModel):
    id_akun: int

class AdminOut(BaseModel):
    id_admin: int
    id_akun: int

    class Config:
        from_attributes = True


# ─── Reset Password ───────────────────────────────────────────────────────────

class ResetPasswordBase(BaseModel):
    isi_pertanyaan: str = Field(..., max_length=50, example="Nama hewan peliharaan pertama?")
    jawaban: str = Field(..., max_length=50, example="Kucingku")

class ResetPasswordCreate(ResetPasswordBase):
    id_akun: int

class ResetPasswordUpdate(BaseModel):
    isi_pertanyaan: Optional[str] = Field(None, max_length=50)
    jawaban: Optional[str] = Field(None, max_length=50)

class ResetPasswordOut(ResetPasswordBase):
    id_pertanyaan: int
    id_akun: int

    class Config:
        from_attributes = True


# ─── Absensi ──────────────────────────────────────────────────────────────────

class AbsensiBase(BaseModel):
    id_siswa: int
    id_guru: int
    tanggal: date = Field(..., example="2024-07-15")
    status: StatusAbsensiEnum
    keterangan: Optional[str] = Field(None, max_length=100)

class AbsensiCreate(AbsensiBase):
    pass

class AbsensiUpdate(BaseModel):
    tanggal: Optional[date] = None
    status: Optional[StatusAbsensiEnum] = None
    keterangan: Optional[str] = Field(None, max_length=100)

class AbsensiOut(AbsensiBase):
    id_absensi: int

    class Config:
        from_attributes = True


# ─── Catatan Harian ───────────────────────────────────────────────────────────

class CatatanHarianBase(BaseModel):
    id_siswa: int
    id_guru: int
    judul: str = Field(..., max_length=50, example="Kegiatan Melukis")
    foto: Optional[str] = Field(None, max_length=50)
    isi: str = Field(..., example="Hari ini siswa belajar melukis dengan gembira.")

class CatatanHarianCreate(CatatanHarianBase):
    pass

class CatatanHarianUpdate(BaseModel):
    judul: Optional[str] = Field(None, max_length=50)
    foto: Optional[str] = Field(None, max_length=50)
    isi: Optional[str] = None

class CatatanHarianOut(CatatanHarianBase):
    id_catatan: int

    class Config:
        from_attributes = True


# ─── Laporan ──────────────────────────────────────────────────────────────────

class LaporanBase(BaseModel):
    id_siswa: int
    id_guru: int
    periode: str = Field(..., max_length=20, example="Juli 2024")
    tanggal_dibuat: date = Field(..., example="2024-07-31")
    status: bool = False
    keterangan: Optional[str] = Field(None, max_length=100)

class LaporanCreate(LaporanBase):
    pass

class LaporanUpdate(BaseModel):
    periode: Optional[str] = Field(None, max_length=20)
    tanggal_dibuat: Optional[date] = None
    status: Optional[bool] = None
    keterangan: Optional[str] = Field(None, max_length=100)

class LaporanOut(LaporanBase):
    id_laporan: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ─── Pesan ────────────────────────────────────────────────────────────────────

class PesanBase(BaseModel):
    id_pengirim: int
    id_penerima: int
    isi_pesan: str = Field(..., example="Selamat siang, bagaimana perkembangan anak saya?")

class PesanCreate(PesanBase):
    pass

class PesanUpdate(BaseModel):
    status: Optional[StatusPesanEnum] = None

class PesanOut(PesanBase):
    id_pesan: int
    waktu: Optional[datetime] = None
    status: StatusPesanEnum

    class Config:
        from_attributes = True


# ─── Notifikasi ───────────────────────────────────────────────────────────────

class NotifikasiBase(BaseModel):
    id_akun: int
    judul: str = Field(..., max_length=50, example="Absensi Baru")
    pesan: str = Field(..., max_length=100, example="Andi hadir hari ini.")
    tipe: TipeNotifEnum
    ref_id: Optional[int] = None

class NotifikasiCreate(NotifikasiBase):
    pass

class NotifikasiUpdate(BaseModel):
    status: Optional[StatusNotifEnum] = None

class NotifikasiOut(NotifikasiBase):
    id_notif: int
    tanggal: Optional[datetime] = None
    status: StatusNotifEnum

    class Config:
        from_attributes = True