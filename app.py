import io

import pandas as pd
import streamlit as st

from analysis import analyze, clean, sample_data

st.set_page_config(page_title="Bilet Fiyat Analizi", page_icon="✈️", layout="wide")
st.title("✈️ Bilet Fiyatı Analizi")
st.caption("Kalkışa kaç gün kala bilet almak en ucuz? Şehir bazında analiz.")

src = st.sidebar.radio("Veri kaynağı", ["Elle gir", "CSV yükle", "Demo veri (gerçek değil)"])

if src == "Elle gir":
    st.subheader("Fiyatları gir")
    base = pd.DataFrame({"city": ["Berlin"] * 4, "days_before": [7, 14, 21, 30], "price": [0.0] * 4})
    df_raw = st.data_editor(base, num_rows="dynamic", use_container_width=True)
elif src == "CSV yükle":
    up = st.sidebar.file_uploader("CSV (city, days_before, price)", type="csv")
    st.sidebar.download_button(
        "Örnek şablon indir",
        sample_data("Berlin").head(8).to_csv(index=False),
        "sablon.csv",
    )
    df_raw = pd.read_csv(io.BytesIO(up.getvalue())) if up else None
else:
    df_raw = pd.concat([sample_data("Berlin", 1), sample_data("Roma", 2), sample_data("Paris", 3)])
    st.warning("Bu veriler simülasyondur; gerçek fiyatları temsil etmez.")

if df_raw is None:
    st.info("Başlamak için veri yükle.")
    st.stop()

try:
    df = clean(df_raw)
except ValueError as e:
    st.error(str(e))
    st.stop()

if df.empty:
    st.info("Geçerli satır yok. Fiyatları gir (price > 0).")
    st.stop()

cities = sorted(df["city"].unique())
city = st.selectbox("Şehir", cities)
d = df[df["city"] == city]
res = analyze(d)

c1, c2, c3 = st.columns(3)
c1.metric("En uygun aralık", res["best_window"], f"medyan {res['best_median']:.0f}")
c2.metric("Genele göre tasarruf", f"%{res['saving_vs_overall_pct']:.1f}")
if "saving_vs_last_minute_pct" in res:
    c3.metric("Son dakikaya göre tasarruf", f"%{res['saving_vs_last_minute_pct']:.1f}")

bd = res["best_day"]
st.success(
    f"**{city}:** En ucuz aralık **{res['best_window']}** önce almak. "
    f"Tek gün olarak en düşük: **{bd['day']} gün** önce (medyan {bd['price']:.0f})."
)
if res["low_data"]:
    st.warning("Gözlem sayısı az; sonuç güvenilir olmayabilir. Daha fazla fiyat gir.")

st.subheader("Kalan güne göre fiyat")
daily = d.groupby("days_before")["price"].median().sort_index()
st.line_chart(daily)

st.subheader("Aralık özeti")
st.dataframe(
    res["windows"].rename(columns={"window": "aralık", "count": "gözlem", "mean": "ortalama", "median": "medyan", "min": "en düşük"}),
    use_container_width=True,
    hide_index=True,
)

if len(cities) > 1:
    st.subheader("Şehir karşılaştırması")
    rows = []
    for c in cities:
        r = analyze(df[df["city"] == c])
        rows.append({"şehir": c, "en uygun aralık": r["best_window"], "medyan": round(r["best_median"], 1),
                     "tasarruf %": round(r["saving_vs_overall_pct"], 1)})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
