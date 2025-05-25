import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(layout="wide")
st.title("🔆 バージョン6.1：発電量可視化（棒グラフ＋24hカーブ）")

# --- サイドバー：パラメータ ---
st.sidebar.header("🔧 発電パラメータ設定（JIS準拠）")
K = st.sidebar.number_input("K（係数）", value=0.95)
PAS = st.sidebar.number_input("PAS（受光面積 m²）", value=10.0)
GS = st.sidebar.number_input("GS（基準日射量）[kWh/m²]", value=1.0)
alpha = st.sidebar.number_input("αpmax（[%/℃]）", value=-0.35) / 100
delta_T = st.sidebar.number_input("ΔT（℃）", value=25.0)

uploaded_file = st.file_uploader("NEDO形式CSVファイルをアップロードしてください", type="csv")

if uploaded_file:
    # --- データ読み込み ---
    df = pd.read_csv(uploaded_file, header=None, skiprows=1, encoding="shift_jis")
    time_labels = [f"{h}時" for h in range(1, 25)]
    df.columns = (
        ["要素番号", "月", "日", "年"]
        + time_labels
        + ["最大", "最小", "積算", "平均", "通算日"]
    )

    # --- 抽出 ---
    df_solar = df[df["要素番号"] == 1].copy()
    df_temp = df[df["要素番号"] == 5].copy()

    # --- 各時間の単位変換と整形 ---
    solar_data = {}
    temp_data = {}
    for h in time_labels:
        solar_data[h] = pd.to_numeric(df_solar[h], errors="coerce").reset_index(drop=True) * 0.01 / 3.6
        temp_data[h] = pd.to_numeric(df_temp[h], errors="coerce").reset_index(drop=True) * 0.1

    df_hourly = pd.DataFrame({
        "月": df_solar["月"].reset_index(drop=True),
        "日": df_solar["日"].reset_index(drop=True)
    })

    for h in time_labels:
        df_hourly[h] = K * PAS * solar_data[h] * (1 + alpha * (temp_data[h] + delta_T)) / GS

    df_hourly["日発電量 [kWh]"] = df_hourly[time_labels].sum(axis=1)
    eph_monthly_calc = df_hourly.groupby("月")["日発電量 [kWh]"].sum().reset_index()
    eph_monthly_calc.columns = ["月", "積分値（補正前）"]

    # --- 発電量①（基準値） ---
    df_solar["日積算 [kWh/m²]"] = df_solar[time_labels].apply(pd.to_numeric, errors="coerce").sum(axis=1) * 0.01 / 3.6
    df_temp["日平均気温 [℃]"] = df_temp[time_labels].apply(pd.to_numeric, errors="coerce").mean(axis=1) * 0.1
    ham = df_solar.groupby("月")["日積算 [kWh/m²]"].sum().reset_index()
    tam = df_temp.groupby("月")["日平均気温 [℃]"].mean().reset_index()
    df_monthly1 = pd.merge(ham, tam, on="月")
    df_monthly1["発電量① [kWh]"] = K * PAS * df_monthly1["日積算 [kWh/m²]"] * (1 + alpha * delta_T) / GS

    # --- 補正係数計算 ---
    df_monthly2 = eph_monthly_calc.copy()
    df_monthly2 = pd.merge(df_monthly2, df_monthly1[["月", "発電量① [kWh]"]], on="月")
    df_monthly2["補正係数"] = df_monthly2["発電量① [kWh]"] / df_monthly2["積分値（補正前）"]

    # --- 補正後発電量データ作成 ---
    df_hourly["補正係数"] = df_hourly["月"].map(df_monthly2.set_index("月")["補正係数"])
    for h in time_labels:
        df_hourly[f"{h}_補正後"] = df_hourly[h] * df_hourly["補正係数"]

    # --- 📊 月別発電量グラフ ---
    st.subheader("📊 月別発電量（発電量① vs 補正済②）")
    bar_df = df_monthly2.rename(columns={
        "発電量① [kWh]": "発電量①（基準）",
        "積分値（補正前）": "発電量②（積分値）"
    })
    fig_bar = px.bar(bar_df, x="月", y=["発電量①（基準）", "発電量②（積分値）"],
                     barmode="group", labels={"value": "発電量[kWh]", "variable": "種類"})
    st.plotly_chart(fig_bar, use_container_width=True)

    # --- 📅 任意日選択（月＋日） ---
    st.subheader("📈 任意日の24時間発電量カーブ（補正後）")
    month_selected = st.selectbox("月を選択", sorted(df_hourly["月"].unique()))
    day_selected = st.selectbox("日を選択", sorted(df_hourly[df_hourly["月"] == month_selected]["日"].unique()))

    df_day = df_hourly[(df_hourly["月"] == month_selected) & (df_hourly["日"] == day_selected)]
    if not df_day.empty:
        hourly_corrected = df_day[[f"{h}_補正後" for h in time_labels]].iloc[0]
        df_plot = pd.DataFrame({
            "時刻": list(range(1, 25)),
            "発電量（補正後）[kWh]": hourly_corrected.values
        })

        fig_line = px.line(df_plot, x="時刻", y="発電量（補正後）[kWh]", markers=True)
        fig_line.update_layout(xaxis=dict(dtick=1))
        st.plotly_chart(fig_line, use_container_width=True)
