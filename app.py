import os
from datetime import date, datetime

import pandas as pd
import streamlit as st

from analysis import analyze, clean, from_prices, sample_data
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
st.caption("Fiyat takviminin ekran görüntüsünü yükle; kaç gün önce almanın en ucuz olduğunu hesaplasın.")

mode = st.radio("Veri kaynağı", ["📷 Fotoğraf", "CSV", "Elle", "Demo"], horizontal=True)
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
                        res = extract_prices(f.getvalue(), f.type or "image/png", snap, key)
                    except ExtractError as e:
                        st.error(f"{f.name}: {e}")
                        continue
                    for r in res["prices"]:
                        merged[r["date"]] = r["price"]
                    for k in ("origin", "destination", "currency"):
                        if res.get(k) and not meta.get(k):
                            meta[k] = res[k]
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
            help="Aynı rotayı günler sonra tekrar fotoğraflayıp CSV'leri 'CSV' modunda birlikte yüklersen analiz güçlenir.",
        )

elif mode == "CSV":
    ups = st.file_uploader("CSV (city, days_before, price)", type="csv", accept_multiple_files=True)
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
city = st.selectbox("Şehir", cities) if len(cities) > 1 else cities[0]
d = df[df["city"] == city]
res = analyze(d)

st.metric("En uygun aralık", res["best_window"], f"medyan {res['best_median']:.0f}")
c1, c2 = st.columns(2)
c1.metric("Genele göre tasarruf", f"%{res['saving_vs_overall_pct']:.1f}")
if "saving_vs_last_minute_pct" in res:
    c2.metric("Son dakikaya göre tasarruf", f"%{res['saving_vs_last_minute_pct']:.1f}")

bd = res["best_day"]
st.success(
    f"**{city}:** en ucuz aralık kalkıştan **{res['best_window']}** önce. "
    f"Tek gün olarak en düşük: **{bd['day']} gün** önce (medyan {bd['price']:.0f})."
)
if res["low_data"]:
    st.warning("Gözlem sayısı az; sonuç güvenilir olmayabilir.")
if photo_mode:
    st.caption(
        "Not: Tek fotoğraf, 'bugün alırsam' kalkışa kalan gün sayısına göre fiyatı gösterir. "
        "Hafta içi/sonu ve tatil dönemleri de fiyatı etkiler; aynı rotayı günler içinde tekrar "
        "fotoğraflarsan sonuç daha güvenilir olur."
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
    st.subheader("Şehir karşılaştırması")
    rows_c = []
    for c in cities:
        r = analyze(df[df["city"] == c])
        rows_c.append(
            {
                "şehir": c,
                "en uygun aralık": r["best_window"],
                "medyan": round(r["best_median"], 1),
                "tasarruf %": round(r["saving_vs_overall_pct"], 1),
            }
        )
    st.dataframe(pd.DataFrame(rows_c), hide_index=True)
