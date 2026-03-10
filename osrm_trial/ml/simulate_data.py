"""
Generate realistic multi-day bin fill data for training.

Each bin has a daily fill-rate profile driven by hour-of-day weights
(busier during morning, lunch, evening). When a bin hits ~95-100%,
a "collection" event resets it to near-zero after a random delay.

Usage:
    python simulate_data.py              # 30 days, 3 bins, writes to ../training_data.csv
    python simulate_data.py --days 60 --bins 5 --out data.csv
"""

import argparse
import csv
import random
from datetime import datetime, timedelta

# ---------------------------------------------------------------------------
# Per-hour fill-rate weights (0–23h). Higher = bins fill faster that hour.
# ---------------------------------------------------------------------------

HOURLY_PROFILES = {
    # Bin 1: residential area — morning + evening peaks
    1: [0.1, 0.05, 0.02, 0.02, 0.05, 0.1,
        0.6, 0.9, 1.0, 0.7, 0.4, 0.5,
        0.8, 0.6, 0.4, 0.3, 0.4, 0.7,
        1.0, 0.9, 0.6, 0.4, 0.2, 0.1],
    # Bin 2: commercial zone — lunch peak, business hours
    2: [0.05, 0.02, 0.02, 0.02, 0.02, 0.05,
        0.2, 0.4, 0.7, 0.9, 1.0, 1.0,
        1.0, 0.9, 0.8, 0.6, 0.5, 0.3,
        0.2, 0.1, 0.05, 0.05, 0.02, 0.02],
    # Bin 3: park / tourist — afternoon peak
    3: [0.05, 0.02, 0.02, 0.02, 0.02, 0.05,
        0.1, 0.2, 0.3, 0.5, 0.7, 0.9,
        1.0, 1.0, 1.0, 0.9, 0.8, 0.6,
        0.4, 0.3, 0.2, 0.1, 0.05, 0.02],
}

# Base fill increment per 10-min interval when weight=1.0
BASE_INCREMENT = 2.5  # percent per interval at peak


def _get_profile(bin_id: int) -> list[float]:
    """Return hourly weight profile, cycling through predefined ones."""
    keys = sorted(HOURLY_PROFILES.keys())
    return HOURLY_PROFILES[keys[(bin_id - 1) % len(keys)]]


def simulate(num_bins: int = 3, num_days: int = 30, interval_min: int = 10) -> list[list]:
    """
    Returns rows of [timestamp_str, bin_id, percentage, status, movement].
    """
    rows = []
    start_date = datetime(2025, 1, 1)
    intervals_per_day = 24 * 60 // interval_min

    for bin_id in range(1, num_bins + 1):
        profile = _get_profile(bin_id)
        fill = random.uniform(0, 15)  # start with some fill
        collecting = False
        collect_countdown = 0

        # Add weekday variation: weekends have different patterns
        weekend_scale = 0.6  # bins fill slower on weekends (for commercial)

        for day in range(num_days):
            date = start_date + timedelta(days=day)
            is_weekend = date.weekday() >= 5
            day_noise = random.uniform(0.8, 1.2)  # daily variation

            for slot in range(intervals_per_day):
                ts = date + timedelta(minutes=slot * interval_min)
                hour = ts.hour

                # Fill rate
                weight = profile[hour]
                if is_weekend:
                    if bin_id % 3 == 2:  # commercial bins slow on weekends
                        weight *= weekend_scale
                    elif bin_id % 3 == 0:  # park bins busier on weekends
                        weight *= 1.4

                increment = BASE_INCREMENT * weight * day_noise * random.uniform(0.5, 1.5)

                # Collection logic
                mov = 0
                if collecting:
                    collect_countdown -= 1
                    if collect_countdown <= 0:
                        fill = random.uniform(0, 5)
                        collecting = False
                        mov = 1  # movement detected during collection
                else:
                    fill += increment
                    if fill >= random.uniform(92, 100):
                        collecting = True
                        collect_countdown = random.randint(1, 6)  # 10-60 min delay

                fill = max(0, min(100, fill))
                percentage = int(round(fill))
                status = "FULL" if percentage >= 80 else "EMPTY"

                rows.append([
                    ts.strftime("%Y-%m-%d %H:%M:%S"),
                    bin_id,
                    percentage,
                    status,
                    mov,
                ])

    # Sort by timestamp so all bins are interleaved chronologically
    rows.sort(key=lambda r: r[0])
    return rows


def main():
    parser = argparse.ArgumentParser(description="Simulate bin fill data")
    parser.add_argument("--days", type=int, default=30, help="Number of days to simulate")
    parser.add_argument("--bins", type=int, default=3, help="Number of bins")
    parser.add_argument("--interval", type=int, default=10, help="Sample interval in minutes")
    parser.add_argument("--out", type=str, default="../training_data.csv", help="Output CSV path")
    args = parser.parse_args()

    rows = simulate(num_bins=args.bins, num_days=args.days, interval_min=args.interval)

    with open(args.out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["Timestamp", "Bin ID", "Percentage", "Status", "Movement"])
        writer.writerows(rows)

    print(f"Generated {len(rows)} rows for {args.bins} bins over {args.days} days → {args.out}")


if __name__ == "__main__":
    main()
