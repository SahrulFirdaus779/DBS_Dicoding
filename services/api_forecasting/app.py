"""
ZakatSight Forecast API — V3.

Run locally:
    uvicorn app:app --reload --port 8000

Run in production:
    uvicorn app:app --host 0.0.0.0 --port 8000 --workers 2
"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from schemas import HealthResponse
from routers.forecast import router as forecast_router
from lib.model_loader import get_bundle

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load model bundle saat startup."""
    logger.info("Starting ZakatSight Forecast API V3...")
    try:
        bundle = get_bundle()
        logger.info(f"✓ Bundle loaded — history: {len(bundle.history_df)} days")
    except Exception as e:
        logger.exception(f"Failed to load model bundle: {e}")
        # Don't raise — biar app tetap up, /health akan report unhealthy
    yield
    logger.info("Shutting down...")


app = FastAPI(
    title="ZakatSight Forecast API",
    description=(
        "Forecasting model V3 untuk prediksi penerimaan zakat harian. "
        "LSTM(64) + TemporalAttention dengan 21 features (calendar, lag, rolling, Ramadan). "
        "Multi-seed validated: MASE 2.23 ± 0.48, R² +0.34, Direction Acc 54.8%."
    ),
    version="3.0.0",
    lifespan=lifespan,
)

# CORS — terbuka untuk semua origin di dev, restrict di production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check — verify model loaded + history available."""
    try:
        bundle = get_bundle()
        return HealthResponse(
            status="ok",
            model_loaded=bundle.model is not None,
            history_days=len(bundle.history_df) if bundle.history_df is not None else 0,
            latest_history_date=(
                bundle.history_df['date'].max().date()
                if bundle.history_df is not None else None
            ),
        )
    except Exception as e:
        logger.exception("Health check failed")
        return HealthResponse(
            status=f"unhealthy: {e}",
            model_loaded=False,
            history_days=0,
            latest_history_date=None,
        )


@app.get("/")
async def root():
    """Root — link ke docs."""
    return {
        "service": "ZakatSight Forecast API",
        "version": "3.0.0",
        "docs": "/docs",
        "health": "/health",
        "endpoints": [
            "POST /forecast/tomorrow",
            "POST /forecast/range",
            "GET /forecast/historical",
            "GET /model/info",
        ],
    }


# Include forecast router
app.include_router(forecast_router, tags=["forecast"])
