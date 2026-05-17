"""
End-to-end smoke test untuk FastAPI V3.

Run dari root project:
    python tests/test_e2e.py

Tidak butuh server running — test langsung internal pipeline.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd

from lib.model_loader import get_bundle
from lib.preprocessing import build_inference_input, predict_single, is_in_ramadan


def test_model_bundle_loads():
    """Model bundle harus load tanpa error."""
    bundle = get_bundle()
    assert bundle.model is not None, "Model not loaded"
    assert bundle.scaler is not None, "Scaler not loaded"
    assert len(bundle.feature_cols) == 21, f"Expected 21 features, got {len(bundle.feature_cols)}"
    assert bundle.window_size == 30, f"Expected window 30, got {bundle.window_size}"
    assert len(bundle.ramadan_mult_map) == 30, f"Expected 30 Ramadan days, got {len(bundle.ramadan_mult_map)}"
    print(f"  Model: {bundle.model.count_params():,} params")
    print(f"  History: {len(bundle.history_df)} days")
    print("✓ Bundle loads correctly")


def test_predict_tomorrow():
    """Predict 1 hari setelah history terakhir."""
    bundle = get_bundle()
    target = bundle.history_df['date'].max() + pd.Timedelta(days=1)

    features, _ = build_inference_input(
        history_df=bundle.history_df,
        target_date=target,
        ramadan_mult_map=bundle.ramadan_mult_map,
        feature_cols=bundle.feature_cols,
        window_size=bundle.window_size,
    )
    assert features.shape == (1, 30, 21), f"Bad features shape: {features.shape}"

    pred = predict_single(bundle.model, bundle.scaler, features)
    assert pred['pred_rupiah'] > 0, f"Prediction should be positive: {pred}"
    assert pred['pred_rupiah'] < 1e15, f"Prediction sanity: too large: {pred}"

    print(f"  Tomorrow ({target.date()}): Rp {pred['pred_rupiah']/1e6:,.2f} jt")
    print("✓ Tomorrow prediction works")


def test_predict_in_ramadan():
    """Predict tanggal yang ada di periode Ramadan — harus masuk akal."""
    bundle = get_bundle()
    # Try predicting day 15 Ramadan 2026 (March 4, 2026)
    target = pd.Timestamp('2026-03-04')

    if target > bundle.history_df['date'].max():
        print(f"  ⚠️  Skipping — {target.date()} beyond history range")
        return

    features, window_df = build_inference_input(
        history_df=bundle.history_df,
        target_date=target,
        ramadan_mult_map=bundle.ramadan_mult_map,
        feature_cols=bundle.feature_cols,
        window_size=bundle.window_size,
    )
    pred = predict_single(bundle.model, bundle.scaler, features)
    actual = bundle.history_df[bundle.history_df['date'] == target]['total_nominal'].values[0]

    print(f"  Ramadan day 15 ({target.date()}): pred Rp {pred['pred_rupiah']/1e6:,.2f} jt, actual Rp {actual/1e6:,.2f} jt")
    print("✓ Ramadan prediction works")


def test_predict_range_autoregressive():
    """Predict 7 hari forward — autoregressive dengan working_df extension."""
    bundle = get_bundle()
    start_date = bundle.history_df['date'].max() + pd.Timedelta(days=1)

    working_df = bundle.history_df.copy()
    preds = []
    for i in range(7):
        target = start_date + pd.Timedelta(days=i)
        features, _ = build_inference_input(
            history_df=working_df,
            target_date=target,
            ramadan_mult_map=bundle.ramadan_mult_map,
            feature_cols=bundle.feature_cols,
            window_size=bundle.window_size,
        )
        pred = predict_single(bundle.model, bundle.scaler, features)
        preds.append((target.date(), pred['pred_rupiah']))

        # Extend working_df dengan prediction
        new_row = {
            'date': target,
            'total_nominal': pred['pred_rupiah'],
            'n_transactions': 0, 'unique_donors': 0, 'new_donors': 0,
        }
        working_df = pd.concat([working_df, pd.DataFrame([new_row])], ignore_index=True)

    print(f"  7-day forecast:")
    for date, val in preds:
        ramadan_marker = " 🌙" if is_in_ramadan(date) else ""
        print(f"    {date}: Rp {val/1e6:,.2f} jt{ramadan_marker}")
    print("✓ Range autoregressive works")


def test_window_size_validation():
    """Insufficient history harus raise ValueError."""
    bundle = get_bundle()
    # Build df dengan cuma 100 hari (kurang dari 365 + 30 minimum)
    short_df = bundle.history_df.head(100).copy()
    target = short_df['date'].max() + pd.Timedelta(days=1)

    try:
        build_inference_input(
            history_df=short_df,
            target_date=target,
            ramadan_mult_map=bundle.ramadan_mult_map,
            feature_cols=bundle.feature_cols,
            window_size=bundle.window_size,
        )
        assert False, "Should have raised ValueError for insufficient history"
    except ValueError as e:
        print(f"  Got expected error: {str(e)[:80]}...")
        print("✓ Insufficient history validation works")


if __name__ == '__main__':
    print("=" * 70)
    print("ZakatSight Forecast V3 — E2E Smoke Tests")
    print("=" * 70)

    tests = [
        ("Model bundle loads", test_model_bundle_loads),
        ("Predict tomorrow", test_predict_tomorrow),
        ("Predict in Ramadan", test_predict_in_ramadan),
        ("Predict range (autoregressive)", test_predict_range_autoregressive),
        ("Window size validation", test_window_size_validation),
    ]

    failed = 0
    for name, test_fn in tests:
        print(f"\n[TEST] {name}")
        try:
            test_fn()
        except AssertionError as e:
            print(f"❌ FAILED: {e}")
            failed += 1
        except Exception as e:
            print(f"❌ ERROR: {type(e).__name__}: {e}")
            failed += 1

    print("\n" + "=" * 70)
    if failed == 0:
        print("✅ ALL TESTS PASSED")
    else:
        print(f"❌ {failed}/{len(tests)} tests failed")
        sys.exit(1)
