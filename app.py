import os
from datetime import date, datetime

import pandas as pd
import streamlit as st

from analysis import (
    analyze,
    cheapest_dates,
    clean,
    fmt_date,
    from_prices,
    recommend,
    sample_data,
    weekday_stats,
)
from extract import ExtractError, extract_prices


def today_local() -> date:
    """Bugünün tarihi (Bakü saati); sunucu saati UTC olsa bile doğru gün gelir."""
    try:
        from zoneinfo import ZoneInfo

        return datetime.now(ZoneInfo("Asia/Baku")).date()
    except Exception:
        return date.today()


def get_key():
    try:
        k = st.secrets.get("ANTHROPIC_API_KEY")
    except Exception:
        k = None
    return k or os.environ.get("ANTHROPIC_API_KEY")


st.set_page_config(page_title="Bilet Fiyat Analizi", page_icon="✈️")
st.title("✈️ Bilet Fiyat Analizi")
st.caption("Fiyat takvimini yükle; kaç gün önce, hangi gün ve ne kadara almanın en ucuz olduğunu hesaplasın.")

mode = st.radio("Veri kaynağı", ["CSV", "📷 Fotoğraf", "Elle", "Demo"], horizontal=True)
df_raw = None
photo_mode = False

if mode == "📷 Fotoğraf":
    photo_mode = True
    city_in = st.text_input("Şehir / rota", placeholder="Örn. Bakü → İstanbul")
    snap = st.date_input("Bugünün tarihi", value=today_local())
    files = st.file_uploader(
        "Takvim ekran görüntüsü (birden fazla seçebilirsin)",
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
    )
    key = get_key()
    if not key:
        key = st.text_input(
            "Anthropic API anahtarı",
            type="password",
            help="Fotoğrafı okumak için gerekli. Kalıcı olması için Streamlit 'Secrets' bölümüne ANTHROPIC_API_KEY olarak ekle.",
        )

    if st.button("Fiyatları oku", disabled=not files):
        if not key:
            st.error("Önce API anahtarını gir.")
        else:
            merged, meta = {}, {}
            with st.spinner("Fotoğraf okunuyor..."):
                for f in files:
                    try:
                        res_x = extract_prices(f.getvalue(), f.type or "image/png", snap, key)
                    except ExtractError as e:
                        st.error(f"{f.name}: {e}")
                        continue
                    for r in res_x["prices"]:
                        merged[r["date"]] = r["price"]
                    for k in ("origin", "destination", "currency"):
                        if res_x.get(k) and not meta.get(k):
                            meta[k] = res_x[k]
            if merged:
                st.session_state["photo_rows"] = pd.DataFrame(
                    [{"date": d, "price": p} for d, p in sorted(merged.items())]
                )
                st.session_state["photo_meta"] = meta
                st.session_state["photo_snap"] = snap

    rows = st.session_state.get("photo_rows")
    if rows is not None:
        meta = st.session_state.get("photo_meta", {})
        snap_used = st.session_state["photo_snap"]
        st.subheader("Okunan fiyatlar")
        st.caption(f"Hesapta bugün = {snap_used:%d.%m.%Y}. Yanlış okunan varsa buradan düzelt.")
        edited = st.data_editor(
            rows,
            num_rows="dynamic",
            key="photo_editor",
            column_config={
                "date": st.column_config.DateColumn("Kalkış tarihi", format="DD.MM.YYYY"),
                "price": st.column_config.NumberColumn("Fiyat", min_value=0),
            },
        )
        route = f"{meta['origin']} → {meta['destination']}" if meta.get("origin") and meta.get("destination") else ""
        label = city_in.strip() or route or "Rota"
        if meta.get("currency"):
            st.caption(f"Para birimi: {meta['currency']}")
        df_raw = from_prices(label, snap_used, edited)
        st.download_button(
            "Bu veriyi CSV olarak indir",
            df_raw.to_csv(index=False),
            f"bilet_{snap_used:%Y%m%d}.csv",
            help="Aynı rotayı günler sonra tekrar kaydedip CSV'leri 'CSV' modunda birlikte yüklersen analiz güçlenir.",
        )

elif mode == "CSV":
    ups = st.file_uploader(
        "CSV dosyaları (her rota için bir dosya; birden fazla seçebilirsin)",
        type="csv",
        accept_multiple_files=True,
    )
    if ups:
        df_raw = pd.concat([pd.read_csv(u) for u in ups], ignore_index=True)

elif mode == "Elle":
    base = pd.DataFrame({"city": ["Berlin"] * 4, "days_before": [7, 14, 21, 30], "price": [0.0] * 4})
    df_raw = st.data_editor(base, num_rows="dynamic")

else:
    df_raw = pd.concat([sample_data("Berlin", 1), sample_data("Roma", 2), sample_data("Paris", 3)])
    st.warning("Bu veriler simülasyondur; gerçek fiyatları temsil etmez.")

if df_raw is None:
    st.info("Başlamak için veri ekle.")
    st.stop()

try:
    df = clean(df_raw)
except ValueError as e:
    st.error(str(e))
    st.stop()

if df.empty:
    st.info("Geçerli satır yok.")
    st.stop()

st.divider()
cities = sorted(df["city"].unique())
city = st.selectbox("Rota / şehir", cities) if len(cities) > 1 else cities[0]
d = df[df["city"] == city]
res = analyze(d)
cd = cheapest_dates(d, 5)
wd = weekday_stats(d)

# --- Özet ---
st.metric("En uygun alım aralığı", res["best_window"], f"medyan {res['best_median']:.0f}", delta_color="off")
if cd is not None:
    mn = cd.iloc[0]
    st.metric(
        "En düşük fiyat",
        f"{mn['price']:.0f}",
        f"{fmt_date(mn['depart_dt'])} ({mn['weekday']}) · {int(mn['days_before'])} gün kala",
        delta_color="off",
    )
else:
    bd = res["best_day"]
    st.metric("En düşük fiyat", f"{bd['price']:.0f}", f"kalkışa {bd['day']} gün kala", delta_color="off")
c1, c2 = st.columns(2)
c1.metric("Genele göre tasarruf", f"%{res['saving_vs_overall_pct']:.1f}")
if "saving_vs_last_minute_pct" in res:
    c2.metric("Son dakikaya göre tasarruf", f"%{res['saving_vs_last_minute_pct']:.1f}")

if res["low_data"]:
    st.warning("Gözlem sayısı az; sonuç güvenilir olmayabilir.")

# --- Tavsiye ---
st.subheader("💡 Ne zaman almak mantıklı?")
for tip in recommend(d, res, wd):
    st.markdown(f"- {tip}")

# --- En ucuz günler ---
if cd is not None:
    st.subheader("En ucuz 5 kalkış günü")
    st.dataframe(
        pd.DataFrame(
            {
                "tarih": [fmt_date(x) for x in cd["depart_dt"]],
                "gün": cd["weekday"],
                "fiyat": cd["price"].round(0).astype(int),
                "kalkışa kalan gün": cd["days_before"].astype(int),
            }
        ),
        hide_index=True,
    )

# --- Haftanın günü ---
if wd is not None:
    st.subheader("Haftanın gününe göre fiyat")
    st.caption("Kalkış gününe göre. 'Fark %' = o günün fiyatının çevresindeki ~2 haftalık fiyat düzeyine göre farkı (eksi = daha ucuz).")
    st.dataframe(
        pd.DataFrame(
            {
                "gün": wd["weekday"],
                "gözlem": wd["n"],
                "medyan fiyat": wd["median"].round(0).astype(int),
                "fark %": ((wd["rel"] - 1) * 100).round(0).astype(int),
            }
        ),
        hide_index=True,
    )
elif cd is None:
    st.caption("Haftanın günü analizi için kalkış tarihi gerekir (fotoğraf modu veya tarih sütunlu CSV).")

if photo_mode:
    st.caption(
        "Not: Tek fotoğraf, 'bugün alırsam' kalkışa kalan gün sayısına göre fiyatı gösterir. "
        "Aynı rotayı günler içinde tekrar kaydedersen sonuç daha güvenilir olur."
    )

st.subheader("Kalan güne göre fiyat")
daily = d.groupby("days_before")["price"].median().sort_index()
st.line_chart(daily)

st.subheader("Aralık özeti")
st.dataframe(
    res["windows"].rename(
        columns={"window": "aralık", "count": "gözlem", "mean": "ortalama", "median": "medyan", "min": "en düşük"}
    ),
    hide_index=True,
)

if len(cities) > 1:
    st.subheader("Rota karşılaştırması")
    rows_c = []
    for c in cities:
        dc = df[df["city"] == c]
        r = analyze(dc)
        cdc = cheapest_dates(dc, 1)
        row = {"rota": c, "en uygun aralık": r["best_window"], "medyan": round(r["best_median"], 1)}
        if cdc is not None:
            row["en düşük fiyat"] = int(cdc.iloc[0]["price"])
            row["tarihi"] = fmt_date(cdc.iloc[0]["depart_dt"])
        rows_c.append(row)
    st.dataframe(pd.DataFrame(rows_c), hide_index=True)
