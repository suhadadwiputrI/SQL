from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, date
from enum import Enum
from pydantic import BaseModel, Field, model_validator
import json


# ─── Enums (sesuai models.py) ─────────────────────────────────────────────────

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
    username:  str            = Field(..., example="qoulansadid")
    password:  str            = Field(..., example="123")
    device_id: Optional[str] = Field(None, max_length=64, example="a1b2c3d4e5f6")


# ─── Akun ─────────────────────────────────────────────────────────────────────
# Model: id, username, password, nama, role, first_login, device_id,
#        created_at, updated_at

class AkunBase(BaseModel):
    username: str      = Field(..., max_length=50, example="budi123")   # String(50) di model
    nama:     str      = Field(..., max_length=50, example="Budi Santoso")  # String(50) di model
    role:     RoleEnum = Field(default=RoleEnum.admin)

class AkunCreate(AkunBase):
    password: str = Field(..., example="rahasia123")

class AkunUpdate(BaseModel):
    username:    Optional[str]      = Field(None, max_length=50)
    password:    Optional[str]      = None
    nama:        Optional[str]      = Field(None, max_length=50)
    role:        Optional[RoleEnum] = None
    first_login: Optional[bool]     = None

class AkunCreateWithRole(BaseModel):
    username: str           = Field(..., max_length=50,  example="kepsek01")
    nama:     str           = Field(..., max_length=50,  example="Siti Kepala")
    role:     RoleEnum      = Field(..., example=RoleEnum.kepala_sekolah)
    nip:      Optional[str] = Field(None, max_length=20, example="196501011990031001")

class AkunOut(AkunBase):
    id:          int
    first_login: bool
    device_id:   Optional[str]      = None
    created_at:  Optional[datetime] = None
    updated_at:  Optional[datetime] = None

    class Config:
        from_attributes = True

class GantiPasswordFirstLoginRequest(BaseModel):
    password_baru: str = Field(..., min_length=6, example="passwordbaru123")


# ─── Reset Password ───────────────────────────────────────────────────────────
# Model: id_pertanyaan (PK), id_akun (FK → akun.id), isi_pertanyaan, jawaban

class ResetPasswordBase(BaseModel):
    isi_pertanyaan: str = Field(..., max_length=50, example="Nama hewan peliharaan pertama?")
    jawaban:        str = Field(..., max_length=50, example="Kucingku")

class ResetPasswordCreate(ResetPasswordBase):
    id_akun: int = Field(..., example=1)   # FK ke akun.id (bukan id generic)

class ResetPasswordUpdate(BaseModel):
    isi_pertanyaan: Optional[str] = Field(None, max_length=50)
    jawaban:        Optional[str] = Field(None, max_length=50)

class ResetPasswordOut(ResetPasswordBase):
    id_pertanyaan: int
    id_akun:       int

    class Config:
        from_attributes = True

class VerifyJawabanRequest(BaseModel):
    id_akun: int = Field(..., example=1)   # konsisten dengan ResetPasswordCreate
    jawaban: str = Field(..., example="Kucingku")

class GantiPasswordRequest(BaseModel):
    id_akun:       int = Field(..., example=1)
    jawaban:       str = Field(..., example="Kucingku")
    password_baru: str = Field(..., example="passwordbaru123")


# ─── Kelas ────────────────────────────────────────────────────────────────────
# Model: id_kelas (PK), nama_kelas String(30)

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
# Model: id_guru (PK), id_akun (FK), id_kelas String(50) JSON, nip String(20)

class GuruBase(BaseModel):
    nip:           Optional[str]       = Field(None, max_length=20, example="198501012010011001")
    list_id_kelas: Optional[List[int]] = Field(
        None, example=[1, 2],
        description="ID kelas yang diampu, maks 2. Disimpan sebagai JSON string di kolom id_kelas.",
    )

class GuruCreate(GuruBase):
    username: str      = Field(..., max_length=50,  example="budi.guru")   # String(50)
    password: str      = Field(...,                 example="rahasia123")
    nama:     str      = Field(..., max_length=50,  example="Budi Santoso")  # String(50)
    role:     RoleEnum = Field(...,                 example=RoleEnum.guru)

class GuruUpdate(BaseModel):
    nip:           Optional[str]       = Field(None, max_length=20)
    list_id_kelas: Optional[List[int]] = Field(
        None, description="Kirim [] untuk hapus semua kelas. Maks 2.",
    )

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


# ─── Admin ────────────────────────────────────────────────────────────────────
# Model: id_admin (PK), id_akun (FK)

class AdminCreate(BaseModel):
    username: str = Field(..., max_length=50, example="admin01")   # String(50)
    nama:     str = Field(..., max_length=50, example="Budi Admin")  # String(50)

class AdminOut(BaseModel):
    id_admin: int
    id_akun:  int
    akun:     Optional[AkunOut] = None

    class Config:
        from_attributes = True


# ─── Kepala Sekolah ───────────────────────────────────────────────────────────
# Model: id_kepsek (PK), id_akun (FK), nip String(20)

class KepsekCreate(BaseModel):
    username: str           = Field(..., max_length=50,  example="kepsek01")   # String(50)
    nama:     str           = Field(..., max_length=50,  example="Siti Kepala")  # String(50)
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


# ─── Siswa Simple (untuk nested, hindari circular ref) ───────────────────────
# Model: id_siswa, id_kelas (FK nullable), id_wali_siswa (FK nullable),
#        nisn String(25), nama_siswa String(50), jenis_kelamin, tgl_lahir, tahun_masuk

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
# Model: id_wali_siswa (PK), id_akun (FK), id_siswa (plain int, bukan FK!),
#        no_hp_telp String(20), alamat String(100)

class WaliSiswaOut(BaseModel):
    id_wali_siswa: int
    id_akun:       int
    id_siswa:      Optional[int] = None   # kolom biasa, bukan FK eksplisit
    no_hp_telp:    Optional[str] = None
    alamat:        Optional[str] = None
    akun:          Optional[AkunOut]       = None
    siswa:         Optional[SiswaSimpleOut] = None

    class Config:
        from_attributes = True

class WaliSiswaUpdate(BaseModel):
    no_hp_telp: Optional[str] = Field(None, max_length=20)
    alamat:     Optional[str] = Field(None, max_length=100)


# ─── Siswa ────────────────────────────────────────────────────────────────────
# Model: nisn String(25), nama_siswa String(50), jenis_kelamin, tgl_lahir,
#        tahun_masuk INTEGER(7), id_kelas (FK SET NULL), id_wali_siswa (FK SET NULL)

class SiswaBase(BaseModel):
    nisn:          str              = Field(..., max_length=25,  example="0012345678")
    nama_siswa:    str              = Field(..., max_length=50,  example="Ahmad Fauzi")  # String(50)
    jenis_kelamin: JenisKelaminEnum = Field(..., example=JenisKelaminEnum.laki_laki)
    tgl_lahir:     date             = Field(..., example="2019-04-10")
    tahun_masuk:   int              = Field(..., example=2024)
    id_kelas:      Optional[int]    = Field(None, example=1)

class SiswaCreate(SiswaBase):
    username_wali: str           = Field(..., max_length=50,  example="wali.ahmad")   # String(50)
    nama_wali:     str           = Field(..., max_length=50,  example="Budi Fauzi")   # String(50)
    no_hp_telp:    Optional[str] = Field(None, max_length=20,  example="081234567890")
    alamat:        Optional[str] = Field(None, max_length=100, example="Jl. Mawar No. 5")

class SiswaUpdate(BaseModel):
    nisn:          Optional[str]              = Field(None, max_length=25)
    nama_siswa:    Optional[str]              = Field(None, max_length=50)
    jenis_kelamin: Optional[JenisKelaminEnum] = None
    tgl_lahir:     Optional[date]             = None
    tahun_masuk:   Optional[int]              = None
    id_kelas:      Optional[int]              = None

class SiswaOut(SiswaBase):
    id_siswa:      int
    id_wali_siswa: Optional[int]          = None
    kelas:         Optional[KelasOut]     = None
    wali_siswa:    Optional[WaliSiswaOut] = None

    class Config:
        from_attributes = True


# ─── Pesan ────────────────────────────────────────────────────────────────────
# Model: id_pesan, id_pengirim (FK), id_penerima (FK), isi_pesan Text,
#        waktu TIMESTAMP, status Enum(StatusPesanEnum)

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
    id_akun_wali:   int
    nama_wali:      str
    inisial:        str
    nama_siswa:     str = ""
    id_kelas_siswa: Optional[int] = None

class GuruListItem(BaseModel):
    id_akun_guru:        int
    nama_guru:           str
    inisial:             str
    pesan_terakhir:      Optional[str]            = None
    waktu:               Optional[datetime]        = None
    status:              Optional[StatusPesanEnum] = None
    jumlah_belum_dibaca: int = 0


# ─── Absensi ──────────────────────────────────────────────────────────────────
# Model: id_absensi, id_siswa (FK CASCADE), id_guru (FK SET NULL → nullable!),
#        tanggal Date, status Enum, keterangan String(100)

class StatusAbsensiEnum(str, Enum):
    hadir = "hadir"
    sakit = "sakit"
    izin  = "izin"
    alpha = "alpha"


class AbsensiSiswaInput(BaseModel):
    """Satu baris input absensi untuk satu siswa."""
    id_siswa:   int
    status:     StatusAbsensiEnum
    keterangan: Optional[str] = Field(None, max_length=100)


class AbsensiBatchRequest(BaseModel):
    """
    Request body POST /absensi/batch
    Guru mengirim daftar absensi seluruh kelas sekaligus.
    """
    id_kelas: int
    tanggal:  date
    data:     List[AbsensiSiswaInput]


class AbsensiOut(BaseModel):
    id_absensi: int
    id_siswa:   int
    id_guru:    Optional[int] = None   # nullable (SET NULL) sesuai model
    tanggal:    date
    status:     StatusAbsensiEnum
    keterangan: Optional[str] = None

    class Config:
        from_attributes = True


class AbsensiHarianSiswaOut(BaseModel):
    """
    Dipakai oleh GET /absensi/siswa/{id_siswa}?bulan=&tahun=
    Satu record per hari yang ada data absensi.
    """
    id_absensi:  int
    id_siswa:    int
    id_guru:     Optional[int] = None   # nullable (SET NULL) sesuai model
    tanggal:     date
    status:      StatusAbsensiEnum
    keterangan:  Optional[str] = None
    nama_guru:   Optional[str] = None   # JOIN dari akun.nama via guru

    class Config:
        from_attributes = True


class RingkasanAbsensiOut(BaseModel):
    """
    Rekap absensi satu siswa dalam satu bulan.
    Dipakai oleh GET /absensi/siswa/{id_siswa}/ringkasan
    """
    bulan:      int
    tahun:      int
    hadir:      int = 0
    sakit:      int = 0
    izin:       int = 0
    alpha:      int = 0
    total_hari: int = 0

    class Config:
        from_attributes = True


class SiswaAbsensiItem(BaseModel):
    """
    Satu item dalam daftar siswa untuk input absensi guru.
    Berisi info siswa + status absensi hari ini (jika sudah diisi).
    """
    id_siswa:   int
    nama_siswa: str
    status:     Optional[StatusAbsensiEnum] = None
    keterangan: Optional[str]               = None

    class Config:
        from_attributes = True


# ─── Catatan Harian ───────────────────────────────────────────────────────────
# Model: id_catatan, id_guru (FK SET NULL), id_siswa (FK CASCADE),
#        id_kelas (FK SET NULL), target Enum, judul String(50), foto String(50),
#        isi Text, tanggal TIMESTAMP

class TargetCatatanEnum(str, Enum):
    semua_kelas = "semua_kelas"
    satu_kelas  = "satu_kelas"
    satu_siswa  = "satu_siswa"


class CatatanHarianCreate(BaseModel):
    """
    Request body POST /catatan/

    Aturan validasi target:
      - semua_kelas → id_siswa & id_kelas wajib None
      - satu_kelas  → id_kelas wajib diisi, id_siswa wajib None
      - satu_siswa  → id_siswa wajib diisi, id_kelas wajib None
    """
    target:   TargetCatatanEnum = Field(..., example="satu_siswa")
    judul:    str               = Field(..., max_length=50, example="Kegiatan Olahraga Pagi")
    isi:      str               = Field(..., example="Anak sangat antusias mengikuti kegiatan...")
    foto:     Optional[str]     = Field(None, max_length=50, example="foto_olahraga.jpg")
    id_siswa: Optional[int]     = Field(None, example=13)
    id_kelas: Optional[int]     = Field(None, example=1)

    @model_validator(mode="after")
    def validate_target_fields(self) -> "CatatanHarianCreate":
        if self.target == TargetCatatanEnum.semua_kelas:
            if self.id_siswa is not None or self.id_kelas is not None:
                raise ValueError(
                    "Target 'semua_kelas': id_siswa dan id_kelas harus kosong (null)"
                )
        elif self.target == TargetCatatanEnum.satu_kelas:
            if self.id_kelas is None:
                raise ValueError("Target 'satu_kelas': id_kelas wajib diisi")
            if self.id_siswa is not None:
                raise ValueError("Target 'satu_kelas': id_siswa harus kosong (null)")
        elif self.target == TargetCatatanEnum.satu_siswa:
            if self.id_siswa is None:
                raise ValueError("Target 'satu_siswa': id_siswa wajib diisi")
            if self.id_kelas is not None:
                raise ValueError("Target 'satu_siswa': id_kelas harus kosong (null)")
        return self


class CatatanHarianUpdate(BaseModel):
    """Request body PUT /catatan/{id_catatan}"""
    judul: Optional[str] = Field(None, max_length=50)
    isi:   Optional[str] = None
    foto:  Optional[str] = Field(None, max_length=50)


class CatatanHarianOut(BaseModel):
    """Response untuk satu catatan — dipakai guru & wali."""
    id_catatan: int
    id_guru:    Optional[int]         = None   # nullable (SET NULL)
    id_siswa:   Optional[int]         = None   # nullable
    id_kelas:   Optional[int]         = None   # nullable (SET NULL)
    target:     TargetCatatanEnum
    judul:      str
    foto:       Optional[str]         = None
    isi:        str
    tanggal:    datetime               # TIMESTAMP di model
    nama_guru:  Optional[str]         = None   # hasil JOIN
    nama_siswa: Optional[str]         = None   # hasil JOIN (jika target=satu_siswa)
    nama_kelas: Optional[str]         = None   # hasil JOIN (jika target=satu_kelas)

    class Config:
        from_attributes = True


class CatatanListResponse(BaseModel):
    """
    Wrapper response untuk list catatan + total.
    Dipakai endpoint GET /catatan/siswa/{id_siswa} dan GET /catatan/guru/
    """
    total: int
    data:  List[CatatanHarianOut]


# ─── Notifikasi ───────────────────────────────────────────────────────────────
# Model: id_notif, id_akun (FK), judul String(50), pesan String(100),
#        tipe Enum, ref_id INTEGER nullable, tanggal TIMESTAMP, status Enum

class TipeNotifEnum(str, Enum):
    pesan   = "pesan"
    absensi = "absensi"
    catatan = "catatan"
    laporan = "laporan"


class StatusNotifEnum(str, Enum):
    belum_dibaca = "belum_dibaca"
    sudah_dibaca = "sudah_dibaca"


class NotifikasiOut(BaseModel):
    """Response satu item notifikasi."""
    id_notif: int
    id_akun:  int
    judul:    str               # String(50)
    pesan:    str               # String(100)
    tipe:     TipeNotifEnum
    ref_id:   Optional[int]    = None
    tanggal:  datetime          # TIMESTAMP
    status:   StatusNotifEnum

    class Config:
        from_attributes = True


class NotifikasiListResponse(BaseModel):
    """Wrapper list + jumlah belum dibaca."""
    total_belum_dibaca: int
    data:               List[NotifikasiOut]


class BacaNotifRequest(BaseModel):
    """
    Body PUT /notifikasi/baca
    Kirim id_notif tertentu, atau kosongkan (None) untuk tandai SEMUA dibaca.
    """
    id_notif: Optional[int] = Field(
        None,
        description="ID notif yang ingin ditandai. Kosongkan untuk tandai semua.",
    )


# ─── Laporan Otomatis: Ringkasan Absensi per Siswa (dalam kelas) ──────────────

class RingkasanAbsensiSiswaOut(BaseModel):
    """
    Rekap absensi satu siswa dalam satu bulan.
    Dipakai dalam LaporanKelasOut (list per kelas).
    """
    id_siswa:   int
    nama_siswa: str
    hadir:      int = 0
    sakit:      int = 0
    izin:       int = 0
    alpha:      int = 0
    total_hari: int = 0

    class Config:
        from_attributes = True


# ─── Laporan Otomatis: Per Siswa (gabungan absensi + catatan) ─────────────────

class LaporanSiswaOut(BaseModel):
    """
    Response GET /laporan/otomatis/siswa/{id_siswa}?bulan=&tahun=
    Menggabungkan ringkasan absensi + list catatan untuk satu siswa.
    """
    id_siswa:   int
    nama_siswa: str
    nama_kelas: Optional[str] = None

    bulan: int
    tahun: int

    hadir:      int = 0
    sakit:      int = 0
    izin:       int = 0
    alpha:      int = 0
    total_hari: int = 0

    catatan:       List["CatatanHarianOut"] = []
    total_catatan: int = 0


# ─── Laporan Otomatis: Per Kelas ──────────────────────────────────────────────

class LaporanKelasOut(BaseModel):
    """
    Response GET /laporan/otomatis/kelas/{id_kelas}?bulan=&tahun=
    Ringkasan absensi semua siswa di satu kelas.
    """
    id_kelas:   int
    nama_kelas: str
    bulan:      int
    tahun:      int

    total_siswa: int = 0
    total_hadir: int = 0
    total_sakit: int = 0
    total_izin:  int = 0
    total_alpha: int = 0

    siswa: List[RingkasanAbsensiSiswaOut] = []


LaporanSiswaOut.model_rebuild()


# ─── Laporan Manual Guru ──────────────────────────────────────────────────────
# Model: id_laporan, id_kelas (FK SET NULL), id_guru (FK SET NULL),
#        periode String(20), tanggal_dibuat Date, jenis_laporan Enum,
#        status Enum, keterangan String(100), created_at TIMESTAMP

class StatusLaporanEnum(str, Enum):
    menunggu_verifikasi = "menunggu_verifikasi"
    terverifikasi       = "terverifikasi"


class JenisLaporanEnum(str, Enum):
    absensi = "absensi"
    catatan = "catatan"


class LaporanCreate(BaseModel):
    """
    Request body POST /laporan/
    - id_guru       : diambil otomatis dari JWT, tidak perlu dikirim
    - id_kelas      : wajib — laporan dibuat per kelas
    - periode       : bulan & tahun laporan, contoh "Mei 2025" (max 20 karakter)
    - tanggal_dibuat: tanggal guru membuat laporan
    - jenis_laporan : 'absensi' atau 'catatan'
    - keterangan    : catatan opsional dari guru (max 100 karakter)
    """
    id_kelas:       int              = Field(..., example=1, description="ID kelas yang dilaporkan")
    periode:        str              = Field(..., max_length=20, example="Mei 2025")
    tanggal_dibuat: date             = Field(..., example="2025-05-17")
    jenis_laporan:  JenisLaporanEnum = Field(JenisLaporanEnum.absensi, example="absensi")
    keterangan:     Optional[str]    = Field(None, max_length=100, description="Catatan dari guru")


class LaporanVerifikasi(BaseModel):
    """
    Request body PUT /laporan/{id_laporan}/verifikasi
    Hanya admin yang dapat memverifikasi laporan.
    """
    status:     StatusLaporanEnum = Field(
                    ...,
                    example=StatusLaporanEnum.terverifikasi,
                    description="'menunggu_verifikasi' atau 'terverifikasi'",
                )
    keterangan: Optional[str]     = Field(None, max_length=100, description="Catatan dari admin")


class LaporanOut(BaseModel):
    """Response satu laporan manual guru."""
    id_laporan:     int
    id_kelas:       Optional[int]              = None   # nullable (SET NULL saat kelas dihapus)
    id_guru:        Optional[int]              = None   # nullable (SET NULL saat guru dihapus)
    periode:        str
    tanggal_dibuat: date
    jenis_laporan:  Optional[JenisLaporanEnum] = JenisLaporanEnum.absensi
    status:         StatusLaporanEnum          = StatusLaporanEnum.menunggu_verifikasi
    keterangan:     Optional[str]              = None
    created_at:     Optional[datetime]         = None   # TIMESTAMP audit

    # Hasil JOIN — diisi backend
    nama_kelas: Optional[str] = None
    nama_guru:  Optional[str] = None

    class Config:
        from_attributes = True


class LaporanListResponse(BaseModel):
    """
    Wrapper list laporan.
    total_selesai = jumlah laporan berstatus 'terverifikasi'
    total_belum   = jumlah laporan berstatus 'menunggu_verifikasi'
    """
    total:         int
    total_selesai: int = 0
    total_belum:   int = 0
    data:          List[LaporanOut]


# ─── Rekap Absensi Siswa (range tanggal) ──────────────────────────────────────

class RingkasanAbsensiSiswaRangeOut(BaseModel):
    """
    Rekap absensi satu siswa dalam range tanggal.
    Dipakai dalam LaporanAbsensiKelasOut.
    """
    id_siswa:   int
    nama_siswa: str
    nisn:       Optional[str] = None
    hadir:      int = 0
    sakit:      int = 0
    izin:       int = 0
    alpha:      int = 0
    total_hari: int = 0

    class Config:
        from_attributes = True


# ─── Laporan Absensi Kelas (range tanggal) ────────────────────────────────────

class LaporanAbsensiKelasOut(BaseModel):
    """
    Response GET /laporan/absensi?id_kelas=&tanggal_awal=&tanggal_akhir=
    Rekap absensi semua siswa dalam satu kelas berdasarkan range tanggal.
    """
    id_kelas:      int
    nama_kelas:    str
    tanggal_awal:  date
    tanggal_akhir: date

    total_siswa: int = 0
    total_hadir: int = 0
    total_sakit: int = 0
    total_izin:  int = 0
    total_alpha: int = 0

    siswa: List[RingkasanAbsensiSiswaRangeOut] = []

    class Config:
        from_attributes = True


# ─── Catatan Per Siswa (range tanggal) ────────────────────────────────────────

class CatatanRangeOut(BaseModel):
    """Satu item catatan harian dalam rentang tanggal laporan."""
    id_catatan: int
    tanggal:    date
    judul:      str
    isi:        str

    class Config:
        from_attributes = True


class LaporanCatatanSiswaOut(BaseModel):
    id_siswa:       int
    nama_siswa:     str
    nisn:           Optional[str]          = None
    jumlah_catatan: int                    = 0
    catatan:        List[CatatanRangeOut]  = []

    class Config:
        from_attributes = True


# ─── Laporan Catatan Kelas (range tanggal) ────────────────────────────────────

class LaporanCatatanKelasOut(BaseModel):
    """
    Response GET /laporan/catatan?id_kelas=&tanggal_awal=&tanggal_akhir=
    Daftar catatan harian (target=satu_siswa) untuk semua siswa dalam satu kelas.
    """
    id_kelas:      int
    nama_kelas:    str
    tanggal_awal:  date
    tanggal_akhir: date
    total_siswa:   int = 0

    siswa: List[LaporanCatatanSiswaOut] = []

    class Config:
        from_attributes = True