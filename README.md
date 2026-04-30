# 🚀 FastAPI MySQL Server — Siap Deploy ke Railway

REST API lengkap dengan CRUD menggunakan FastAPI + SQLAlchemy + **MySQL**.  
Mendukung **MySQL lokal** (development) dan **MySQL Railway** (production).

---

## 📁 Struktur Proyek

```
fastapi-railway/
├── app/
│   ├── __init__.py
│   ├── main.py        # Entry point FastAPI
│   ├── database.py    # Koneksi database MySQL
│   ├── models.py      # Model SQLAlchemy
│   ├── schemas.py     # Schema Pydantic
│   └── crud.py        # Operasi database
├── alembic/           # Migrasi database
│   ├── env.py
│   └── versions/
├── alembic.ini
├── requirements.txt
├── Procfile
├── railway.toml
└── .gitignore
```

---

## 🖥️ Jalankan Lokal

### 1. Pastikan MySQL Berjalan

Buat database lokal terlebih dahulu:

```sql
CREATE DATABASE fastapi_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 2. Clone & Install

```bash
git clone <repo-url>
cd fastapi-railway

python -m venv venv
source venv/bin/activate        # Linux/Mac
# venv\Scripts\activate         # Windows

pip install -r requirements.txt
```

### 3. Set Environment Variable Lokal

Buat file `.env` (jangan di-commit ke git!):

```env
DATABASE_URL=mysql+pymysql://root:passwordmu@localhost:3306/fastapi_db
```

Atau export langsung:

```bash
export DATABASE_URL="mysql+pymysql://root:passwordmu@localhost:3306/fastapi_db"
```

### 4. Jalankan Migrasi & Server

```bash
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```

Buka **http://localhost:8000/docs** untuk Swagger UI.

---

## 🚂 Deploy ke Railway (Step-by-Step)

### Langkah 1 — Buat Akun & Project

1. Daftar/login di [railway.app](https://railway.app)
2. Klik **New Project**

### Langkah 2 — Tambahkan MySQL Database

1. Di dashboard, klik **+ Add Service** → **Database** → **MySQL**
2. Tunggu beberapa detik hingga MySQL selesai di-provision
3. Klik service MySQL → tab **Variables**
4. Catat variabel `MYSQL_URL` atau klik **Connect** untuk melihat connection string

### Langkah 3 — Deploy Aplikasi dari GitHub

1. Di project yang sama, klik **+ Add Service** → **GitHub Repo**
2. Hubungkan akun GitHub jika belum
3. Pilih repository ini

### Langkah 4 — Set Environment Variable di Aplikasi

1. Klik service **aplikasi** (bukan MySQL)
2. Buka tab **Variables**
3. Klik **+ New Variable** dan isi:

```
DATABASE_URL = mysql+pymysql://${{MySQL.MYSQLUSER}}:${{MySQL.MYSQLPASSWORD}}@${{MySQL.MYSQLHOST}}:${{MySQL.MYSQLPORT}}/${{MySQL.MYSQLDATABASE}}
```

> Railway mendukung **reference variables** dengan sintaks `${{ServiceName.VAR}}` — ini otomatis terisi dari service MySQL.

### Langkah 5 — Generate Domain

1. Klik service aplikasi → tab **Settings**
2. Scroll ke **Networking** → klik **Generate Domain**
3. API kamu live! Buka `https://your-app.up.railway.app/docs`

### Langkah 6 — Jalankan Migrasi di Production (Opsional)

Jika menggunakan Alembic untuk migrasi, tambahkan start command:

```
alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Atau set di `railway.toml`:

```toml
[deploy]
startCommand = "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT"
```

---

## 📡 Endpoint API

| Method | Endpoint | Deskripsi |
|--------|----------|-----------|
| GET | `/` | Status server |
| GET | `/health` | Health check |
| **USERS** | | |
| POST | `/users/` | Buat user baru |
| GET | `/users/` | Daftar semua user |
| GET | `/users/{id}` | Detail user |
| PUT | `/users/{id}` | Update user |
| DELETE | `/users/{id}` | Hapus user |
| **ITEMS** | | |
| POST | `/users/{id}/items/` | Buat item untuk user |
| GET | `/items/` | Daftar semua item |
| GET | `/items/{id}` | Detail item |
| PUT | `/items/{id}` | Update item |
| DELETE | `/items/{id}` | Hapus item |

---

## 🔧 Migrasi Database (Alembic)

```bash
# Buat migrasi baru setelah ubah models.py
alembic revision --autogenerate -m "deskripsi perubahan"

# Jalankan migrasi
alembic upgrade head

# Rollback
alembic downgrade -1
```

---

## 🛠️ Tech Stack

- **FastAPI** — Framework REST API modern
- **SQLAlchemy** — ORM database
- **PyMySQL** — Driver MySQL untuk Python
- **Pydantic v2** — Validasi data
- **Alembic** — Migrasi database
- **Passlib + bcrypt** — Hashing password
- **MySQL** (lokal & production di Railway)
- **Railway** — Platform hosting

---

## ⚠️ Troubleshooting

**Error: `Access denied for user`**  
→ Cek kembali username/password MySQL di environment variable.

**Error: `Can't connect to MySQL server`**  
→ Pastikan host dan port sudah benar. Di Railway, gunakan reference variable.

**Error: `Unknown database`**  
→ Pastikan nama database sudah dibuat. Di Railway, Railway membuat database otomatis.

**Migrasi gagal di Railway**  
→ Jalankan `alembic upgrade head` manual via Railway CLI atau tambahkan ke start command.
