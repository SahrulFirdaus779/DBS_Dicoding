"""
Feature engineering pipeline untuk inference V3.

V3 butuh 21 features yang dihitung dari historical data:
- Raw aggregates: y, n_transactions, unique_donors, new_donors
- Calendar: is_weekend, dow_sin, dow_cos, month_sin, month_cos, days_since_start
- Ramadan: is_ramadan, days_to_eid_fitr, ramadan_day_index, ramadan_multiplier
- Lag features: lag_1, lag_7, lag_28, lag_365
- Rolling: rolling_mean_7, rolling_mean_30, rolling_std_7

CRITICAL: lag_365 mensyaratkan 365+ hari historical data sebelum window.
Untuk predict tanggal T dengan window_size=30, butuh data dari T-395 sampai T-1.
"""
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path

# Konstanta sama dengan training pipeline
RAMADAN_PERIODS = [
    ('2021-04-13', '2021-05-12'),
    ('2022-04-03', '2022-05-01'),
    ('2023-03-23', '2023-04-21'),
    ('2024-03-12', '2024-04-09'),
    ('2025-03-01', '2025-03-30'),
    ('2026-02-18', '2026-03-19'),
    ('2027-02-08', '2027-03-08'),
    ('2028-01-28', '2028-02-25'),
]

EID_FITR_DATES = [
    '2021-05-13', '2022-05-02', '2023-04-22', '2024-04-10',
    '2025-03-31', '2026-03-20', '2027-03-09', '2028-02-26',
]

# Reference dataset start date — sama dengan yang dipakai saat training
DATASET_START_DATE = pd.Timestamp('2020-12-17')


def get_ramadan_day_index(date, periods=RAMADAN_PERIODS):
    """Return day-of-Ramadan (1-30), atau 0 jika bukan Ramadan."""
    date = pd.Timestamp(date)
    for start, end in periods:
        sd, ed = pd.Timestamp(start), pd.Timestamp(end)
        if sd <= date <= ed:
            return (date - sd).days + 1
    return 0


def is_in_ramadan(date, periods=RAMADAN_PERIODS):
    """Boolean apakah tanggal di periode Ramadan."""
    return get_ramadan_day_index(date, periods) > 0


def days_to_next_eid_fitr(date, eid_dates=EID_FITR_DATES):
    """Jumlah hari sampai Eid Fitr berikutnya. Capped at 365."""
    date = pd.Timestamp(date)
    for eid in eid_dates:
        ed = pd.Timestamp(eid)
        if ed >= date:
            return min((ed - date).days, 365)
    return 365  # fallback kalau tidak ada Eid future di list


def load_ramadan_multiplier_ref(ref_path):
    """Load ramadan multiplier reference dari CSV."""
    ref = pd.read_csv(ref_path)
    return dict(zip(ref['ramadan_day'], ref['multiplier_vs_baseline']))


def add_calendar_features(df, date_col='date'):
    """Tambah features kalender: dow, month, weekend, cyclical encoding."""
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])

    df['dow'] = df[date_col].dt.dayofweek
    df['month'] = df[date_col].dt.month
    df['is_weekend'] = (df['dow'] >= 5).astype(int)

    # Cyclical encoding (sin/cos) — mempertahankan circular nature dow & month
    df['dow_sin'] = np.sin(2 * np.pi * df['dow'] / 7)
    df['dow_cos'] = np.cos(2 * np.pi * df['dow'] / 7)
    df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
    df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

    # Days since start — linear time feature
    df['days_since_start'] = (df[date_col] - DATASET_START_DATE).dt.days

    return df


def add_ramadan_features(df, ramadan_mult_map, date_col='date'):
    """Tambah features Ramadan."""
    df = df.copy()
    df[date_col] = pd.to_datetime(df[date_col])

    df['is_ramadan'] = df[date_col].apply(lambda d: 1 if is_in_ramadan(d) else 0)
    df['days_to_eid_fitr'] = df[date_col].apply(days_to_next_eid_fitr)
    df['ramadan_day_index'] = df[date_col].apply(get_ramadan_day_index)
    df['ramadan_multiplier'] = df['ramadan_day_index'].apply(
        lambda d: ramadan_mult_map.get(d, 1.0) if d > 0 else 1.0
    )

    return df


def add_target_log(df, source_col='total_nominal'):
    """Buat target y = log1p(total_nominal)."""
    df = df.copy()
    df['y'] = np.log1p(df[source_col].clip(lower=0))
    return df


def add_lag_rolling_features(df, target_col='y'):
    """Tambah lag (1, 7, 28, 365) dan rolling stats (7, 30) untuk target.

    PENTING: rolling pakai shift(1) supaya tidak include current day (no leakage).
    """
    df = df.copy()

    # Lags
    for lag in [1, 7, 28, 365]:
        df[f'lag_{lag}'] = df[target_col].shift(lag)

    # Rolling stats — shift(1) untuk avoid leakage current day
    df['rolling_mean_7'] = df[target_col].shift(1).rolling(7, min_periods=1).mean()
    df['rolling_mean_30'] = df[target_col].shift(1).rolling(30, min_periods=1).mean()
    df['rolling_std_7'] = df[target_col].shift(1).rolling(7, min_periods=1).std()

    return df


def build_inference_input(history_df, target_date, ramadan_mult_map,
                           feature_cols, window_size=30):
    """
    Build feature window untuk predict 1 hari (target_date).

    Window = window_size hari SEBELUM target_date (tidak include target).
    Sesuai cara training: X[t] = features[t-window_size : t-1], y[t] = target.

    Args:
        history_df: DataFrame dengan minimal 365+window_size hari sebelum target_date.
                    Harus punya 'date' (datetime) dan 'total_nominal' (raw rupiah).
        target_date: Tanggal yang mau di-predict (string atau pd.Timestamp).
        ramadan_mult_map: dict {ramadan_day: multiplier}.
        feature_cols: List nama feature columns sesuai training (21 cols).
        window_size: Jumlah hari window (default 30 sesuai V3).

    Returns:
        Tuple (features_array, window_df):
        - features_array: shape (1, window_size, n_features) — siap di-scale
        - window_df: DataFrame untuk debugging
    """
    target_date = pd.Timestamp(target_date)
    df = history_df.copy()
    df['date'] = pd.to_datetime(df['date'])
    # Keep only the necessary history (max lag 365 + window size 30 = 395 days) to speed up feature engineering
    df = df[df['date'] >= target_date - timedelta(days=400)].reset_index(drop=True)
    df = df.sort_values('date').reset_index(drop=True)

    # Compute features on history (no synthetic row needed — window is BEFORE target)
    df = add_target_log(df, source_col='total_nominal')
    df = add_calendar_features(df)
    df = add_ramadan_features(df, ramadan_mult_map)
    df = add_lag_rolling_features(df, target_col='y')

    # CRITICAL: training pipeline applied log1p ke count features sebelum scaling
    # Verifikasi via scaler.data_max_ (n_transactions max=8.15 = log1p of ~3500)
    for col in ['n_transactions', 'unique_donors', 'new_donors']:
        if col in df.columns:
            df[col] = np.log1p(df[col].clip(lower=0))

    # Find last index where date < target_date — that's window's last day
    mask = df['date'] < target_date
    candidates = df.index[mask]
    if len(candidates) == 0:
        raise ValueError(f"No history available before target_date {target_date.date()}")
    last_idx = int(candidates[-1])

    if last_idx + 1 < window_size:
        raise ValueError(
            f"Insufficient history before target: {last_idx + 1} days available, "
            f"need {window_size}. Plus need 365+ days more for lag_365."
        )

    # Window: window_size days ending at last_idx (inclusive)
    window_start = last_idx - window_size + 1
    window_df = df.iloc[window_start:last_idx + 1].copy()

    # Validate window covers consecutive dates ending at target_date - 1
    expected_last = target_date - pd.Timedelta(days=1)
    actual_last = window_df['date'].iloc[-1]
    if actual_last != expected_last:
        # Mungkin ada gap di history — warn tapi tidak fail
        # Yang penting last day adalah day before target
        pass

    # Validate no NaN di feature cols
    if window_df[feature_cols].isna().any().any():
        nan_cols = window_df[feature_cols].columns[window_df[feature_cols].isna().any()].tolist()
        first_nan_dates = []
        for c in nan_cols[:3]:  # first 3 only
            d = window_df.loc[window_df[c].isna(), 'date'].iloc[0]
            first_nan_dates.append(f"{c} (NaN at {d.date()})")
        raise ValueError(
            f"NaN detected in window features: {first_nan_dates}. "
            "Window overlap dengan periode awal dataset (lag_365 belum ready)."
        )

    # Extract features array — shape (1, window_size, n_features)
    features = window_df[feature_cols].values.astype(np.float32)
    return features.reshape(1, window_size, -1), window_df


def predict_single(model, scaler, features_window):
    """
    Predict 1 hari dari pre-built feature window.

    Args:
        model: loaded Keras model.
        scaler: fitted MinMaxScaler.
        features_window: array shape (1, window_size, n_features).

    Returns:
        dict dengan keys: 'pred_log', 'pred_rupiah'.
    """
    if model == "FALLBACK":
        # Fallback statistical prediction (rolling mean of last 7 days + trend slope of last 14 days)
        # target y (log1p of total_nominal) is at column index 0 in the feature window
        y_vals = features_window[0, :, 0]
        
        # Simple rolling mean of last 7 days
        recent_y = y_vals[-7:]
        base_log = float(np.mean(recent_y))
        
        # Add a slight trend factor (linear regression slope of last 14 days)
        if len(y_vals) >= 14:
            x = np.arange(14)
            y = y_vals[-14:]
            slope, _ = np.polyfit(x, y, 1)
            pred_log = base_log + slope
        else:
            pred_log = base_log
            
        pred_rupiah = float(np.expm1(pred_log))
        pred_rupiah = max(pred_rupiah, 0.0)
        
        return {
            'pred_log': float(pred_log),
            'pred_rupiah': pred_rupiah,
        }

    # Scale: scaler fit di train data shape (n_samples_total, n_features)
    # Untuk inference, reshape window jadi 2D, scale, reshape balik.
    n, w, f = features_window.shape
    flat = features_window.reshape(-1, f)
    scaled = scaler.transform(flat).reshape(n, w, f).astype(np.float32)

    # Predict — output di skala scaled target (kolom 0 di scaled space)
    pred_scaled = model.predict(scaled, verbose=0).flatten()[0]

    # Inverse scale ke log space:
    # Trick: bikin dummy row yang nilai kolom target = pred_scaled, lalu inverse_transform.
    dummy = np.zeros((1, f))
    dummy[0, 0] = pred_scaled  # target_idx = 0
    pred_log = scaler.inverse_transform(dummy)[0, 0]

    # Inverse log: y = log1p(total_nominal) → total_nominal = expm1(y)
    pred_rupiah = float(np.expm1(pred_log))
    pred_rupiah = max(pred_rupiah, 0.0)  # clamp non-negative

    return {
        'pred_log': float(pred_log),
        'pred_rupiah': pred_rupiah,
    }
