"""
Pydantic models untuk request/response API.
"""
from datetime import date as Date
from typing import List, Optional
from pydantic import BaseModel, Field, field_validator


class ForecastRequest(BaseModel):
    """Request untuk single-day forecast."""
    target_date: Optional[Date] = Field(
        None,
        description="Tanggal yang mau di-predict (YYYY-MM-DD). Jika None, otomatis = hari setelah tanggal terakhir di history.",
    )


class ForecastRangeRequest(BaseModel):
    """Request untuk multi-day forecast dengan autoregressive iteration."""
    start_date: Optional[Date] = Field(
        None,
        description="Tanggal awal forecast. Default: hari setelah history terakhir.",
    )
    n_days: int = Field(
        7,
        ge=1, le=90,
        description="Jumlah hari yang mau di-forecast (1-90). Lebih panjang = error compounding.",
    )

    @field_validator('n_days')
    @classmethod
    def warn_long_horizon(cls, v):
        # Validasi tidak block, cuma untuk dokumentasi
        return v


class DailyForecast(BaseModel):
    """Single-day forecast response."""
    date: Date
    predicted_rupiah: float = Field(..., description="Prediksi dalam Rupiah (sudah inverse log)")
    predicted_log: float = Field(..., description="Prediksi dalam log space (raw model output)")
    is_ramadan: bool
    ramadan_day_index: int = Field(..., description="0 jika bukan Ramadan, 1-30 jika Ramadan")
    is_weekend: bool


class ForecastResponse(BaseModel):
    """Response single-day."""
    forecast: DailyForecast
    model_version: str = "v3"
    note: Optional[str] = None


class ForecastRangeResponse(BaseModel):
    """Response multi-day."""
    forecasts: List[DailyForecast]
    n_days: int
    total_predicted_rupiah: float
    avg_daily_rupiah: float
    model_version: str = "v3"
    warning: Optional[str] = None


class HistoricalRequest(BaseModel):
    """Request untuk fetch actual historical values."""
    start_date: Date
    end_date: Date


class HistoricalDay(BaseModel):
    """Single historical day."""
    date: Date
    total_nominal: float
    n_transactions: int
    is_ramadan: bool


class HistoricalResponse(BaseModel):
    """Response historical."""
    data: List[HistoricalDay]
    n_days: int


class ModelInfoResponse(BaseModel):
    """Response untuk /model/info."""
    model_version: str
    architecture: str
    window_size: int
    n_features: int
    feature_cols: List[str]
    multi_seed_summary: dict
    final_metrics: dict
    history_range: dict


class HealthResponse(BaseModel):
    """Health check."""
    status: str
    model_loaded: bool
    history_days: int
    latest_history_date: Optional[Date]
