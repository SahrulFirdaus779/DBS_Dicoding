# ZakatSight Forecast API V3

REST API untuk forecasting penerimaan zakat harian. Model: **LSTM(64) + Custom TemporalAttention** dengan 21 features (calendar, lag, rolling, Ramadan).

**Performance**: MASE 2.23 ± 0.48, R² +0.34, Direction Accuracy 54.8% (multi-seed n=5).

## Struktur

```
fastapi_v3/
├── app.py                          # FastAPI entry point
├── custom_components.py            # TemporalAttentionLayer + AsymmetricHuberLoss
├── schemas.py                      # Pydantic request/response models
├── routers/
│   └── forecast.py                 # Forecast endpoints
├── lib/
│   ├── model_loader.py             # Cached model + scaler + history loader
│   └── preprocessing.py            # Feature engineering at inference
├── models/
│   ├── forecast_lstm_v3.keras      # Trained model (26K params)
│   ├── forecast_scaler.pkl         # Scaler bundle (MinMaxScaler + metadata)
│   └── forecast_metadata.json      # Model metadata
├── data/
│   ├── daily_timeseries.csv        # Historical data (1945 days, 2020-12-17 → 2026-04-14)
│   └── ramadan_multiplier_reference.csv  # 30 days × multiplier
├── tests/
│   └── test_e2e.py                 # End-to-end smoke tests
├── requirements.txt
├── Dockerfile
└── README.md
```

## Quick Start

### Install & run lokal

```bash
# Install dependencies
pip install -r requirements.txt

# Run server (cold start ~30 detik karena TF model loading)
uvicorn app:app --host 0.0.0.0 --port 8000

# Test health
curl http://localhost:8000/health

# Buka interactive API docs
open http://localhost:8000/docs
```

### Smoke test

```bash
python tests/test_e2e.py
```

## API Endpoints

### `POST /forecast/tomorrow`

Predict 1 hari. Default = hari setelah history terakhir (April 15, 2026 di dataset current).

**Request body:**
```json
{
  "target_date": "2026-04-20"   // optional; default: latest_history + 1 day
}
```

**Response:**
```json
{
  "forecast": {
    "date": "2026-04-20",
    "predicted_rupiah": 16886531.30,
    "predicted_log": 16.642,
    "is_ramadan": false,
    "ramadan_day_index": 0,
    "is_weekend": true
  },
  "model_version": "v3",
  "note": null
}
```

### `POST /forecast/range`

Predict N hari berturutan secara **autoregressive** (prediksi day-1 → input untuk day-2, dst). Error compounding mulai signifikan setelah ~14 hari.

**Request body:**
```json
{
  "start_date": "2026-04-15",   // optional
  "n_days": 7                    // 1-90
}
```

**Response:**
```json
{
  "forecasts": [/* array of DailyForecast */],
  "n_days": 7,
  "total_predicted_rupiah": 117412368.5,
  "avg_daily_rupiah": 16773195.5,
  "warning": null
}
```

### `GET /forecast/historical?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`

Fetch actual historical values dari range tanggal — untuk dashboard prediction-vs-actual comparison.

### `GET /model/info`

Metadata model V3: arsitektur, feature_cols, multi_seed_summary, final_metrics, history_range.

### `GET /health`

Health check — verify model loaded + history available.

## Deployment

### Docker

```bash
# Build image
docker build -t zakatsight-forecast-v3 .

# Run container
docker run -p 8000:8000 zakatsight-forecast-v3

# Test
curl http://localhost:8000/health
```

### Cloud (Railway / Render / Fly.io)

Karena image perlu TensorFlow (~500 MB), recommended platform yang support 1+ GB image:
- **Railway**: connect Github repo, auto-detect Dockerfile, deploy
- **Render**: similar, free tier OK untuk demo
- **Fly.io**: lebih advanced tapi flexibility tinggi

Untuk production load, set workers ke 2-4:
```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
```

## Catatan teknis penting

### 1. Inference butuh historical context yang panjang

Model V3 pakai `lag_365` (donasi 1 tahun lalu) sebagai feature. Untuk predict tanggal T:
- Window 30 hari [T-30, T-1] sebagai input
- Setiap hari dalam window perlu lag_365 → butuh data dari T-395+ ke T-1
- Total: **minimal 395 hari history** sebelum tanggal yang di-predict

`daily_timeseries.csv` di repo current punya 1945 hari, jadi bisa predict apa saja sampai April 2027 (lag_365 masih ke-cover).

### 2. Log transform di feature engineering

Training pipeline apply `log1p()` ke 3 count features (`n_transactions`, `unique_donors`, `new_donors`) sebelum scaling. Inference HARUS replicate ini. Already handled di `lib/preprocessing.py`.

### 3. Custom Components harus di-register saat load model

`TemporalAttentionLayer` dan `AsymmetricHuberLoss` adalah custom components dari training. Saat `tf.keras.models.load_model()`, harus pass `custom_objects=CUSTOM_OBJECTS` (dari `custom_components.py`).

### 4. Sklearn version warning bisa di-ignore

`forecast_scaler.pkl` di-save dengan sklearn 1.6.1, runtime mungkin pakai 1.8.0. MinMaxScaler API stable, tidak ada breaking change. Warning aman di-ignore. Untuk production cleanliness, pin sklearn==1.6.1 di `requirements.txt`.

### 5. Update data history

Setelah ada data baru (misalnya end-of-month update):

```bash
# 1. Replace daily_timeseries.csv dengan data baru
cp /path/to/new_daily_timeseries.csv data/daily_timeseries.csv

# 2. Restart server (cache invalidates on restart)
# Atau panggil reload internally:
python -c "from lib.model_loader import reload_bundle; reload_bundle()"
```

## Limitations & Future Work

| Limitation | Impact | Mitigation |
|---|---|---|
| MASE 2.23 > 1.0 | Model masih lebih buruk dari naive baseline | Future: multiplicative decomposition Ramadan/non-Ramadan |
| Direction Accuracy 54.8% | Cuma slightly better than random | Cuma agregat, single-day prediction unreliable |
| `days_since_start` extrapolation | Inference value > training max → out-of-distribution | Capped behavior, gradual degradation |
| Autoregressive error compounding | n_days > 14 unreliable | Warning di-return saat n_days > 14 |
| Cold start 30s | First request slow | Pre-load di startup (sudah implemented) |
| Single seed (best val) | Production single seed may differ | Multi-seed averaging untuk ensemble (future) |

## Development workflow untuk Putra

### Update model V3 (e.g., re-train atau iterate)

1. Run notebook `05_forecasting_v3_putra.ipynb` di Colab
2. Download artifacts ke `models/`:
   - `forecast_lstm_v3.keras`
   - `forecast_scaler.pkl`
   - `forecast_metadata.json`
3. Test load: `python tests/test_e2e.py`
4. Restart server

### Tambah endpoint baru

1. Tambah Pydantic schema di `schemas.py`
2. Tambah endpoint function di `routers/forecast.py`
3. Update `tests/test_e2e.py` dengan test case baru
4. Update README endpoint section

### Performance profiling

- TF model inference single-day: ~50-100ms
- Window construction (with FE): ~200-500ms (pandas ops)
- Total /forecast/tomorrow: ~300-600ms per request
- /forecast/range (n=7): ~2-4 detik (autoregressive iteration)

## Maintenance checklist

- [ ] `daily_timeseries.csv` updated bulanan dengan data baru
- [ ] `ramadan_multiplier_reference.csv` regenerate setiap Ramadan baru selesai (auto-include in 02_feature_engineering.ipynb section 8)
- [ ] Model re-train tahunan (atau ketika MASE production drift > 20% dari training MASE)
- [ ] Health check monitoring dengan downtime alert
- [ ] Log forecasting requests untuk audit trail (extension future)

## Contact

ZakatSight Capstone Coding Camp 2026 powered by DBS Foundation  
Tim AI: Putra (forecasting) — putra@example.com  
Tim DS: Lemeow (data + handoff) — lemeow@example.com
