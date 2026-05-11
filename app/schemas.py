from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from enum import Enum
from pydantic import BaseModel, Field, model_validator
import json


class RoleEnum(str, Enum):
    admin          = "admin"
    guru           = "guru"
    wali_siswa     = "wali_siswa"
    kepala_sekolah = "kepala_sekolah"


class JenisKelaminEnum(str, Enum):
    laki_laki = "laki_laki"
    perempuan = "perempuan"


class StatusPesanEnum(str, Enum):
    terkirim = "terkirim"
    diterima = "diterima"
    dibaca   = "dibaca"


# ─── Auth ─────────────────────────────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type:   str
    first_login:  bool = False

class LoginRequest(BaseModel):
    username: str = Field(..., example="qoulansadid")
    password: str = Field(..., example="123")


# ─── Akun ─────────────────────────────────────────────────────────────────────

class AkunBase(BaseModel):
    username: str      = Field(..., max_length=100, example="budi123")
    nama:     str      = Field(..., max_length=100, example="Budi Santoso")
    role:     RoleEnum = Field(default=RoleEnum.admin)

class AkunCreate(AkunBase):
    password: str = Field(..., example="rahasia123")

class AkunUpdate(BaseModel):
    username:    Optional[str]      = Field(None, max_length=100)
    password:    Optional[str]      = None
    nama:        Optional[str]      = Field(None, max_length=100)
    role:        Optional[RoleEnum] = None
    first_login: Optional[bool]     = None

class AkunCreateWithRole(BaseModel):
    username: str           = Field(..., max_length=100, example="kepsek01")
    nama:     str           = Field(..., max_length=100, example="Siti Kepala")
    role:     RoleEnum      = Field(..., example=RoleEnum.kepala_sekolah)
    nip:      Optional[str] = Field(None, max_length=20, example="196501011990031001")

class AkunOut(AkunBase):
    id_akun:     int
    first_login: bool
    created_at:  Optional[datetime] = None
    updated_at:  Optional[datetime] = None

    class Config:
        from_attributes = True

class GantiPasswordFirstLoginRequest(BaseModel):
    password_baru: str = Field(..., min_length=6, example="passwordbaru123")


# ─── Reset Password ───────────────────────────────────────────────────────────

class ResetPasswordBase(BaseModel):
    isi_pertanyaan: str = Field(..., max_length=50, example="Nama hewan peliharaan pertama?")
    jawaban:        str = Field(..., max_length=50, example="Kucingku")

class ResetPasswordCreate(ResetPasswordBase):
    id_akun: int

class ResetPasswordUpdate(BaseModel):
    isi_pertanyaan: Optional[str] = Field(None, max_length=50)
    jawaban:        Optional[str] = Field(None, max_length=50)

class ResetPasswordOut(ResetPasswordBase):
    id_pertanyaan: int
    id_akun:       int

    class Config:
        from_attributes = True

class VerifyJawabanRequest(BaseModel):
    id_akun: int
    jawaban: str = Field(..., example="Kucingku")

class GantiPasswordRequest(BaseModel):
    id_akun:       int
    jawaban:       str = Field(..., example="Kucingku")
    password_baru: str = Field(..., example="passwordbaru123")


# ─── Kelas ────────────────────────────────────────────────────────────────────

class KelasBase(BaseModel):
    nama_kelas: str = Field(..., max_length=30, example="TK A")

class KelasCreate(KelasBase):
    pass

class KelasUpdate(BaseModel):
    nama_kelas: Optional[str] = Field(None, max_length=30)

class KelasOut(KelasBase):
    id_kelas: int

    class Config:
        from_attributes = True


# ─── Guru ─────────────────────────────────────────────────────────────────────

class GuruBase(BaseModel):
    nip:           Optional[str]       = Field(None, max_length=20, example="198501012010011001")
    list_id_kelas: Optional[List[int]] = Field(None, example=[1, 2],
                                            description="ID kelas yang diampu, maks 2. "
                                                        "Disimpan sebagai JSON string di kolom id_kelas.")

class GuruCreate(GuruBase):
    username: str      = Field(..., max_length=100, example="budi.guru")
    password: str      = Field(...,                 example="rahasia123")
    nama:     str      = Field(..., max_length=100, example="Budi Santoso")
    role:     RoleEnum = Field(...,                 example=RoleEnum.guru)

class GuruUpdate(BaseModel):
    nip:           Optional[str]       = Field(None, max_length=20)
    list_id_kelas: Optional[List[int]] = Field(None,
                                               description="Kirim [] untuk hapus semua kelas. Maks 2.")

class GuruOut(BaseModel):
    id_guru:       int
    id_akun:       int
    nip:           Optional[str]       = None
    list_id_kelas: Optional[List[int]] = None  
    akun:          Optional[AkunOut]   = None

    class Config:
        from_attributes = True


# ─── Admin ────────────────────────────────────────────────────────────────────

class AdminCreate(BaseModel):
    username: str = Field(..., max_length=100, example="admin01")
    nama:     str = Field(..., max_length=100, example="Budi Admin")

class AdminOut(BaseModel):
    id_admin: int
    id_akun:  int
    akun:     Optional[AkunOut] = None

    class Config:
        from_attributes = True


# ─── Kepala Sekolah ───────────────────────────────────────────────────────────

class KepsekCreate(BaseModel):
    username: str           = Field(..., max_length=100, example="kepsek01")
    nama:     str           = Field(..., max_length=100, example="Siti Kepala")
    nip:      Optional[str] = Field(None, max_length=20, example="196501011990031001")

class KepsekUpdate(BaseModel):
    nip: Optional[str] = Field(None, max_length=20)

class KepsekOut(BaseModel):
    id_kepsek: int
    id_akun:   int
    nip:       Optional[str] = None
    akun:      Optional[AkunOut] = None

    class Config:
        from_attributes = True

# ─── Siswa Simple (untuk nested di WaliSiswaOut, hindari circular ref) ────────

class SiswaSimpleOut(BaseModel):
    id_siswa:      int
    nisn:          str
    nama_siswa:    str
    jenis_kelamin: JenisKelaminEnum
    tgl_lahir:     date
    tahun_masuk:   int
    id_kelas:      Optional[int]      = None
    id_wali_siswa: Optional[int]      = None
    kelas:         Optional[KelasOut] = None

    class Config:
        from_attributes = True

# ─── WaliSiswa ────────────────────────────────────────────────────────────────

class WaliSiswaOut(BaseModel):
    id_wali_siswa: int
    id_akun:       int
    id_siswa:      Optional[int] = None
    no_hp_telp:    Optional[str] = None
    alamat:        Optional[str] = None
    akun:          Optional[AkunOut] = None
    siswa:         Optional[SiswaSimpleOut] = None

    class Config:
        from_attributes = True

class WaliSiswaUpdate(BaseModel):
    no_hp_telp: Optional[str] = Field(None, max_length=20)
    alamat:     Optional[str] = Field(None, max_length=100)


# ─── Siswa ────────────────────────────────────────────────────────────────────

class SiswaBase(BaseModel):
    nisn:          str              = Field(..., max_length=25,  example="0012345678")
    nama_siswa:    str              = Field(..., max_length=100, example="Ahmad Fauzi")
    jenis_kelamin: JenisKelaminEnum = Field(..., example=JenisKelaminEnum.laki_laki)
    tgl_lahir:     date             = Field(..., example="2019-04-10")
    tahun_masuk:   int              = Field(..., example=2024)
    id_kelas:      Optional[int]    = Field(None, example=1)

class SiswaCreate(SiswaBase):
    username_wali: str           = Field(..., max_length=100, example="wali.ahmad")
    nama_wali:     str           = Field(..., max_length=100, example="Budi Fauzi")
    no_hp_telp:    Optional[str] = Field(None, max_length=20,  example="081234567890")
    alamat:        Optional[str] = Field(None, max_length=100, example="Jl. Mawar No. 5")

class SiswaUpdate(BaseModel):
    nisn:          Optional[str]              = Field(None, max_length=25)
    nama_siswa:    Optional[str]              = Field(None, max_length=100)
    jenis_kelamin: Optional[JenisKelaminEnum] = None
    tgl_lahir:     Optional[date]             = None
    tahun_masuk:   Optional[int]              = None
    id_kelas:      Optional[int]              = None

class SiswaOut(SiswaBase):
    id_siswa:      int
    id_wali_siswa: Optional[int]         = None
    wali_siswa:    Optional[WaliSiswaOut] = None

    class Config:
        from_attributes = True


# ─── Pesan ────────────────────────────────────────────────────────────────────

class PesanCreate(BaseModel):
    id_penerima: int = Field(..., example=5)
    isi_pesan:   str = Field(..., min_length=1, example="Selamat pagi, ada yang bisa saya bantu?")

class PesanOut(BaseModel):
    id_pesan:    int
    id_pengirim: int
    id_penerima: int
    isi_pesan:   str
    waktu:       datetime
    status:      StatusPesanEnum

    class Config:
        from_attributes = True

class TandaiBacaRequest(BaseModel):
    id_pengirim: int = Field(..., example=3)

class PercakapanItem(BaseModel):
    id_akun_lawan:       int
    nama_lawan:          str
    nama_siswa:          Optional[str] = None
    inisial:             str
    pesan_terakhir:      str
    waktu:               datetime
    status:              StatusPesanEnum
    jumlah_belum_dibaca: int = 0

class WaliListItem(BaseModel):
    id_akun_wali: int
    nama_wali:    str
    inisial:      str
    nama_siswa:   str = ""

class GuruListItem(BaseModel):
    id_akun_guru: int
    nama_guru:    str
    inisial:      str
    pesan_terakhir:      Optional[str]              = None
    waktu:               Optional[datetime]          = None
    status:              Optional[StatusPesanEnum]   = None
    jumlah_belum_dibaca: int = 0
    
class GuruOut(BaseModel):
    id_guru:       int
    id_akun:       int
    nip:           Optional[str]       = None
    list_id_kelas: Optional[List[int]] = None
    akun:          Optional[AkunOut]   = None

    @model_validator(mode='before')
    @classmethod
    def parse_id_kelas(cls, data):
        if hasattr(data, 'id_kelas'):
            raw = data.id_kelas
            try:
                parsed = json.loads(raw) if raw else []
                data.__dict__['list_id_kelas'] = (
                    [int(x) for x in parsed] if isinstance(parsed, list)
                    else [int(parsed)]
                )
            except (ValueError, TypeError):
                data.__dict__['list_id_kelas'] = []
        return data

    class Config:
        from_attributes = True    