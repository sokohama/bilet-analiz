"""Bilet fiyatı analizi: kalkışa kaç gün kala almak en ucuz?

Girdi: şehir, days_before (kalkışa kalan gün), price sütunlarına sahip tablo.
"""
import numpy as np
import pandas as pd

# (alt sınır, üst sınır, etiket) - gün aralıkları
WINDOWS = [
    (0, 3, "0-3 gün"),
    (4, 7, "4-7 gün"),
    (8, 14, "8-14 gün"),
    (15, 21, "15-21 gün"),
    (22, 30, "22-30 gün"),
    (31, 60, "31-60 gün"),
    (61, 90, "61-90 gün"),
    (91, 120, "91-120 gün"),
    (121, 180, "121-180 gün"),
    (181, 10_000, "181+ gün"),
]


def _label(d: float) -> str:
    for lo, hi, name in WINDOWS:
        if lo <= d <= hi:
            return name
    return "?"


def from_prices(city: str, snapshot, prices: pd.DataFrame) -> pd.DataFrame:
    """Tarih/fiyat tablosunu (date, price) analiz formatına çevirir.

    days_before = kalkış tarihi - snapshot (fotoğrafın çekildiği gün).
    """
    d = prices.copy()
    d.columns = [str(c).strip().lower() for c in d.columns]
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["price"] = pd.to_numeric(d["price"], errors="coerce")
    d = d.dropna(subset=["date", "price"])
    snap = pd.Timestamp(snapshot)
    d["days_before"] = (d["date"] - snap).dt.days
    d["city"] = city
    d["snapshot_date"] = snap.date()
    d["depart_date"] = d["date"].dt.date
    return d[["city", "snapshot_date", "depart_date", "days_before", "price"]].reset_index(drop=True)


def clean(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    for col in ("city", "days_before", "price"):
        if col not in df.columns:
            raise ValueError(f"Eksik sütun: {col}")
    df["city"] = df["city"].astype(str).str.strip()
    df["days_before"] = pd.to_numeric(df["days_before"], errors="coerce")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["city", "days_before", "price"])
    df = df[(df["days_before"] >= 0) & (df["price"] > 0)]
    return df


def by_window(df_city: pd.DataFrame) -> pd.DataFrame:
    d = df_city.copy()
    d["window"] = d["days_before"].map(_label)
    order = [w[2] for w in WINDOWS]
    g = d.groupby("window")["price"].agg(["count", "mean", "median", "min"]).reset_index()
    g["window"] = pd.Categorical(g["window"], categories=order, ordered=True)
    return g.sort_values("window").reset_index(drop=True)


def best_day(df_city: pd.DataFrame) -> dict:
    """Gün bazında medyan fiyatı en düşük olan günü bulur (eşitlikte en yakın gün)."""
    daily = df_city.groupby("days_before")["price"].median().sort_index()
    day = int(daily.idxmin())
    return {"day": day, "price": float(daily.loc[day])}


def analyze(df_city: pd.DataFrame) -> dict:
    """Bir şehir için özet ve öneri üretir."""
    win = by_window(df_city)
    if len(win) == 0:
        raise ValueError("Veri yok")
    best = win.loc[win["median"].idxmin()]
    worst = win.loc[win["median"].idxmax()]
    last_minute = win[win["window"] == "0-3 gün"]
    overall = float(df_city["price"].median())
    saving_vs_overall = (overall - best["median"]) / overall * 100
    result = {
        "best_window": str(best["window"]),
        "best_median": float(best["median"]),
        "worst_window": str(worst["window"]),
        "worst_median": float(worst["median"]),
        "overall_median": overall,
        "saving_vs_overall_pct": float(saving_vs_overall),
        "saving_vs_worst_pct": float((worst["median"] - best["median"]) / worst["median"] * 100),
        "n_obs": int(len(df_city)),
        "best_day": best_day(df_city),
        "windows": win,
    }
    if len(last_minute):
        lm = float(last_minute["median"].iloc[0])
        result["saving_vs_last_minute_pct"] = float((lm - best["median"]) / lm * 100)
    result["low_data"] = len(df_city) < 15 or int(best["count"]) < 3
    return result


def sample_data(city: str = "Berlin", seed: int = 7) -> pd.DataFrame:
    """SADECE DEMO: gerçek veri değildir. Tipik 'U' şeklinde bir eğri simüle eder."""
    rng = np.random.default_rng(seed)
    days = np.array([1, 2, 3, 5, 7, 10, 14, 17, 21, 25, 30, 35, 45, 60, 75, 90])
    base = 105 + 0.12 * (28 - days) ** 2 / 4 * (days < 28) + 0.5 * np.maximum(days - 60, 0)
    rows = []
    for d, b in zip(days, base):
        for _ in range(3):
            rows.append({"city": city, "days_before": int(d), "price": round(float(b * rng.normal(1, 0.06)), 2)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    df = clean(sample_data("Berlin"))
    r = analyze(df)
    print(r["windows"].to_string(index=False))
    print({k: v for k, v in r.items() if k != "windows"})
