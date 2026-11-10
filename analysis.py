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


WEEKDAYS = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]
MONTHS_TR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]


def fmt_date(ts) -> str:
    ts = pd.Timestamp(ts)
    return f"{ts.day} {MONTHS_TR[ts.month - 1]} {ts.year}"


def with_dates(df):
    """Kalkış tarihini (depart_dt) ekler; tarih bilgisi yoksa None döner."""
    d = df.copy()
    dt = None
    if "depart_date" in d.columns:
        dt = pd.to_datetime(d["depart_date"], errors="coerce")
    if (dt is None or dt.isna().all()) and "snapshot_date" in d.columns:
        dt = pd.to_datetime(d["snapshot_date"], errors="coerce") + pd.to_timedelta(d["days_before"], unit="D")
    if dt is None:
        return None
    d["depart_dt"] = dt
    d = d.dropna(subset=["depart_dt"])
    return d if len(d) else None


def cheapest_dates(df_city: pd.DataFrame, k: int = 5):
    """En düşük fiyatlı k kalkış tarihi (tarih, fiyat, kalan gün, haftanın günü)."""
    d = with_dates(df_city)
    if d is None:
        return None
    d = d.sort_values(["price", "days_before"]).drop_duplicates("depart_dt").head(k)
    d = d[["depart_dt", "price", "days_before"]].copy()
    d["weekday"] = d["depart_dt"].dt.dayofweek.map(lambda i: WEEKDAYS[i])
    return d.reset_index(drop=True)


def weekday_stats(df_city: pd.DataFrame):
    """Kalkış gününe (haftanın günü) göre fiyat.

    'rel' = fiyatın, çevresindeki ~15 günlük medyan fiyata oranı. Böylece tatil/sezon
    etkisi azalır ve gerçekten hafta günü farkı ölçülür (1.00 = çevresiyle aynı).
    """
    d = with_dates(df_city)
    if d is None or len(d) < 14:
        return None
    d = d.sort_values("depart_dt")
    s = d.set_index("depart_dt")["price"]
    local = s.rolling("15D", center=True, min_periods=5).median()
    d = d.assign(rel=s.to_numpy() / local.to_numpy(), wd=d["depart_dt"].dt.dayofweek.to_numpy())
    d = d.dropna(subset=["rel"])
    if d.empty:
        return None
    g = d.groupby("wd").agg(n=("price", "size"), median=("price", "median"), rel=("rel", "median"))
    g = g.reindex(range(7)).dropna(subset=["n"])
    g["weekday"] = [WEEKDAYS[i] for i in g.index]
    g["n"] = g["n"].astype(int)
    return g.reset_index(drop=True)[["weekday", "n", "median", "rel"]]


def lead_range(win: pd.DataFrame, tol: float = 0.10, min_n: int = 5):
    """En ucuz aralık ve medyanı %tol içinde olan komşu aralıklar -> (etiketler, alt, üst, medyan)."""
    w = win[win["count"] >= min_n].reset_index(drop=True)
    if w.empty:
        w = win.reset_index(drop=True)
    bi = int(w["median"].idxmin())
    limit = w.loc[bi, "median"] * (1 + tol)
    lo_i = hi_i = bi
    while lo_i > 0 and w.loc[lo_i - 1, "median"] <= limit:
        lo_i -= 1
    while hi_i < len(w) - 1 and w.loc[hi_i + 1, "median"] <= limit:
        hi_i += 1
    bounds = {name: (lo, hi) for lo, hi, name in WINDOWS}
    labels = [str(x) for x in w.loc[lo_i:hi_i, "window"]]
    return labels, bounds[labels[0]][0], bounds[labels[-1]][1], float(w.loc[bi, "median"])


def recommend(df_city: pd.DataFrame, res: dict, wd=None) -> list:
    """Veriden 'ne zaman almak mantıklı' önerileri üretir (Markdown metin listesi)."""
    tips = []
    labels, lo, hi, best_med = lead_range(res["windows"])
    rng = f"{lo}+ gün" if hi >= 10_000 else f"{lo}-{hi} gün"
    pct = res.get("saving_vs_last_minute_pct")
    extra = f"; son dakikaya (0-3 gün) göre yaklaşık %{pct:.0f} daha ucuz" if pct and pct > 1 else ""
    tips.append(f"**Alım zamanı:** Kalkıştan **{rng}** önce almak en uygun görünüyor (medyan fiyat {best_med:.0f}{extra}).")

    d = with_dates(df_city)
    if d is not None:
        sub = d[(d["days_before"] >= lo) & (d["days_before"] <= hi)]
        if len(sub):
            r = sub.sort_values(["price", "days_before"]).iloc[0]
            tips.append(
                f"**Şu anki en iyi seçenek:** bu aralıktaki en ucuz tarih **{fmt_date(r['depart_dt'])} "
                f"({WEEKDAYS[r['depart_dt'].dayofweek]})**, fiyat **{r['price']:.0f}** "
                f"(bugünden {int(r['days_before'])} gün sonra)."
            )

    if wd is not None:
        ok = wd[wd["n"] >= 4]
        if len(ok) >= 3:
            b = ok.loc[ok["rel"].idxmin()]
            w = ok.loc[ok["rel"].idxmax()]
            if w["rel"] - b["rel"] >= 0.10:
                tips.append(
                    f"**Kalkış günü:** {b['weekday']} en ucuz, {w['weekday']} en pahalı gün. Tarihin esnekse "
                    f"{b['weekday']} günü uçmayı dene (çevresindeki günlere göre yaklaşık "
                    f"%{abs(1 - b['rel']) * 100:.0f} fark)."
                )
            else:
                tips.append("**Kalkış günü:** haftanın günleri arasında belirgin bir fark yok; tarih seçerken en ucuz tarihlere bak.")

    tips.append(
        "**Not:** Bu analiz tek günlük bir fiyat görüntüsüne dayanıyor ve mevsim etkisini tam ayıramaz. "
        "Aynı rotayı birkaç hafta boyunca tekrar kaydedersen öneri güvenilirleşir."
    )
    return tips


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
