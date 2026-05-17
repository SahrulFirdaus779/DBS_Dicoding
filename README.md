# ZakatSight — Dokumentasi Teknis Lengkap

> Platform analitik zakat berbasis AI untuk transparansi publik dan manajemen amil.
> Dibangun oleh Tim CC26-PSU193 — Coding Camp 2026 powered by DBS Foundation.

---

## 📁 Struktur Folder Lengkap

```
DBS-Dashboard/
├── data/                              # Dataset mentah (CSV)
│   └── mustahiq dari 2021 - 2026.csv # 114.000+ baris data penerima manfaat
│
└── services/                          # Seluruh layanan aplikasi
    │
    ├── web_dashboard/                 # 🐍 Backend API (Flask)
    │   ├── app.py                     # Entry point: REST API + Cache + CORS
    │   ├── segmentation.py            # Loader model AI segmentasi donatur
    │   ├── requirements.txt           # Dependensi Python
    │   ├── fix_typo.py                # Script pembersihan data anomali
    │   ├── import_to_mongodb.py       # ETL: CSV penerimaan → MongoDB
    │   ├── import_mustahiq_to_mongodb.py  # ETL: CSV mustahiq → MongoDB
    │   ├── env/                       # Virtual environment Python (lokal)
    │   ├── models/                    # Model AI tersimpan (TensorFlow SavedModel)
    │   ├── static/                    # Aset statis CSS/JS (Flask)
    │   └── templates/                 # Template HTML (Flask/Jinja2 — legacy)
    │       ├── index.html             # Internal Dashboard (legacy, digantikan Next.js)
    │       ├── public.html            # Public Dashboard (legacy, digantikan Next.js)
    │       └── zakatsight_revised_landing.html  # Referensi desain landing page
    │
    ├── frontend/                      # ⚛️ Frontend (Next.js 16 + React + Tailwind)
    │   ├── src/app/
    │   │   ├── layout.tsx             # Root layout: font, metadata, global style
    │   │   ├── globals.css            # Design tokens: warna, font, skeleton loader
    │   │   ├── page.tsx               # Route "/" → Internal Dashboard Amil
    │   │   └── transparansi/
    │   │       └── page.tsx           # Route "/transparansi" → Public Dashboard
    │   ├── package.json               # Dependensi Node.js
    │   ├── tsconfig.json              # Konfigurasi TypeScript
    │   └── tailwind.config.ts         # Konfigurasi Tailwind CSS
    │
    ├── api_forecasting/               # 📈 Forecasting Service (FastAPI)
    │   ├── app.py                     # Entry point FastAPI
    │   ├── schemas.py                 # Skema data Pydantic
    │   ├── custom_components.py       # Komponen model kustom
    │   ├── routers/                   # Router endpoint forecasting
    │   ├── models/                    # Model ARIMA/LSTM tersimpan
    │   ├── data/                      # Data training forecasting
    │   ├── Dockerfile                 # Container image FastAPI
    │   └── requirements.txt           # Dependensi Python FastAPI
    │
    └── model_segmentation/            # 🤖 Model Segmentasi AI
        ├── ZakatSight_Segmentasi_v2.ipynb  # Jupyter notebook training
        ├── app_segmentasi_v2.py            # Aplikasi segmentasi mandiri
        ├── inference_simple.py             # Script inferensi model
        └── model_output/                   # Artefak model terlatih
```

---

## 🏗️ Arsitektur Sistem

```
┌─────────────────────────────────────────────────────────────┐
│                     CLIENT / BROWSER                        │
│              http://localhost:3000                          │
└──────────────────────┬──────────────────────────────────────┘
                       │  React Fetch (AJAX)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                 FRONTEND — Next.js 16                       │
│   Route /          → Internal Dashboard (Amil)              │
│   Route /transparansi → Public Dashboard                    │
│   Teknologi: React 19, TypeScript, Tailwind CSS v4          │
│   Port: 3000                                                │
└──────────────────────┬──────────────────────────────────────┘
                       │  REST API (CORS Enabled)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                 BACKEND — Flask API                         │
│   GET /api/dashboard?year=&month=   → KPI + Chart data      │
│   GET /api/v1/public/stats          → Data publik (cached)  │
│   GET /                             → Legacy HTML shell     │
│   GET /transparansi                 → Legacy HTML shell     │
│   Teknologi: Flask 3.0, Flask-CORS, In-Memory Cache (5 min) │
│   Port: 5000                                                │
└──────────────────────┬──────────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          ▼                         ▼
┌──────────────────┐    ┌────────────────────────────────────┐
│  MONGODB (lokal) │    │     AI SERVICE — FastAPI           │
│  DB: zakatsight  │    │   GET /forecast/tomorrow           │
│  Col: penerimaan │    │   Model: ARIMA / LSTM              │
│  Col: mustahiq   │    │   Port: 8000                       │
│  280.000+ docs   │    └────────────────────────────────────┘
└──────────────────┘
```

---

## 🗄️ Database MongoDB

### Koleksi `penerimaan`
| Field | Tipe | Keterangan |
|-------|------|------------|
| `donatur` | String | Nama donatur (dimask "Hamba Allah" di publik) |
| `nominal` | Number | Jumlah donasi dalam Rupiah |
| `program` | String | Nama program donasi |
| `channel` | String | Saluran pengumpulan (relawan/wilayah) |
| `bank` | String | Metode transfer/bank |
| `tgl` | String | Tanggal donasi (raw string) |
| `tgl_dt` | Date | Tanggal donasi (parsed, indexed) |

### Koleksi `mustahiq`
| Field | Tipe | Keterangan |
|-------|------|------------|
| `mustahiq_id` | String | ID unik penerima manfaat |
| `nama` | String | Nama penerima |
| `kategori_asnaf` | String | Kategori: Fakir, Miskin, Gharim, dll |
| `program` | String | Program yang diikuti |
| `nominal_disalurkan` | Number | Jumlah yang diterima (Rupiah) |
| `status_penyaluran` | String | "Tersalurkan" / "Pending" |
| `channel` | String | Wilayah penyaluran |
| `tgl_penyaluran` | Date | Tanggal penyaluran |

---

## 🚀 Cara Menjalankan Aplikasi

### Prasyarat
| Software | Versi Minimum | Cek Instalasi |
|----------|--------------|---------------|
| Python | 3.10+ | `python --version` |
| Node.js | 18+ | `node -v` |
| npm | 9+ | `npm -v` |
| MongoDB | 6+ | `mongod --version` |

---

### Langkah 1 — Jalankan MongoDB
Pastikan MongoDB berjalan di background. Buka terminal baru:
```bash
# Windows (jika MongoDB terinstall sebagai service, sudah otomatis)
# Atau jalankan manual:
mongod --dbpath "C:/data/db"
```

---

### Langkah 2 — Setup & Jalankan Backend (Flask API)

```bash
# Masuk ke direktori backend
cd DBS-Dashboard/services/web_dashboard

# Aktifkan virtual environment
.\env\Scripts\activate        # Windows PowerShell
# atau
source env/bin/activate       # Linux/Mac

# Jalankan server
.\env\Scripts\python.exe app.py
```

> ✅ Flask akan berjalan di: `http://127.0.0.1:5000`
>
> ⚠️ Peringatan `WARNING: Failed to load SegmentationModel` adalah **normal** jika TensorFlow belum terinstall — dashboard tetap berfungsi penuh.

---

### Langkah 3 — Jalankan Frontend (Next.js)

Buka terminal **baru** (jangan tutup terminal Flask):

```bash
# Masuk ke direktori frontend
cd DBS-Dashboard/services/frontend

# Install dependensi (hanya pertama kali)
npm install

# Jalankan development server
npm run dev
```

> ✅ Next.js akan berjalan di: `http://localhost:3000`

---

### Langkah 4 — Akses Aplikasi

| URL | Keterangan |
|-----|------------|
| `http://localhost:3000/` | Dashboard Internal (Amil) |
| `http://localhost:3000/transparansi` | Dashboard Publik (Donatur) |
| `http://127.0.0.1:5000/api/v1/public/stats` | REST API publik (JSON) |
| `http://127.0.0.1:5000/api/dashboard?year=2026&month=5` | REST API internal (JSON, filter) |

---

### (Opsional) Langkah 5 — Import Data ke MongoDB

Jika database belum berisi data, jalankan script ETL:

```bash
cd DBS-Dashboard/services/web_dashboard

# Import data penerimaan donasi
.\env\Scripts\python.exe import_to_mongodb.py

# Import data mustahiq (penerima manfaat)
.\env\Scripts\python.exe import_mustahiq_to_mongodb.py
```

---

## ⬇️ Export Data dari MongoDB (untuk dibagikan via GitHub)

Jika Anda sudah punya data di MongoDB dan ingin mengirim snapshot ke rekan (misalnya lewat GitHub), Anda bisa export koleksi MongoDB ke folder `data/raw/mongodb_export/` dalam format **JSONL**.

### Export (Windows)

Jalankan dari root project:

```bat
export_data.bat
```

Jika MongoDB Anda tidak di `localhost:27017` atau nama database berbeda, set environment variable dulu (PowerShell):

```powershell
$env:MONGO_URI = "mongodb://localhost:27017/"
$env:MONGO_DB  = "zakatsight"
./export_data.bat
```

Output default:
- `data/raw/mongodb_export/penerimaan.jsonl`
- `data/raw/mongodb_export/mustahiq.jsonl`
- `data/raw/mongodb_export/penyaluran.jsonl`
- `data/raw/mongodb_export/export_metadata.json`

### Re-import di komputer rekan (opsi cepat)

Jika rekan Anda punya MongoDB Database Tools (`mongoimport`), contoh:

```bash
mongoimport --db zakatsight --collection penerimaan --drop --file data/raw/mongodb_export/penerimaan.jsonl
mongoimport --db zakatsight --collection mustahiq    --drop --file data/raw/mongodb_export/mustahiq.jsonl
mongoimport --db zakatsight --collection penyaluran  --drop --file data/raw/mongodb_export/penyaluran.jsonl
```

> Catatan: Pastikan Anda mempertimbangkan ukuran file & privasi data sebelum commit ke GitHub.

---

## 🔌 API Reference

### `GET /api/v1/public/stats`
Data ringkasan publik (di-cache 5 menit).

**Response:**
```json
{
  "total_terkumpul": 28700000000,
  "total_terkumpul_str": "Rp 28.7M",
  "total_disalurkan": 24000000000,
  "total_disalurkan_str": "Rp 24.0M",
  "progress_percent": 84,
  "keluarga_terbantu": 114523,
  "program_aktif": 12,
  "titik_wilayah": 142,
  "distribusi_labels": ["Fakir Miskin", "Amil", "Gharim", ...],
  "distribusi_data": [45.2, 12.5, 8.3, ...],
  "latest_donations": [
    { "donatur": "Hamba Allah", "nominal": "Rp 250rb", "program": "Zakat Maal", "waktu": "17 Mei 2026" }
  ]
}
```

---

### `GET /api/dashboard?year=&month=`
Data dashboard internal dengan filter tahun/bulan. Di-cache 5 menit per kombinasi filter.

**Query Parameters:**

| Parameter | Nilai | Default |
|-----------|-------|---------|
| `year` | `2021`–`2026` atau `all` | `all` |
| `month` | `1`–`12` atau `all` | `all` |

**Response (ringkasan):**
```json
{
  "total_nominal_str": "Rp 28.7M",
  "jumlah_transaksi": 60489,
  "donatur_unik": 25848,
  "rata_rata_donasi_str": "Rp 474rb",
  "bulan_tertinggi_nama": "Mar 2026",
  "bulan_tertinggi_val": "Rp 4.2M",
  "monthly_labels": ["2021", "2022", "2023", ...],
  "monthly_data": [2.1, 3.4, 5.2, ...],
  "channel_labels": ["Al Araf MS", "Sukmajaya", ...],
  "channel_data": [3.56, 3.47, ...],
  "bank_labels": ["BSI Pusat", "Sahabat Berbagi", ...],
  "bank_data": [74.4, 8.5, ...],
  "latest_txns": [...]
}
```

---

## 🛠️ Tech Stack

| Layer | Teknologi | Versi |
|-------|-----------|-------|
| **Frontend Framework** | Next.js (React) | 16.2+ |
| **Bahasa Frontend** | TypeScript | 5+ |
| **Styling** | Tailwind CSS | v4 |
| **Charting** | Chart.js | 4.4+ |
| **Font** | Lora (serif) + Plus Jakarta Sans | Google Fonts |
| **Backend Framework** | Flask | 3.0.3 |
| **Cross-Origin** | Flask-CORS | 6.0+ |
| **Database** | MongoDB | 6+ |
| **ODM** | PyMongo | 4.17+ |
| **Data Processing** | Pandas | 2.2.1 |
| **AI — Segmentasi** | TensorFlow / scikit-learn | 2.15+ / 1.4+ |
| **AI — Forecasting** | FastAPI + ARIMA | 1.0+ |
| **Caching** | In-Memory Python dict (TTL 5 min) | — |

---

## ⚙️ Konfigurasi Penting

### Cache TTL (`app.py`)
```python
CACHE_TTL = 300  # 5 menit dalam detik
```
Ubah nilai ini untuk mengatur seberapa sering data direfresh dari MongoDB.

### MongoDB URI (`app.py`)
```python
MONGO_URI = "mongodb://localhost:27017/"
DB_NAME   = "zakatsight"
```

### Forecasting API (`app.py`)
```python
FORECAST_URL = "http://localhost:8000/forecast/tomorrow"
```
Uncomment dan jalankan `services/api_forecasting/app.py` untuk mengaktifkan prediksi live.

---

## 🔄 Alur Pengembangan (Development Flow)

```
Perubahan data CSV
       ↓
Jalankan ETL script (import_to_mongodb.py)
       ↓
Data masuk MongoDB
       ↓
Flask API baca dari MongoDB (di-cache)
       ↓
Next.js fetch dari Flask API
       ↓
React render ke browser
```

---

## 📌 Catatan Penting

> ⚠️ **Jangan gunakan `python app.py` langsung.** Selalu gunakan virtual env:
> `.\env\Scripts\python.exe app.py`

> ⚠️ **Cache perlu di-reset** jika ada perubahan data besar di MongoDB: cukup **restart Flask**.

> ℹ️ **TensorFlow opsional**: Model AI segmentasi hanya aktif jika TensorFlow 2.15 terinstall. Dashboard berfungsi normal tanpanya.

> ℹ️ **Dua terminal wajib berjalan bersamaan**: Flask (port 5000) + Next.js (port 3000).
