"""
inference_simple.py — ZakatSight Segmentasi Donor
CC26-PSU193 | AI Engineer: Hasna Minatul Mardiah

Skrip sederhana untuk menjalankan inferensi model segmentasi donor
tanpa web framework. Cocok untuk testing lokal, demo, atau integrasi
ke pipeline batch sederhana.

Cara pakai:
    python inference_simple.py

Pastikan file-file berikut ada di folder model_output/:
    - zakatsight_segmentasi_v2.keras
    - scaler_segmentasi_v2.pkl
    - label_encoder_v2.pkl
"""

import numpy as np
import joblib
import tensorflow as tf
from pathlib import Path

# ============================================================
# Custom Objects — harus didefinisikan ulang agar model bisa dimuat
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
        self.W_a = self.add_weight(name='W_a', shape=(d, 1),          initializer=gi, trainable=True)
        self.b_a = self.add_weight(name='b_a', shape=(1,),            initializer=zi, trainable=True)
        self.W_o = self.add_weight(name='W_o', shape=(d, self.units), initializer=gi, trainable=True)
        self.b_o = self.add_weight(name='b_o', shape=(self.units,),   initializer=zi, trainable=True)
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
# Konfigurasi path model
# ============================================================

MODEL_PATH   = Path('model_output/zakatsight_segmentasi_v2.keras')
SCALER_PATH  = Path('model_output/scaler_segmentasi_v2.pkl')
ENCODER_PATH = Path('model_output/label_encoder_v2.pkl')

# ============================================================
# Fitur yang digunakan model v2 (23 fitur, tanpa R/F/M score)
# ============================================================

FEATURE_COLS = [
    'recency_days', 'log_frequency', 'log_monetary_total',
    'log_monetary_avg', 'log_monetary_max', 'log_monetary_std',
    'tenure_days', 'n_unique_programs', 'n_unique_channels',
    'pct_zakat', 'pct_infaq', 'pct_kemanusiaan', 'pct_pendidikan',
    'pct_sedekah', 'pct_wakaf', 'pct_yatim', 'pct_qurban', 'pct_other',
    'pct_weekend', 'pct_ramadan',
    'inter_arrival_avg_days', 'inter_arrival_std_days',
    'has_real_phone',
]

# Fitur raw yang perlu di-log-transform sebelum masuk model
RAW_TO_LOG = ['monetary_total', 'monetary_avg', 'monetary_max',
              'monetary_min', 'monetary_median', 'monetary_std', 'frequency']


# ============================================================
# Step 1: Load model, scaler, dan label encoder
# ============================================================

def load_artifacts():
    """Muat model dan artefak pendukung dari disk."""
    for path in [MODEL_PATH, SCALER_PATH, ENCODER_PATH]:
        if not path.exists():
            raise FileNotFoundError(
                f"File tidak ditemukan: {path}\n"
                "Pastikan sudah menjalankan notebook training v2 terlebih dahulu."
            )

    print("Memuat model...")
    model   = tf.keras.models.load_model(str(MODEL_PATH), custom_objects=CUSTOM_OBJECTS)

    print("Memuat scaler dan label encoder...")
    scaler  = joblib.load(str(SCALER_PATH))
    encoder = joblib.load(str(ENCODER_PATH))

    print(f"✅ Artefak berhasil dimuat.")
    print(f"   Segmen yang dikenali: {list(encoder.classes_)}\n")
    return model, scaler, encoder


# ============================================================
# Step 2: Preprocessing input donor
# ============================================================

def preprocess(donor_data: dict, scaler) -> np.ndarray:
    """
    Konversi data mentah donor → feature vector siap dipakai model.

    Langkah:
    1. Log-transform fitur skewed (monetary, frequency)
    2. Susun sesuai urutan FEATURE_COLS
    3. Standardisasi dengan scaler (fit dari data training)
    """
    d = dict(donor_data)

    # Log-transform fitur yang skewed
    for col in RAW_TO_LOG:
        if col in d:
            d[f'log_{col}'] = float(np.log1p(d[col]))

    # Susun feature vector sesuai urutan FEATURE_COLS (default 0 jika tidak ada)
    feat_vec = np.array([[d.get(col, 0.0) for col in FEATURE_COLS]], dtype=np.float32)

    # Standardisasi
    feat_scaled = scaler.transform(feat_vec).astype(np.float32)
    return feat_scaled


# ============================================================
# Step 3: Inferensi
# ============================================================

def predict_segment(donor_data: dict, model, scaler, encoder) -> dict:
    """
    Prediksi segmen donor dari data mentah.

    Returns:
        dict berisi segmen, confidence, dan probabilitas semua segmen.
    """
    # Preprocessing
    feat_scaled = preprocess(donor_data, scaler)

    # Prediksi probabilitas semua segmen
    probs = model.predict(feat_scaled, verbose=0)[0]

    # Ambil segmen dengan probabilitas tertinggi
    idx        = int(np.argmax(probs))
    segment    = encoder.classes_[idx]
    confidence = float(probs[idx])

    # Susun probabilitas semua segmen
    all_probs = {encoder.classes_[i]: round(float(probs[i]), 4)
                 for i in range(len(encoder.classes_))}

    return {
        'segment'          : segment,
        'confidence'       : round(confidence, 4),
        'all_probabilities': all_probs,
    }


# ============================================================
# Contoh data donor untuk demo
# ============================================================

CONTOH_DONOR = [
    {
        'nama'            : 'Donor A (Champions)',
        'recency_days'    : 5,
        'frequency'       : 48,
        'monetary_total'  : 15_000_000,
        'monetary_avg'    : 312_500,
        'monetary_max'    : 1_000_000,
        'monetary_std'    : 150_000,
        'tenure_days'     : 730,
        'n_unique_programs': 5,
        'n_unique_channels': 3,
        'pct_zakat'       : 0.5,
        'pct_infaq'       : 0.2,
        'pct_kemanusiaan' : 0.1,
        'pct_pendidikan'  : 0.1,
        'pct_sedekah'     : 0.1,
        'pct_wakaf'       : 0.0,
        'pct_yatim'       : 0.0,
        'pct_qurban'      : 0.0,
        'pct_other'       : 0.0,
        'pct_weekend'     : 0.3,
        'pct_ramadan'     : 0.25,
        'inter_arrival_avg_days': 7.5,
        'inter_arrival_std_days': 3.2,
        'has_real_phone'  : 1,
    },
    {
        'nama'            : 'Donor B (At Risk)',
        'recency_days'    : 280,
        'frequency'       : 6,
        'monetary_total'  : 900_000,
        'monetary_avg'    : 150_000,
        'monetary_max'    : 300_000,
        'monetary_std'    : 80_000,
        'tenure_days'     : 540,
        'n_unique_programs': 2,
        'n_unique_channels': 1,
        'pct_zakat'       : 0.0,
        'pct_infaq'       : 0.6,
        'pct_kemanusiaan' : 0.4,
        'pct_pendidikan'  : 0.0,
        'pct_sedekah'     : 0.0,
        'pct_wakaf'       : 0.0,
        'pct_yatim'       : 0.0,
        'pct_qurban'      : 0.0,
        'pct_other'       : 0.0,
        'pct_weekend'     : 0.5,
        'pct_ramadan'     : 0.5,
        'inter_arrival_avg_days': 65.0,
        'inter_arrival_std_days': 40.0,
        'has_real_phone'  : 0,
    },
    {
        'nama'            : 'Donor C (New Donor)',
        'recency_days'    : 10,
        'frequency'       : 1,
        'monetary_total'  : 100_000,
        'monetary_avg'    : 100_000,
        'monetary_max'    : 100_000,
        'monetary_std'    : 0,
        'tenure_days'     : 10,
        'n_unique_programs': 1,
        'n_unique_channels': 1,
        'pct_zakat'       : 0.0,
        'pct_infaq'       : 1.0,
        'pct_kemanusiaan' : 0.0,
        'pct_pendidikan'  : 0.0,
        'pct_sedekah'     : 0.0,
        'pct_wakaf'       : 0.0,
        'pct_yatim'       : 0.0,
        'pct_qurban'      : 0.0,
        'pct_other'       : 0.0,
        'pct_weekend'     : 0.0,
        'pct_ramadan'     : 0.0,
        'inter_arrival_avg_days': 0.0,
        'inter_arrival_std_days': 0.0,
        'has_real_phone'  : 1,
    },
]


# ============================================================
# Main
# ============================================================

if __name__ == '__main__':
    print("=" * 55)
    print("  ZakatSight — Inference Segmentasi Donor v2")
    print("  CC26-PSU193 | Hasna Minatul Mardiah")
    print("=" * 55)
    print()

    # Step 1: Load artefak
    model, scaler, encoder = load_artifacts()

    # Step 2 & 3: Prediksi tiap contoh donor
    for donor in CONTOH_DONOR:
        nama = donor.pop('nama')  # ambil nama untuk display, bukan fitur model
        print(f"--- {nama} ---")

        hasil = predict_segment(donor, model, scaler, encoder)

        print(f"  Segmen     : {hasil['segment']}")
        print(f"  Confidence : {hasil['confidence'] * 100:.2f}%")
        print(f"  Probabilitas semua segmen:")
        for seg, prob in sorted(hasil['all_probabilities'].items(),
                                key=lambda x: x[1], reverse=True):
            bar = '█' * int(prob * 20)
            print(f"    {seg:<20} {prob:.4f}  {bar}")
        print()

    print("✅ Inferensi selesai.")
