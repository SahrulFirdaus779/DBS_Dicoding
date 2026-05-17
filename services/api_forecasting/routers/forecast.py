"""
Forecast endpoints — V3 LSTM model.

Endpoints:
- POST /forecast/tomorrow      → predict 1 hari (default: hari setelah history terakhir)
- POST /forecast/range         → predict N hari berturutan (autoregressive)
- GET  /forecast/historical    → fetch actual historical values dari range
- GET  /model/info             → metadata model
"""
import logging
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, date as Date
from fastapi import APIRouter, HTTPException

from schemas import (
    ForecastRequest, ForecastRangeRequest,
    DailyForecast, ForecastResponse, ForecastRangeResponse,
    HistoricalRequest, HistoricalDay, HistoricalResponse,
    ModelInfoResponse,
)
from lib.model_loader import get_bundle
from lib.preprocessing import (
    build_inference_input, predict_single,
    is_in_ramadan, get_ramadan_day_index,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def _resolve_target_date(target_date, history_df, offset_days=1):
    """Resolve target date — default ke hari setelah history terakhir."""
    if target_date is None:
        latest = history_df['date'].max()
        return (latest + timedelta(days=offset_days)).date()
    return target_date


def _build_daily_forecast(target_date, pred_dict):
    """Build DailyForecast object dari prediction dict."""
    td = pd.Timestamp(target_date)
    return DailyForecast(
        date=td.date(),
        predicted_rupiah=pred_dict['pred_rupiah'],
        predicted_log=pred_dict['pred_log'],
        is_ramadan=is_in_ramadan(td),
        ramadan_day_index=get_ramadan_day_index(td),
        is_weekend=td.dayofweek >= 5,
    )


@router.post("/forecast/tomorrow", response_model=ForecastResponse)
async def forecast_tomorrow(req: ForecastRequest):
    """Predict 1 hari. Default: hari setelah history terakhir."""
    bundle = get_bundle()

    target_date = _resolve_target_date(req.target_date, bundle.history_df)
    target_ts = pd.Timestamp(target_date)

    try:
        features, _ = build_inference_input(
            history_df=bundle.history_df,
            target_date=target_ts,
            ramadan_mult_map=bundle.ramadan_mult_map,
            feature_cols=bundle.feature_cols,
            window_size=bundle.window_size,
        )
        pred = predict_single(bundle.model, bundle.scaler, features)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Inference error")
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")

    forecast = _build_daily_forecast(target_date, pred)

    note = None
    if forecast.is_ramadan:
        note = (
            f"Tanggal target adalah hari ke-{forecast.ramadan_day_index} Ramadan. "
            "Akurasi model di periode Ramadan: MAPE 50-80% (better than non-Ramadan)."
        )

    return ForecastResponse(forecast=forecast, note=note)


@router.post("/forecast/range", response_model=ForecastRangeResponse)
async def forecast_range(req: ForecastRangeRequest):
    """Predict N hari berturutan secara autoregressive.

    PENTING: prediksi day 2+ pakai prediksi day 1 sebagai input → error compounding.
    Dianjurkan n_days <= 14 untuk akurasi terbaik.
    """
    bundle = get_bundle()

    start_date = _resolve_target_date(req.start_date, bundle.history_df)
    n_days = req.n_days

    # Working copy of history — akan di-extend dengan predictions
    working_df = bundle.history_df.copy()

    forecasts = []
    try:
        for day_offset in range(n_days):
            target = pd.Timestamp(start_date) + timedelta(days=day_offset)

            features, _ = build_inference_input(
                history_df=working_df,
                target_date=target,
                ramadan_mult_map=bundle.ramadan_mult_map,
                feature_cols=bundle.feature_cols,
                window_size=bundle.window_size,
            )
            pred = predict_single(bundle.model, bundle.scaler, features)
            forecasts.append(_build_daily_forecast(target, pred))

            # Append prediction ke working_df untuk iterasi berikutnya (autoregressive)
            new_row = {
                'date': target,
                'total_nominal': pred['pred_rupiah'],
                # Raw aggregates di-zero karena tidak ada prediksi untuk metrics ini
                'n_transactions': 0,
                'unique_donors': 0,
                'new_donors': 0,
            }
            working_df = pd.concat(
                [working_df, pd.DataFrame([new_row])],
                ignore_index=True,
            )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Range inference error")
        raise HTTPException(status_code=500, detail=f"Inference failed: {e}")

    total = sum(f.predicted_rupiah for f in forecasts)
    avg = total / n_days if n_days > 0 else 0

    warning = None
    if n_days > 14:
        warning = (
            f"Forecast horizon {n_days} hari panjang — error compounding di autoregressive "
            "akan signifikan. Akurasi degraded setelah ~14 hari."
        )

    return ForecastRangeResponse(
        forecasts=forecasts,
        n_days=n_days,
        total_predicted_rupiah=total,
        avg_daily_rupiah=avg,
        warning=warning,
    )


@router.get("/forecast/historical", response_model=HistoricalResponse)
async def get_historical(start_date: Date, end_date: Date):
    """Fetch actual historical values untuk range tanggal — untuk dashboard comparison."""
    bundle = get_bundle()

    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be >= start_date")

    df = bundle.history_df
    mask = (df['date'].dt.date >= start_date) & (df['date'].dt.date <= end_date)
    subset = df[mask].copy()

    data = [
        HistoricalDay(
            date=row['date'].date(),
            total_nominal=float(row['total_nominal']),
            n_transactions=int(row.get('n_transactions', 0)),
            is_ramadan=is_in_ramadan(row['date']),
        )
        for _, row in subset.iterrows()
    ]

    return HistoricalResponse(data=data, n_days=len(data))


@router.get("/model/info", response_model=ModelInfoResponse)
async def model_info():
    """Metadata model V3."""
    bundle = get_bundle()
    meta = bundle.metadata

    history_range = {
        'start': bundle.history_df['date'].min().date().isoformat(),
        'end': bundle.history_df['date'].max().date().isoformat(),
        'n_days': len(bundle.history_df),
    }

    return ModelInfoResponse(
        model_version=meta.get('model_version', 'v3'),
        architecture=meta.get('architecture', ''),
        window_size=int(meta['window_size']),
        n_features=meta['n_features'],
        feature_cols=meta['feature_cols'],
        multi_seed_summary=meta.get('multi_seed_summary', {}),
        final_metrics=meta.get('final_metrics', {}),
        history_range=history_range,
    )
