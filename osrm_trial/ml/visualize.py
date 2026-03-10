"""
Generate a standalone HTML report to evaluate prediction model quality.

Outputs: report.html (self-contained, no server needed)

Charts:
    1. Historical fill curves per bin (last 7 days)
    2. Predicted vs actual fill (backtest on held-out data)
    3. 24h forecast per bin with FULL threshold line
    4. Collection schedule timeline
    5. Per-bin MAE bar chart

Usage:
    python visualize.py                           # uses ../training_data.csv
    python visualize.py --data ../bin_log.csv
    python visualize.py --out my_report.html
"""

import argparse
import json
import html

from predictor import load_csv, build_features, forecast_bin

import numpy as np
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score


def _backtest(rows, bin_id, test_ratio=0.2):
    """Train on earlier data, predict on later data, return actual vs predicted."""
    bin_rows = sorted(
        [r for r in rows if r["bin_id"] == bin_id],
        key=lambda r: r["timestamp"],
    )
    X, y = build_features(rows, bin_id)
    if len(X) == 0:
        return [], [], 0

    split = int(len(X) * (1 - test_ratio))
    X_train, X_test = X[:split], X[split:]
    y_train, y_test = y[:split], y[split:]

    model = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42)
    model.fit(X_train, y_train)
    y_pred = model.predict(X_test)
    mae = float(np.mean(np.abs(y_test - y_pred)))

    return y_test.tolist(), y_pred.tolist(), mae


def _train_and_forecast(rows, bin_id, hours=24):
    """Full train + forecast."""
    X, y = build_features(rows, bin_id)
    if len(X) == 0:
        return None, 0, []

    model = RandomForestRegressor(n_estimators=100, max_depth=12, random_state=42)
    scores = cross_val_score(model, X, y, cv=5, scoring="neg_mean_absolute_error")
    mae = float(-scores.mean())
    model.fit(X, y)

    bin_rows = sorted(
        [r for r in rows if r["bin_id"] == bin_id],
        key=lambda r: r["timestamp"],
    )
    preds = forecast_bin(model, bin_rows, hours_ahead=hours)
    return model, mae, preds


def _history_series(rows, bin_id, last_days=7):
    """Extract last N days of historical data for a bin."""
    bin_rows = sorted(
        [r for r in rows if r["bin_id"] == bin_id],
        key=lambda r: r["timestamp"],
    )
    if not bin_rows:
        return [], []

    cutoff = bin_rows[-1]["timestamp"] - __import__("datetime").timedelta(days=last_days)
    recent = [r for r in bin_rows if r["timestamp"] >= cutoff]

    # Downsample to ~1 point per hour for readability
    sampled_ts, sampled_pct = [], []
    last_hour = None
    for r in recent:
        h = r["timestamp"].strftime("%Y-%m-%d %H:00")
        if h != last_hour:
            sampled_ts.append(r["timestamp"].strftime("%m-%d %H:%M"))
            sampled_pct.append(r["percentage"])
            last_hour = h

    return sampled_ts, sampled_pct


def generate_report(data_path, out_path, forecast_hours):
    rows = load_csv(data_path)
    bin_ids = sorted(set(r["bin_id"] for r in rows))

    # Collect all chart data
    history_data = {}
    backtest_data = {}
    forecast_data = {}
    mae_scores = {}

    for bid in bin_ids:
        # History
        ts, pct = _history_series(rows, bid)
        history_data[bid] = {"labels": ts, "data": pct}

        # Backtest
        actual, predicted, bt_mae = _backtest(rows, bid)
        # Downsample backtest for chart (every 6th point)
        step = max(1, len(actual) // 200)
        backtest_data[bid] = {
            "actual": actual[::step],
            "predicted": [round(p, 1) for p in predicted[::step]],
            "mae": round(bt_mae, 2),
        }

        # Forecast
        _, cv_mae, preds = _train_and_forecast(rows, bid, forecast_hours)
        mae_scores[bid] = round(cv_mae, 2)
        forecast_data[bid] = {
            "labels": [p["timestamp"].strftime("%m-%d %H:%M") for p in preds],
            "data": [p["predicted_pct"] for p in preds],
        }

    # Build schedule from forecasts
    schedule = []
    for bid in bin_ids:
        for p in forecast_data[bid]["data"]:
            pass
        for i, p in enumerate(forecast_data[bid]["data"]):
            if p >= 80:
                schedule.append({
                    "time": forecast_data[bid]["labels"][i],
                    "bin": bid,
                    "pct": p,
                })
                break

    # Color palette
    colors = ["#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#8b5cf6"]

    report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IntelliBin — Prediction Report</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
  :root {{ --bg: #0f172a; --card: #1e293b; --text: #e2e8f0; --muted: #94a3b8; --accent: #3b82f6; --danger: #ef4444; --success: #22c55e; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: var(--bg); color: var(--text); font-family: 'Inter', system-ui, sans-serif; padding: 24px; }}
  h1 {{ font-size: 1.5rem; margin-bottom: 8px; }}
  .subtitle {{ color: var(--muted); font-size: 0.85rem; margin-bottom: 32px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(560px, 1fr)); gap: 20px; margin-bottom: 20px; }}
  .card {{ background: var(--card); border-radius: 12px; padding: 20px; }}
  .card h2 {{ font-size: 0.95rem; color: var(--muted); margin-bottom: 12px; font-weight: 500; }}
  canvas {{ width: 100% !important; height: 280px !important; }}
  .metrics {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 20px; }}
  .metric {{ background: var(--card); border-radius: 12px; padding: 16px 24px; min-width: 150px; }}
  .metric .value {{ font-size: 1.8rem; font-weight: 700; }}
  .metric .label {{ color: var(--muted); font-size: 0.8rem; margin-top: 4px; }}
  .schedule {{ background: var(--card); border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
  .schedule h2 {{ font-size: 0.95rem; color: var(--muted); margin-bottom: 12px; font-weight: 500; }}
  .schedule-item {{ display: flex; align-items: center; gap: 12px; padding: 8px 0; border-bottom: 1px solid #334155; }}
  .schedule-item:last-child {{ border-bottom: none; }}
  .schedule-item .time {{ color: var(--accent); font-weight: 600; min-width: 110px; }}
  .schedule-item .bin-badge {{ background: var(--danger); color: #fff; border-radius: 6px; padding: 2px 10px; font-size: 0.8rem; font-weight: 600; }}
  .schedule-item .pct {{ color: var(--muted); font-size: 0.85rem; }}
</style>
</head>
<body>

<h1>IntelliBin Prediction Report</h1>
<p class="subtitle">Data: {html.escape(data_path)} | {len(rows)} records | {len(bin_ids)} bins | Forecast: {forecast_hours}h</p>

<!-- Metrics -->
<div class="metrics">
  {"".join(f'''<div class="metric"><div class="value" style="color:{colors[i % len(colors)]}">{mae_scores[bid]}%</div><div class="label">Bin {bid} MAE</div></div>''' for i, bid in enumerate(bin_ids))}
  <div class="metric"><div class="value" style="color:var(--success)">{round(sum(mae_scores.values()) / len(mae_scores), 2)}%</div><div class="label">Avg MAE</div></div>
  <div class="metric"><div class="value">{len(rows)}</div><div class="label">Training Samples</div></div>
</div>

<!-- Schedule -->
<div class="schedule">
  <h2>Predicted Collection Schedule (next {forecast_hours}h)</h2>
  {"".join(f'''<div class="schedule-item"><span class="time">{s["time"]}</span><span class="bin-badge">Bin {s["bin"]}</span><span class="pct">{s["pct"]}% predicted</span></div>''' for s in schedule) if schedule else '<p style="color:var(--muted)">No collections needed in forecast window</p>'}
</div>

<!-- Charts -->
<div class="grid">

  <!-- Historical -->
  <div class="card">
    <h2>Historical Fill Levels (last 7 days)</h2>
    <canvas id="historyChart"></canvas>
  </div>

  <!-- Forecast -->
  <div class="card">
    <h2>Forecast (next {forecast_hours}h)</h2>
    <canvas id="forecastChart"></canvas>
  </div>

  <!-- Backtest per bin -->
  {"".join(f'''<div class="card"><h2>Backtest — Bin {bid} (MAE: {backtest_data[bid]["mae"]}%)</h2><canvas id="bt{bid}"></canvas></div>''' for bid in bin_ids)}

  <!-- MAE comparison -->
  <div class="card">
    <h2>Model Accuracy (MAE per bin)</h2>
    <canvas id="maeChart"></canvas>
  </div>

</div>

<script>
const COLORS = {json.dumps(colors)};
Chart.defaults.color = '#94a3b8';
Chart.defaults.borderColor = '#334155';
Chart.defaults.font.family = "'Inter', system-ui, sans-serif";

// --- History ---
new Chart(document.getElementById('historyChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(history_data[bin_ids[0]]["labels"])},
    datasets: [{",".join(f'''{{
      label: 'Bin {bid}',
      data: {json.dumps(history_data[bid]["data"])},
      borderColor: COLORS[{i}],
      backgroundColor: COLORS[{i}] + '20',
      borderWidth: 1.5,
      pointRadius: 0,
      tension: 0.3,
      fill: true
    }}''' for i, bid in enumerate(bin_ids))}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{
      legend: {{ position: 'top', labels: {{ boxWidth: 12 }} }},
      annotation: undefined
    }},
    scales: {{
      x: {{ display: true, ticks: {{ maxTicksLimit: 12 }} }},
      y: {{ min: 0, max: 105 }}
    }}
  }}
}});

// --- Forecast ---
new Chart(document.getElementById('forecastChart'), {{
  type: 'line',
  data: {{
    labels: {json.dumps(forecast_data[bin_ids[0]]["labels"])},
    datasets: [
      {",".join(f'''{{
        label: 'Bin {bid}',
        data: {json.dumps(forecast_data[bid]["data"])},
        borderColor: COLORS[{i}],
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3
      }}''' for i, bid in enumerate(bin_ids))},
      {{
        label: 'FULL Threshold',
        data: Array({len(forecast_data[bin_ids[0]]["labels"])}).fill(80),
        borderColor: '#ef4444',
        borderWidth: 1,
        borderDash: [6, 4],
        pointRadius: 0,
        fill: false
      }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'top', labels: {{ boxWidth: 12 }} }} }},
    scales: {{
      x: {{ ticks: {{ maxTicksLimit: 12 }} }},
      y: {{ min: 0, max: 105 }}
    }}
  }}
}});

// --- Backtest charts ---
{chr(10).join(f'''
new Chart(document.getElementById('bt{bid}'), {{
  type: 'line',
  data: {{
    labels: Array({len(backtest_data[bid]["actual"])}).fill('').map((_, i) => i),
    datasets: [
      {{ label: 'Actual', data: {json.dumps(backtest_data[bid]["actual"])}, borderColor: COLORS[{i}], borderWidth: 1.5, pointRadius: 0, tension: 0.2 }},
      {{ label: 'Predicted', data: {json.dumps(backtest_data[bid]["predicted"])}, borderColor: '#f59e0b', borderWidth: 1.5, pointRadius: 0, tension: 0.2, borderDash: [4, 3] }}
    ]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ position: 'top', labels: {{ boxWidth: 12 }} }} }},
    scales: {{
      x: {{ display: false }},
      y: {{ min: 0, max: 105 }}
    }}
  }}
}});''' for i, bid in enumerate(bin_ids))}

// --- MAE bar chart ---
new Chart(document.getElementById('maeChart'), {{
  type: 'bar',
  data: {{
    labels: {json.dumps([f"Bin {bid}" for bid in bin_ids])},
    datasets: [{{
      label: 'MAE (%)',
      data: {json.dumps([mae_scores[bid] for bid in bin_ids])},
      backgroundColor: {json.dumps([colors[i % len(colors)] + '80' for i in range(len(bin_ids))])},
      borderColor: {json.dumps([colors[i % len(colors)] for i in range(len(bin_ids))])},
      borderWidth: 1.5,
      borderRadius: 6
    }}]
  }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }} }},
    scales: {{ y: {{ beginAtZero: true, title: {{ display: true, text: 'MAE (%)' }} }} }}
  }}
}});
</script>
</body>
</html>"""

    with open(out_path, "w") as f:
        f.write(report_html)

    print(f"Report generated → {out_path}")
    print(f"  Bins: {bin_ids}")
    for bid in bin_ids:
        print(f"  Bin {bid}: CV-MAE={mae_scores[bid]}%, Backtest-MAE={backtest_data[bid]['mae']}%")


def main():
    parser = argparse.ArgumentParser(description="Generate prediction report")
    parser.add_argument("--data", type=str, default="../training_data.csv")
    parser.add_argument("--out", type=str, default="report.html")
    parser.add_argument("--forecast-hours", type=int, default=24)
    args = parser.parse_args()

    generate_report(args.data, args.out, args.forecast_hours)


if __name__ == "__main__":
    main()
