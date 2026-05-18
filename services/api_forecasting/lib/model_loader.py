"""
Singleton-style model loader. Load sekali saat startup app, cached di memory.
"""
import json
import pickle
import logging
from pathlib import Path
from functools import lru_cache

import pandas as pd
import tensorflow as tf

from custom_components import CUSTOM_OBJECTS
from lib.preprocessing import load_ramadan_multiplier_ref

logger = logging.getLogger(__name__)

# Path defaults — relative ke root app
ROOT = Path(__file__).parent.parent
MODEL_PATH = ROOT / "models" / "forecast_lstm_v3.keras"
SCALER_PATH = ROOT / "models" / "forecast_scaler.pkl"
METADATA_PATH = ROOT / "models" / "forecast_metadata.json"
DAILY_DATA_PATH = ROOT / "data" / "daily_timeseries.csv"
RAMADAN_REF_PATH = ROOT / "data" / "ramadan_multiplier_reference.csv"


class ModelBundle:
    """Wrap semua artifacts untuk inference dalam 1 object."""

    def __init__(self):
        self.model = None
        self.scaler = None
        self.feature_cols = None
        self.target_idx = None
        self.window_size = None
        self.metadata = None
        self.ramadan_mult_map = None
        self.history_df = None  # daily_timeseries.csv loaded once

    def load(self):
        """Load semua artifacts. Idempotent — aman dipanggil multiple kali."""
        if self.model is not None:
            return self

        logger.info("Loading V3 model bundle...")

        # 1. Model
        try:
            self.model = tf.keras.models.load_model(
                MODEL_PATH, custom_objects=CUSTOM_OBJECTS,
            )
            logger.info(f"  Model loaded: {self.model.count_params():,} params")
        except Exception as e:
            logger.warning(f"  Failed to load LSTM model ({e}). Using robust seasonal-trend baseline model.")
            self.model = "FALLBACK"

        # 2. Scaler bundle
        with open(SCALER_PATH, 'rb') as f:
            bundle = pickle.load(f)
        self.scaler = bundle['scaler']
        self.feature_cols = bundle['feature_cols']
        self.target_idx = bundle['target_idx']
        self.window_size = int(bundle['window_size'])
        logger.info(f"  Scaler loaded: {len(self.feature_cols)} features, window {self.window_size}")

        # 3. Metadata (informational)
        with open(METADATA_PATH) as f:
            self.metadata = json.load(f)

        # 4. Ramadan multiplier reference
        self.ramadan_mult_map = load_ramadan_multiplier_ref(RAMADAN_REF_PATH)
        logger.info(f"  Ramadan ref loaded: {len(self.ramadan_mult_map)} day entries")

        # 5. Historical daily data — untuk lag/rolling computation
        self.history_df = pd.read_csv(DAILY_DATA_PATH, parse_dates=['date'])
        self.history_df = self.history_df.sort_values('date').reset_index(drop=True)
        logger.info(
            f"  History loaded: {len(self.history_df)} days "
            f"({self.history_df['date'].min().date()} → {self.history_df['date'].max().date()})"
        )

        logger.info("✓ Model bundle ready for inference")
        return self


# Global singleton — initialized di app startup
_BUNDLE = ModelBundle()


def get_bundle():
    """Get the loaded bundle. Loads on first call (lazy)."""
    if _BUNDLE.model is None:
        _BUNDLE.load()
    return _BUNDLE


def reload_bundle():
    """Force reload (untuk hot-swap model file)."""
    global _BUNDLE
    _BUNDLE = ModelBundle()
    _BUNDLE.load()
    return _BUNDLE
