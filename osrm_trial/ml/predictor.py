"""
Bin fill prediction model — predicts when each bin will be full
and outputs a collection schedule with optimal time windows.

Pipeline:
    1. Load CSV data (real or simulated)
    2. Feature engineering: hour, weekday, rolling fill rate
    3. Train per-bin Random Forest to predict fill % at future time slots
    4. Forecast next 24h and identify collection windows
    5. Output schedule: which bins to collect at what time

Usage:
    python predictor.py                         # uses ../training_data.csv
    python predictor.py --data ../bin_log.csv
    python predictor.py --forecast-hours 48
"""

import argparse
import csv
from datetime import datetime, timedelta
from collections import defaultdict

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_csv(path: str) -> list[dict]:
    """Load bin log CSV into list of dicts."""
    rows = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append({
                "timestamp": datetime.strptime(row["Timestamp"], "%Y-%m-%d %H:%M:%S"),
                "bin_id": int(row["Bin ID"]),
                "percentage": int(row["Percentage"]),
                "status": row["Status"],
                "movement": int(row["Movement"]),
            })
    return rows


# ---------------------------------------------------------------------------
# Feature engineering
# ---------------------------------------------------------------------------

def build_features(rows: list[dict], bin_id: int) -> tuple[np.ndarray, np.ndarray]:
    """
    Build feature matrix X and target y for a single bin.

    Features per sample:
        - hour (0-23)
        - minute (0-59)
        - weekday (0=Mon, 6=Sun)
        - is_weekend (0/1)
        - current fill %
        - fill rate (delta % over last 3 samples)
    Target:
        - fill % 1 hour later
    """
    bin_rows = [r for r in rows if r["bin_id"] == bin_id]
    bin_rows.sort(key=lambda r: r["timestamp"])

    if len(bin_rows) < 10:
        return np.array([]), np.array([])

    # Build lookup: timestamp -> percentage
    ts_pct = {r["timestamp"]: r["percentage"] for r in bin_rows}
    timestamps = sorted(ts_pct.keys())

    # Detect sample interval
    intervals = [(timestamps[i+1] - timestamps[i]).total_seconds()
                 for i in range(min(20, len(timestamps)-1))]
    median_interval = sorted(intervals)[len(intervals)//2]

    # How many steps = 1 hour
    steps_per_hour = max(1, int(3600 / median_interval))

    X_list, y_list = [], []

    for i in range(3, len(bin_rows) - steps_per_hour):
        current = bin_rows[i]
        future = bin_rows[i + steps_per_hour]

        ts = current["timestamp"]
        pct = current["percentage"]

        # Fill rate over last 3 samples
        delta = pct - bin_rows[i - 3]["percentage"]

        features = [
            ts.hour,
            ts.minute,
            ts.weekday(),
            1 if ts.weekday() >= 5 else 0,
            pct,
            delta,
        ]
        X_list.append(features)
        y_list.append(future["percentage"])

    return np.array(X_list), np.array(y_list)


# ---------------------------------------------------------------------------
# Model training
# ---------------------------------------------------------------------------

def train_model(X: np.ndarray, y: np.ndarray) -> tuple[RandomForestRegressor, float]:
    """Train a Random Forest and return (model, cross-val MAE)."""
    model = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42)

    scores = cross_val_score(model, X, y, cv=5, scoring="neg_mean_absolute_error")
    mae = -scores.mean()

    model.fit(X, y)
    return model, mae


# ---------------------------------------------------------------------------
# Forecasting
# ---------------------------------------------------------------------------

def forecast_bin(
    model: RandomForestRegressor,
    last_rows: list[dict],
    hours_ahead: int = 24,
    interval_min: int = 10,
) -> list[dict]:
    """
    Iteratively predict fill % for the next N hours.
    Returns list of {timestamp, predicted_pct, status}.
    """
    # Start from the last known state
    recent = last_rows[-4:]  # need 3 prior + current
    current_pct = recent[-1]["percentage"]
    current_ts = recent[-1]["timestamp"]
    delta = current_pct - recent[-4]["percentage"] if len(recent) >= 4 else 0

    predictions = []
    steps = hours_ahead * 60 // interval_min

    for step in range(1, steps + 1):
        future_ts = current_ts + timedelta(minutes=step * interval_min)

        features = np.array([[
            future_ts.hour,
            future_ts.minute,
            future_ts.weekday(),
            1 if future_ts.weekday() >= 5 else 0,
            current_pct,
            delta,
        ]])

        pred_pct = model.predict(features)[0]
        pred_pct = max(0, min(100, pred_pct))

        old_pct = current_pct
        current_pct = pred_pct
        delta = current_pct - old_pct

        predictions.append({
            "timestamp": future_ts,
            "predicted_pct": round(pred_pct, 1),
            "status": "FULL" if pred_pct >= 80 else "OK",
        })

    return predictions


# ---------------------------------------------------------------------------
# Schedule generation
# ---------------------------------------------------------------------------

def generate_schedule(
    all_forecasts: dict[int, list[dict]],
    threshold: float = 80.0,
) -> list[dict]:
    """
    From per-bin forecasts, identify time windows where bins need collection.

    Returns list of {time_window, bins_to_collect} sorted by time.
    """
    # Find first time each bin crosses threshold
    events = []
    for bin_id, preds in all_forecasts.items():
        for p in preds:
            if p["predicted_pct"] >= threshold:
                events.append({
                    "timestamp": p["timestamp"],
                    "bin_id": bin_id,
                    "predicted_pct": p["predicted_pct"],
                })
                break

    events.sort(key=lambda e: e["timestamp"])

    # Group into 1-hour collection windows
    schedule = []
    if not events:
        return schedule

    window_start = events[0]["timestamp"].replace(minute=0, second=0)
    current_bins = []

    for ev in events:
        ev_hour = ev["timestamp"].replace(minute=0, second=0)
        if ev_hour == window_start:
            current_bins.append(ev["bin_id"])
        else:
            if current_bins:
                schedule.append({
                    "time_window": window_start.strftime("%Y-%m-%d %H:00"),
                    "bins_to_collect": sorted(current_bins),
                })
            window_start = ev_hour
            current_bins = [ev["bin_id"]]

    if current_bins:
        schedule.append({
            "time_window": window_start.strftime("%Y-%m-%d %H:00"),
            "bins_to_collect": sorted(current_bins),
        })

    return schedule


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Bin fill predictor")
    parser.add_argument("--data", type=str, default="../training_data.csv")
    parser.add_argument("--forecast-hours", type=int, default=24)
    args = parser.parse_args()

    print(f"Loading data from {args.data}...")
    rows = load_csv(args.data)
    print(f"  {len(rows)} records loaded")

    bin_ids = sorted(set(r["bin_id"] for r in rows))
    print(f"  Bins: {bin_ids}")

    models = {}
    all_forecasts = {}

    for bin_id in bin_ids:
        print(f"\n--- Bin {bin_id} ---")
        X, y = build_features(rows, bin_id)
        if len(X) == 0:
            print("  Not enough data, skipping")
            continue

        print(f"  Training samples: {len(X)}")
        model, mae = train_model(X, y)
        print(f"  Cross-val MAE: {mae:.2f}%")
        models[bin_id] = model

        # Forecast
        bin_rows = sorted(
            [r for r in rows if r["bin_id"] == bin_id],
            key=lambda r: r["timestamp"],
        )
        preds = forecast_bin(model, bin_rows, hours_ahead=args.forecast_hours)
        all_forecasts[bin_id] = preds

        # Show first time it reaches FULL
        full_times = [p for p in preds if p["status"] == "FULL"]
        if full_times:
            first = full_times[0]
            print(f"  Predicted FULL at: {first['timestamp']} ({first['predicted_pct']}%)")
        else:
            print(f"  Stays below 80% for next {args.forecast_hours}h")

    # Schedule
    print("\n=== Collection Schedule ===")
    schedule = generate_schedule(all_forecasts)
    if not schedule:
        print("  No collections needed in forecast window")
    else:
        for entry in schedule:
            bins_str = ", ".join(f"Bin {b}" for b in entry["bins_to_collect"])
            print(f"  {entry['time_window']}  →  Collect: {bins_str}")


if __name__ == "__main__":
    main()
