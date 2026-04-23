from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st
from streamlit_autorefresh import st_autorefresh

from app.strategy import SignalService

st.set_page_config(page_title="台指期波段監控", layout="wide")
st.title("台指期動能趨勢監控（30分K / 60分K / 日K）")

if "service" not in st.session_state:
    st.session_state.service = SignalService(symbol="^TWII")

service: SignalService = st.session_state.service

col1, col2, col3 = st.columns([1, 1, 2])
with col1:
    auto_refresh = st.toggle("自動更新（每60秒）", value=True)
with col2:
    force = st.button("立即刷新")
with col3:
    st.caption("規則：7天強平 / 停損10% / 動態追蹤停利")

if auto_refresh:
    st_autorefresh(interval=60_000, key="refresh_60s")

try:
    payload = service.refresh() if force else service.get_latest()
except Exception as exc:
    st.error(f"資料更新失敗：{exc}")
    st.stop()

st.write(
    f"標的：`{payload['symbol']}` | 更新時間（UTC）：{datetime.fromisoformat(payload['updated_at']).strftime('%Y-%m-%d %H:%M:%S')}"
)

frames = payload["timeframes"]
cols = st.columns(3)

for idx, key in enumerate(["30m", "60m", "1d"]):
    frame = frames[key]
    backtest = frame["backtest"]

    with cols[idx]:
        st.subheader(f"{key} 訊號")
        st.metric("最新訊號", frame["latest_signal"])
        st.metric("最新價格", frame["latest_price"])
        st.caption(f"EMA12: {frame['ema_fast']} / EMA34: {frame['ema_slow']}")
        st.caption(f"Momentum(10): {frame['momentum']}% / RSI: {frame['rsi']}")
        st.caption(f"K棒時間: {frame['as_of']}")

        st.markdown("**回測摘要**")
        st.write(
            {
                "initial_cash": backtest["initial_cash"],
                "final_cash": backtest["final_cash"],
                "total_return_pct": backtest["total_return_pct"],
                "win_rate_pct": backtest["win_rate_pct"],
                "close_count": backtest["close_count"],
            }
        )

st.divider()
st.subheader("最近交易紀錄（1d）")
trades = frames["1d"]["backtest"].get("trades", [])
if not trades:
    st.info("目前沒有交易紀錄")
else:
    st.dataframe(pd.DataFrame(trades).tail(20), use_container_width=True)

st.caption("⚠️ 目前為研究/教學用途，不構成投資建議。")
