"""
ZakatSight — FastAPI Segmentasi Donor v2
CC26-PSU193 | AI Engineer: Hasna Minatul Mardiah

Changelog v2:
  - FEATURE_COLS: hapus R_score, F_score, M_score (fix label leakage)
  - Tambah Pydantic validator: pct_* harus sum ≈ 1.0 (±0.05)
  - Response /predict/segment sekarang include 'insight' per segmen
  - Endpoint baru: GET /segments/insight/{segment}
  - Model path diupdate ke v2 artifacts

Endpoint:
  GET  /               → info API
  GET  /health         → status model, scaler, label encoder
  POST /predict/segment      → prediksi segmen 1 donor (+ insight)
  POST /predict/segment/batch → prediksi segmen banyak donor sekaligus
  GET  /segments        → daftar segmen + deskripsi singkat
  GET  /segments/insight/{segment} → detail insight & rekomendasi aksi
  GET  /docs            → Swagger UI (otomatis)

Cara run:
  pip install fastapi uvicorn tensorflow scikit-learn joblib pandas numpy
  uvicorn app_segmentasi_v2:app --reload --port 8001
  → buka http://localhost:8001/docs
"""

from __future__ import annotations

import datetime
import os
from pathlib import Path
from typing import Dict, List, Optional

import joblib
import numpy as np
import tensorflow as tf
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, field_validator, model_validator

# ============================================================
# Custom Objects — identik dengan definisi di notebook v2
# ============================================================

class DonorAttentionLayer(tf.keras.layers.Layer):
    """Custom Layer: Feature Attention untuk profil donor."""

    def __init__(self, units: int, dropout_rate: float = 0.3, **kwargs):
        super().__init__(**kwargs)
        self.units        = units
        self.dropout_rate = dropout_rate

    def build(self, input_shape):
        d  = input_shape[-1]
        gi = tf.keras.initializers.GlorotUniform()
        zi = tf.keras.initializers.Zeros()
        self.W_a = self.add_weight(name='W_a', shape=(d, 1),          dtype=tf.float32, initializer=gi, trainable=True)
        self.b_a = self.add_weight(name='b_a', shape=(1,),            dtype=tf.float32, initializer=zi, trainable=True)
        self.W_o = self.add_weight(name='W_o', shape=(d, self.units), dtype=tf.float32, initializer=gi, trainable=True)
        self.b_o = self.add_weight(name='b_o', shape=(self.units,),   dtype=tf.float32, initializer=zi, trainable=True)
        self.drop = tf.keras.layers.Dropout(self.dropout_rate)
        super().build(input_shape)

    def call(self, x, training=False):
        attn  = tf.nn.sigmoid(tf.matmul(x, self.W_a) + self.b_a)
        gated = self.drop(x * attn, training=training)
        return tf.nn.relu(tf.matmul(gated, self.W_o) + self.b_o)

    def get_config(self):
        cfg = super().get_config()
        cfg.update({'units': self.units, 'dropout_rate': self.dropout_rate})
        return cfg


class WeightedFocalLoss(tf.keras.losses.Loss):
    """Custom Loss: Focal Loss + class weighting untuk data imbalanced."""

    def __init__(self, gamma=2.0, class_weights=None, **kwargs):
        super().__init__(**kwargs)
        self.gamma         = gamma
        self.class_weights = class_weights

    def call(self, y_true, y_pred):
        y_pred = tf.clip_by_value(y_pred, 1e-7, 1 - 1e-7)
        ce     = -y_true * tf.math.log(y_pred)
        p_t    = tf.reduce_sum(y_true * y_pred, axis=-1, keepdims=True)
        loss   = tf.pow(1 - p_t, self.gamma) * ce
        if self.class_weights is not None:
            cw   = tf.constant(self.class_weights, dtype=tf.float32)
            sw   = tf.reduce_sum(y_true * cw, axis=-1, keepdims=True)
            loss = loss * sw
        return tf.reduce_mean(tf.reduce_sum(loss, axis=-1))

    def get_config(self):
        cfg = super().get_config()
        cfg.update({'gamma': self.gamma, 'class_weights': self.class_weights})
        return cfg


CUSTOM_OBJECTS = {
    'DonorAttentionLayer': DonorAttentionLayer,
    'WeightedFocalLoss'  : WeightedFocalLoss,
}

# ============================================================
# Feature columns v2 — TANPA R_score, F_score, M_score
# Ref: segmentasi_perbaikan.md Step 1
#
# ALASAN PENGHAPUSAN R/F/M SCORES:
# R_score, F_score, M_score adalah quartile encoding dari recency_days,
# frequency, dan monetary_total — ketiganya dipakai langsung untuk
# membentuk segment_rule_based (target label). Menyertakan scores
# sebagai input = label leakage: model hanya perlu lookup score,
# bukan belajar pola perilaku.
#
# 23 fitur (turun dari 26)
# ============================================================
FEATURE_COLS = [
    # RFM core (continuous — bukan quartile score)
    'recency_days', 'log_frequency', 'log_monetary_total',
    'log_monetary_avg', 'log_monetary_max', 'log_monetary_std',
    # Tenure & activity
    'tenure_days', 'n_unique_programs', 'n_unique_channels',
    # Behavioral — program preference
    'pct_zakat', 'pct_infaq', 'pct_kemanusiaan', 'pct_pendidikan',
    'pct_sedekah', 'pct_wakaf', 'pct_yatim', 'pct_qurban', 'pct_other',
    # Timing patterns
    'pct_weekend', 'pct_ramadan',
    # Inter-arrival
    'inter_arrival_avg_days', 'inter_arrival_std_days',
    # Binary
    'has_real_phone',
]

# Fitur raw yang perlu di-log-transform sebelum masuk ke model
RAW_TO_LOG = [
    'monetary_total', 'monetary_avg', 'monetary_max',
    'monetary_min', 'monetary_median', 'monetary_std', 'frequency',
]

# ============================================================
# Segment descriptions & insights
# ============================================================
SEGMENT_DESCRIPTIONS = {
    'champions'         : 'Donor paling aktif dan loyal. Sering donasi, nominal besar, baru-baru ini donasi.',
    'loyal'             : 'Donor setia dengan frekuensi tinggi dan nominal konsisten.',
    'potential_loyalist': 'Donor baru atau occasional yang menunjukkan potensi menjadi loyal.',
    'at_risk'           : 'Donor yang dulu aktif namun sudah lama tidak donasi. Perlu re-engagement.',
    'cant_lose'         : 'Donor dengan nominal besar yang mulai tidak aktif. Prioritas retensi tinggi.',
    'hibernating'       : 'Donor yang sudah sangat lama tidak donasi dan frekuensinya rendah.',
    'new_donors'        : 'Donor baru, belum bisa diprediksi loyalitasnya.',
}

SEGMENT_INSIGHTS: Dict[str, dict] = {
    'champions': {
        'emoji'         : '🏆',
        'karakteristik' : 'Baru saja donasi, sering donasi, nominal besar. Pilar utama penerimaan.',
        'risiko'        : 'Rendah — perlu dipertahankan dengan engagement personal.',
        'rekomendasi'   : [
            'Berikan apresiasi eksklusif (thank-you letter, laporan dampak personal)',
            'Undang ke program VIP / kunjungan lapangan',
            'Tawarkan wakaf atau program jangka panjang',
            'Jadikan brand ambassador / referral program',
        ],
    },
    'loyal': {
        'emoji'         : '💛',
        'karakteristik' : 'Donasi rutin meski nominal tidak selalu besar. Bisa diprediksi.',
        'risiko'        : 'Rendah — jaga konsistensi komunikasi.',
        'rekomendasi'   : [
            'Program loyalitas / reward milestone (misal: donasi ke-10, ke-25)',
            'Upsell ke program dengan nilai lebih tinggi',
            'Edukasi tentang program wakaf atau zakat produktif',
            'Survey kepuasan untuk mempertahankan engagement',
        ],
    },
    'potential_loyalist': {
        'emoji'         : '🌱',
        'karakteristik' : 'Mungkin donor relatif baru yang mulai membangun kebiasaan donasi.',
        'risiko'        : 'Sedang — jika tidak diaktivasi bisa drift ke hibernating.',
        'rekomendasi'   : [
            'Onboarding campaign: cerita dampak donasi mereka sejauh ini',
            'Dorong donasi rutin / langganan bulanan',
            'Tawarkan program yang sesuai preferensi program mereka',
            'Follow-up personal setelah donasi pertama',
        ],
    },
    'at_risk': {
        'emoji'         : '⚠️',
        'karakteristik' : 'Historis frekuensi & monetary cukup baik, tapi sudah lama tidak donasi.',
        'risiko'        : 'Tinggi — prioritas re-engagement sebelum fully churn.',
        'rekomendasi'   : [
            'Win-back campaign dengan pesan personal & urgensi',
            'Tunjukkan dampak donasi sebelumnya yang masih berlanjut',
            'Tawarkan kemudahan: autodebet, e-wallet, QR code baru',
            'Kirim pengingat di momen relevan (Ramadan, akhir tahun)',
        ],
    },
    'cant_lose': {
        'emoji'         : '🚨',
        'karakteristik' : 'Pernah donasi nominal sangat besar, tapi recency sudah lama.',
        'risiko'        : 'Sangat Tinggi — kehilangan 1 donor segmen ini = kehilangan nilai besar.',
        'rekomendasi'   : [
            'PRIORITAS TERTINGGI — outreach personal dari leadership',
            'Laporan dampak khusus atas kontribusi besar mereka',
            'Undang ke event eksklusif / program strategis',
            'Investigasi penyebab berhenti (survei singkat, call center)',
        ],
    },
    'hibernating': {
        'emoji'         : '😴',
        'karakteristik' : 'Recency sangat tinggi, frekuensi rendah. Sulit diaktifkan kembali.',
        'risiko'        : 'Sangat Tinggi untuk churn — tapi volume besar, ada potensi reaktivasi massal.',
        'rekomendasi'   : [
            'Low-cost reactivation: email campaign, SMS blast di Ramadan',
            'Tidak worthwhile untuk outreach personal — gunakan otomasi',
            'Jika teraktivasi, pindahkan ke potential_loyalist flow',
            'Pertimbangkan unsubscribe jika email bounce rate tinggi',
        ],
    },
    'new_donors': {
        'emoji'         : '📦',
        'karakteristik' : 'Tenure pendek, frekuensi sangat rendah (sering 1x). Periode kritis.',
        'risiko'        : 'Sedang — 30-hari pertama menentukan retensi jangka panjang.',
        'rekomendasi'   : [
            'Welcome campaign: cerita organisasi, dampak program',
            'Dorong donasi ke-2 dalam 30 hari pertama (kritis untuk habit)',
            'Tanyakan preferensi program — personalisasi sejak awal',
            'Monitor konversi ke potential_loyalist dalam 90 hari',
        ],
    },
}

# ============================================================
# Model & Bundle Loading (lazy, thread-safe)
# ============================================================

MODEL_PATH   = Path(os.getenv('MODEL_PATH',   'model_output/zakatsight_segmentasi_v2.keras'))
SCALER_PATH  = Path(os.getenv('SCALER_PATH',  'model_output/scaler_segmentasi_v2.pkl'))
ENCODER_PATH = Path(os.getenv('ENCODER_PATH', 'model_output/label_encoder_v2.pkl'))

_model: Optional[tf.keras.Model] = None
_scaler   = None
_encoder  = None


def get_model() -> tf.keras.Model:
    global _model
    if _model is None:
        if not MODEL_PATH.exists():
            raise RuntimeError(
                f'Model tidak ditemukan di {MODEL_PATH}. '
                'Jalankan notebook training v2 terlebih dahulu.'
            )
        _model = tf.keras.models.load_model(str(MODEL_PATH), custom_objects=CUSTOM_OBJECTS)
    return _model


def get_scaler():
    global _scaler
    if _scaler is None:
        if not SCALER_PATH.exists():
            raise RuntimeError(f'Scaler tidak ditemukan di {SCALER_PATH}.')
        _scaler = joblib.load(str(SCALER_PATH))
    return _scaler


def get_encoder():
    global _encoder
    if _encoder is None:
        if not ENCODER_PATH.exists():
            raise RuntimeError(f'LabelEncoder tidak ditemukan di {ENCODER_PATH}.')
        _encoder = joblib.load(str(ENCODER_PATH))
    return _encoder


# ============================================================
# Helper: donor_data dict → feature vector siap dipakai model
# ============================================================

def build_feature_vector(donor_data: dict) -> np.ndarray:
    """
    Konversi raw donor dict → feature vector (1, n_features) yang sudah di-scale.

    Step:
    1. Log-transform fitur skewed (monetary_*, frequency)
    2. Ambil nilai tiap FEATURE_COLS (default 0 jika tidak ada)
    3. Scale dengan scaler yang sudah di-fit di training

    Note v2: FEATURE_COLS tidak lagi menyertakan R_score, F_score, M_score.
    Jika dict input masih menyertakannya, diabaikan saja.
    """
    d = dict(donor_data)

    for col in RAW_TO_LOG:
        if col in d:
            d[f'log_{col}'] = float(np.log1p(d[col]))

    feat_vec = np.array(
        [[d.get(c, 0.0) for c in FEATURE_COLS]],
        dtype=np.float32
    )

    scaler  = get_scaler()
    feat_sc = scaler.transform(feat_vec).astype(np.float32)
    return feat_sc


# ============================================================
# Pydantic Models
# ============================================================

class DonorFeatures(BaseModel):
    """
    Fitur perilaku donor untuk prediksi segmen.

    v2: R_score, F_score, M_score TIDAK LAGI DIPERLUKAN.
    API akan mengabaikan field tersebut jika dikirim (backward compat).

    Validasi:
    - pct_zakat + pct_infaq + ... + pct_other harus = 1.0 (±0.05)
    """
    # RFM core (raw — API yang lakukan log-transform)
    recency_days      : float = Field(..., ge=0,   description='Hari sejak donasi terakhir')
    frequency         : float = Field(..., ge=0,   description='Total jumlah transaksi')
    monetary_total    : float = Field(..., ge=0,   description='Total nominal donasi (Rp)')
    monetary_avg      : float = Field(0.0, ge=0,   description='Rata-rata nominal per transaksi (Rp)')
    monetary_max      : float = Field(0.0, ge=0,   description='Nominal terbesar (Rp)')
    monetary_min      : float = Field(0.0, ge=0,   description='Nominal terkecil (Rp)')
    monetary_median   : float = Field(0.0, ge=0,   description='Median nominal (Rp)')
    monetary_std      : float = Field(0.0, ge=0,   description='Standar deviasi nominal (Rp)')

    # Tenure & activity
    tenure_days       : float = Field(0.0, ge=0,   description='Jumlah hari sejak donasi pertama')
    n_unique_programs : int   = Field(0,   ge=0,   description='Jumlah program unik yang didukung')
    n_unique_channels : int   = Field(0,   ge=0,   description='Jumlah channel donasi unik')

    # Program preference (pct_* harus sum ≈ 1.0)
    pct_zakat         : float = Field(0.0, ge=0, le=1, description='Proporsi donasi ke Zakat')
    pct_infaq         : float = Field(0.0, ge=0, le=1, description='Proporsi donasi ke Infaq')
    pct_kemanusiaan   : float = Field(0.0, ge=0, le=1, description='Proporsi donasi ke Kemanusiaan')
    pct_pendidikan    : float = Field(0.0, ge=0, le=1, description='Proporsi donasi ke Pendidikan')
    pct_sedekah       : float = Field(0.0, ge=0, le=1, description='Proporsi donasi ke Sedekah')
    pct_wakaf         : float = Field(0.0, ge=0, le=1, description='Proporsi donasi ke Wakaf')
    pct_yatim         : float = Field(0.0, ge=0, le=1, description='Proporsi donasi ke Yatim')
    pct_qurban        : float = Field(0.0, ge=0, le=1, description='Proporsi donasi ke Qurban')
    pct_other         : float = Field(0.0, ge=0, le=1, description='Proporsi donasi ke program lain')

    # Timing
    pct_weekend           : float = Field(0.0, ge=0, le=1, description='Proporsi transaksi di akhir pekan')
    pct_ramadan           : float = Field(0.0, ge=0, le=1, description='Proporsi transaksi di bulan Ramadan')

    # Inter-arrival
    inter_arrival_avg_days: float = Field(0.0, ge=0, description='Rata-rata hari antar transaksi')
    inter_arrival_std_days: float = Field(0.0, ge=0, description='Std dev hari antar transaksi')

    # Binary
    has_real_phone: int = Field(0, ge=0, le=1, description='1 jika donor memiliki nomor HP valid')

    # Backward compatibility: field lama boleh dikirim tapi diabaikan
    R_score: Optional[float] = Field(None, description='[Deprecated v2] Diabaikan — hapus dari integrasi Anda')
    F_score: Optional[float] = Field(None, description='[Deprecated v2] Diabaikan — hapus dari integrasi Anda')
    M_score: Optional[float] = Field(None, description='[Deprecated v2] Diabaikan — hapus dari integrasi Anda')

    # ============================================================
    # Pydantic validator: pct_* harus sum ≈ 1.0 (±0.05)
    # Ref: segmentasi_perbaikan.md Step 5
    # ============================================================
    @model_validator(mode='after')
    def pct_must_sum_to_one(self) -> 'DonorFeatures':
        pct_fields = [
            'pct_zakat', 'pct_infaq', 'pct_kemanusiaan', 'pct_pendidikan',
            'pct_sedekah', 'pct_wakaf', 'pct_yatim', 'pct_qurban', 'pct_other',
        ]
        pct_sum = sum(getattr(self, f) for f in pct_fields)
        # Toleransi ±0.05 untuk floating point error dan pembulatan
        if pct_sum > 0 and not (0.95 <= pct_sum <= 1.05):
            raise ValueError(
                f'Jumlah semua pct_* harus ≈ 1.0 (toleransi ±0.05). '
                f'Didapat: {pct_sum:.4f}. Periksa nilai pct_zakat, pct_infaq, dst.'
            )
        return self


class SegmentInsight(BaseModel):
    """Insight & rekomendasi aksi untuk satu segmen."""
    emoji         : str
    karakteristik : str
    risiko        : str
    rekomendasi   : List[str]


class SegmentPrediction(BaseModel):
    """Response prediksi segmen untuk satu donor."""
    segment           : str             = Field(..., description='Nama segmen terprediksi')
    confidence        : float           = Field(..., description='Probabilitas segmen terprediksi (0-1)')
    all_probabilities : Dict[str, float]= Field(..., description='Probabilitas semua segmen')
    description       : str             = Field(..., description='Deskripsi singkat segmen')
    insight           : SegmentInsight  = Field(..., description='Insight & rekomendasi aksi per segmen')
    inference_time_ms : float           = Field(..., description='Waktu inferensi (ms)')
    deprecated_fields : Optional[List[str]] = Field(
        None,
        description='Field yang dikirim tapi sudah deprecated di v2'
    )


class BatchRequest(BaseModel):
    """Request untuk prediksi banyak donor sekaligus."""
    donors: List[DonorFeatures] = Field(
        ..., min_length=1, max_length=500,
        description='List donor (maks 500 per request)'
    )


class BatchPrediction(BaseModel):
    """Response batch prediksi."""
    results           : List[SegmentPrediction]
    total_donors      : int
    inference_time_ms : float


class HealthResponse(BaseModel):
    status        : str
    model_loaded  : bool
    scaler_loaded : bool
    encoder_loaded: bool
    model_path    : str
    n_features    : int
    n_classes     : int
    model_version : str
    timestamp     : str


class SegmentInfo(BaseModel):
    segment     : str
    description : str
    insight     : SegmentInsight


# ============================================================
# Helper: single inference
# ============================================================

def _infer_one(donor: DonorFeatures) -> SegmentPrediction:
    t0      = datetime.datetime.now()
    model   = get_model()
    encoder = get_encoder()

    donor_dict = donor.model_dump(exclude={'R_score', 'F_score', 'M_score', 'deprecated_fields'})
    feat_sc    = build_feature_vector(donor_dict)
    probs      = model.predict(feat_sc, verbose=0)[0]
    idx        = int(np.argmax(probs))
    segment    = encoder.classes_[idx]

    elapsed = (datetime.datetime.now() - t0).total_seconds() * 1000

    # Deteksi field deprecated yang masih dikirim
    deprecated = []
    for f in ['R_score', 'F_score', 'M_score']:
        if getattr(donor, f, None) is not None:
            deprecated.append(f)

    insight_data = SEGMENT_INSIGHTS.get(segment, {
        'emoji': '📌', 'karakteristik': '', 'risiko': '', 'rekomendasi': []
    })

    return SegmentPrediction(
        segment           = segment,
        confidence        = round(float(probs[idx]), 4),
        all_probabilities = {
            encoder.classes_[i]: round(float(probs[i]), 4)
            for i in range(len(encoder.classes_))
        },
        description       = SEGMENT_DESCRIPTIONS.get(segment, ''),
        insight           = SegmentInsight(**insight_data),
        inference_time_ms = round(elapsed, 2),
        deprecated_fields = deprecated if deprecated else None,
    )


# ============================================================
# FastAPI App
# ============================================================

app = FastAPI(
    title='ZakatSight Segmentasi Donor API v2',
    description=(
        'REST API untuk memprediksi segmen donor berdasarkan perilaku donasi '
        'menggunakan model DonorAttentionLayer + Residual Dense + WeightedFocalLoss.\n\n'
        '**v2 Changes:**\n'
        '- Hapus R_score/F_score/M_score dari input (fix label leakage)\n'
        '- Tambah Pydantic validator untuk pct_* sum\n'
        '- Response sekarang include insight & rekomendasi aksi per segmen\n\n'
        '**Project:** CC26-PSU193 ZakatSight\n'
        '**AI Engineer:** Hasna Minatul Mardiah'
    ),
    version='2.0.0',
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)


# ============================================================
# Endpoints
# ============================================================

@app.get('/', tags=['Info'])
def root():
    """Informasi umum API."""
    return {
        'name'     : 'ZakatSight Segmentasi Donor API',
        'version'  : '2.0.0',
        'project'  : 'CC26-PSU193',
        'engineer' : 'Hasna Minatul Mardiah',
        'model'    : 'DonorAttentionLayer + Residual Dense + WeightedFocalLoss',
        'changes_v2': [
            'Hapus R_score, F_score, M_score dari FEATURE_COLS (fix label leakage)',
            'Pydantic validator: pct_* harus sum ≈ 1.0',
            'Response include insight & rekomendasi aksi per segmen',
        ],
        'endpoints': {
            'POST /predict/segment'           : 'Prediksi segmen 1 donor (+ insight)',
            'POST /predict/segment/batch'     : 'Prediksi segmen banyak donor (maks 500)',
            'GET  /segments'                  : 'Daftar segmen + deskripsi + insight',
            'GET  /segments/insight/{segment}': 'Detail insight & rekomendasi per segmen',
            'GET  /health'                    : 'Status model',
            'GET  /docs'                      : 'Swagger UI interaktif',
        },
    }


@app.get('/health', response_model=HealthResponse, tags=['Info'])
def health():
    """Health check — cek apakah model dan artefak siap dipakai."""
    try:
        enc = get_encoder()
        n_classes = len(enc.classes_)
    except Exception:
        n_classes = 0

    return HealthResponse(
        status         = 'ok' if all([MODEL_PATH.exists(), SCALER_PATH.exists(), ENCODER_PATH.exists()]) else 'degraded',
        model_loaded   = _model   is not None,
        scaler_loaded  = _scaler  is not None,
        encoder_loaded = _encoder is not None,
        model_path     = str(MODEL_PATH.resolve()),
        n_features     = len(FEATURE_COLS),
        n_classes      = n_classes,
        model_version  = '2.0.0',
        timestamp      = datetime.datetime.now().isoformat(),
    )


@app.get('/segments', response_model=List[SegmentInfo], tags=['Info'])
def list_segments():
    """Daftar semua segmen donor beserta deskripsi dan insight singkat."""
    results = []
    for seg, desc in SEGMENT_DESCRIPTIONS.items():
        insight_data = SEGMENT_INSIGHTS.get(seg, {
            'emoji': '📌', 'karakteristik': '', 'risiko': '', 'rekomendasi': []
        })
        results.append(SegmentInfo(
            segment     = seg,
            description = desc,
            insight     = SegmentInsight(**insight_data),
        ))
    return results


@app.get('/segments/insight/{segment}', response_model=SegmentInfo, tags=['Info'])
def segment_insight(segment: str):
    """
    Detail insight dan rekomendasi aksi untuk satu segmen spesifik.

    Berguna untuk tim marketing mengambil rekomendasi aksi
    berdasarkan segmen hasil prediksi.
    """
    if segment not in SEGMENT_DESCRIPTIONS:
        raise HTTPException(
            status_code=404,
            detail=f"Segmen '{segment}' tidak ditemukan. "
                   f"Pilihan valid: {list(SEGMENT_DESCRIPTIONS.keys())}"
        )
    insight_data = SEGMENT_INSIGHTS.get(segment, {
        'emoji': '📌', 'karakteristik': '', 'risiko': '', 'rekomendasi': []
    })
    return SegmentInfo(
        segment     = segment,
        description = SEGMENT_DESCRIPTIONS[segment],
        insight     = SegmentInsight(**insight_data),
    )


@app.post('/predict/segment', response_model=SegmentPrediction, tags=['Prediksi'])
def predict_segment(donor: DonorFeatures):
    """
    Prediksi segmen untuk **satu donor**.

    **Input:** Fitur perilaku donasi donor.

    **v2 — Field yang TIDAK LAGI DIPERLUKAN:**
    `R_score`, `F_score`, `M_score` — jika dikirim, akan diabaikan dan
    muncul di field `deprecated_fields` pada response.

    **Output:** Segmen terprediksi, confidence, probabilitas semua segmen,
    dan **insight** berisi karakteristik & rekomendasi aksi.

    **Validasi input:**
    - `pct_zakat + pct_infaq + ... + pct_other` harus = 1.0 (±0.05)
    """
    try:
        get_model(); get_scaler(); get_encoder()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    try:
        return _infer_one(donor)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Inference error: {e}')


@app.post('/predict/segment/batch', response_model=BatchPrediction, tags=['Prediksi'])
def predict_segment_batch(request: BatchRequest):
    """
    Prediksi segmen untuk **banyak donor sekaligus** (maks 500 per request).

    Lebih efisien dari memanggil `/predict/segment` berulang karena
    semua prediksi dijalankan dalam satu forward pass.

    **Input:** List donor features (v2: tanpa R_score/F_score/M_score).
    **Output:** List prediksi dengan urutan yang sama dengan input,
    masing-masing include insight per segmen.
    """
    try:
        model   = get_model()
        scaler  = get_scaler()
        encoder = get_encoder()
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))

    t0 = datetime.datetime.now()

    try:
        rows = []
        deprecated_flags = []
        for donor in request.donors:
            d = donor.model_dump(exclude={'R_score', 'F_score', 'M_score', 'deprecated_fields'})
            dep = [f for f in ['R_score', 'F_score', 'M_score'] if getattr(donor, f, None) is not None]
            deprecated_flags.append(dep if dep else None)

            for col in RAW_TO_LOG:
                if col in d:
                    d[f'log_{col}'] = float(np.log1p(d[col]))
            rows.append([d.get(c, 0.0) for c in FEATURE_COLS])

        feat_mat  = np.array(rows, dtype=np.float32)
        feat_sc   = scaler.transform(feat_mat).astype(np.float32)
        all_probs = model.predict(feat_sc, verbose=0)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Batch inference error: {e}')

    elapsed = (datetime.datetime.now() - t0).total_seconds() * 1000

    results = []
    for probs, dep in zip(all_probs, deprecated_flags):
        idx     = int(np.argmax(probs))
        segment = encoder.classes_[idx]
        insight_data = SEGMENT_INSIGHTS.get(segment, {
            'emoji': '📌', 'karakteristik': '', 'risiko': '', 'rekomendasi': []
        })
        results.append(SegmentPrediction(
            segment           = segment,
            confidence        = round(float(probs[idx]), 4),
            all_probabilities = {
                encoder.classes_[i]: round(float(probs[i]), 4)
                for i in range(len(encoder.classes_))
            },
            description       = SEGMENT_DESCRIPTIONS.get(segment, ''),
            insight           = SegmentInsight(**insight_data),
            inference_time_ms = round(elapsed / len(request.donors), 2),
            deprecated_fields = dep,
        ))

    return BatchPrediction(
        results           = results,
        total_donors      = len(results),
        inference_time_ms = round(elapsed, 2),
    )


# ============================================================
# Startup — eager load agar inferensi pertama tidak lambat
# ============================================================

@app.on_event('startup')
async def startup_event():
    print('🚀 ZakatSight Segmentasi API v2 starting...')
    print(f'   FEATURE_COLS: {len(FEATURE_COLS)} fitur (R/F/M scores dihapus)')
    try:
        get_model(); get_scaler(); get_encoder()
        encoder = get_encoder()
        print(f'✅ Model, scaler, dan encoder berhasil dimuat.')
        print(f'   Segmen : {list(encoder.classes_)}')
    except RuntimeError as e:
        print(f'⚠️  {e}')
        print('   API tetap berjalan — artefak dimuat saat request pertama.')


# ============================================================
# Entry point
# ============================================================

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('app_segmentasi_v2:app', host='0.0.0.0', port=8001, reload=True)
