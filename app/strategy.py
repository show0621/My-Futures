from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf


class DataProvider:
    """抓取行情資料，抓不到時回傳 mock，讓頁面不中斷。"""

    def __init__(self, symbol: str = "^TWII") -> None:
        self.symbol = symbol

    @staticmethod
    def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
        # yfinance 可能回傳 MultiIndex columns，先壓平
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
        return df

    def fetch_bars(self, interval: str, period: str) -> pd.DataFrame:
        try:
            df = yf.download(
                tickers=self.symbol,
                interval=interval,
                period=period,
                auto_adjust=False,
                progress=False,
                threads=False,
            )
            df = self._normalize_columns(df)
        except Exception:
            return self._mock_data(interval)

        if df.empty:
            return self._mock_data(interval)

        df = df.rename(
            columns={
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )
        keep_cols = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
        out = df[keep_cols].copy()
        out.index = pd.to_datetime(out.index, utc=True)
        out = out.sort_index()
        return out

    def _mock_data(self, interval: str) -> pd.DataFrame:
        steps = 700 if interval in {"30m", "60m"} else 500
        freq = "30min" if interval == "30m" else "60min" if interval == "60m" else "1D"
        idx = pd.date_range(end=datetime.now(timezone.utc), periods=steps, freq=freq)

        trend = np.linspace(0, 40, steps)
        noise = np.random.randn(steps) * 6
        seed = 20000 + trend + np.cumsum(noise)

        df = pd.DataFrame(index=idx)
        df["close"] = seed
        df["open"] = df["close"].shift(1).fillna(df["close"])
        df["high"] = np.maximum(df["open"], df["close"]) + np.random.rand(steps) * 8
        df["low"] = np.minimum(df["open"], df["close"]) - np.random.rand(steps) * 8
        df["volume"] = np.random.randint(1200, 8000, size=steps)
        return df


class TrendSignalEngine:
    def __init__(self, force_exit_days: int = 7, stop_loss_pct: float = 0.10, trailing_pct: float = 0.04) -> None:
        self.force_exit_days = force_exit_days
        self.stop_loss_pct = stop_loss_pct
        self.trailing_pct = trailing_pct

    @staticmethod
    def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
        delta = series.diff()
        gain = delta.where(delta > 0, 0.0)
        loss = -delta.where(delta < 0, 0.0)
        avg_gain = gain.rolling(period).mean()
        avg_loss = loss.rolling(period).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - (100 / (1 + rs))

    def build_features(self, bars: pd.DataFrame) -> pd.DataFrame:
        df = bars.copy()
        df["ema_fast"] = df["close"].ewm(span=12).mean()
        df["ema_slow"] = df["close"].ewm(span=34).mean()
        df["mom"] = df["close"].pct_change(10)
        df["rsi"] = self._rsi(df["close"])

        df["signal"] = "HOLD"
        long_rule = (df["ema_fast"] > df["ema_slow"]) & (df["mom"] > 0) & (df["rsi"] > 55)
        short_rule = (df["ema_fast"] < df["ema_slow"]) & (df["mom"] < 0) & (df["rsi"] < 45)
        df.loc[long_rule, "signal"] = "LONG"
        df.loc[short_rule, "signal"] = "SHORT"
        return df


class PaperTrader:
    def __init__(self, engine: TrendSignalEngine, initial_cash: float = 1_000_000) -> None:
        self.engine = engine
        self.initial_cash = initial_cash
        self.reset()

    def reset(self) -> None:
        self.cash = self.initial_cash
        self.position = 0
        self.entry_price: float | None = None
        self.entry_time: datetime | None = None
        self.trailing_anchor: float | None = None
        self.trade_log: list[dict[str, Any]] = []

    def _close(self, when: datetime, price: float, reason: str) -> None:
        if self.position == 0 or self.entry_price is None:
            return

        pnl_ratio = (price - self.entry_price) / self.entry_price
        if self.position == -1:
            pnl_ratio = -pnl_ratio

        self.cash *= 1 + pnl_ratio
        self.trade_log.append(
            {
                "time": when.isoformat(),
                "action": "CLOSE",
                "side": "LONG" if self.position == 1 else "SHORT",
                "price": round(price, 2),
                "pnl_ratio": round(float(pnl_ratio), 4),
                "cash": round(float(self.cash), 2),
                "reason": reason,
            }
        )

        self.position = 0
        self.entry_price = None
        self.entry_time = None
        self.trailing_anchor = None

    def _open(self, when: datetime, price: float, side: int) -> None:
        if self.position != 0:
            return

        self.position = side
        self.entry_price = price
        self.entry_time = when
        self.trailing_anchor = price
        self.trade_log.append(
            {
                "time": when.isoformat(),
                "action": "OPEN",
                "side": "LONG" if side == 1 else "SHORT",
                "price": round(price, 2),
                "cash": round(float(self.cash), 2),
                "reason": "signal",
            }
        )

    def step(self, when: datetime, price: float, signal: str) -> None:
        if self.position == 1 and self.trailing_anchor is not None:
            self.trailing_anchor = max(self.trailing_anchor, price)
        elif self.position == -1 and self.trailing_anchor is not None:
            self.trailing_anchor = min(self.trailing_anchor, price)

        if self.position != 0 and self.entry_price and self.entry_time:
            held_days = (when - self.entry_time).total_seconds() / 86400
            if held_days >= self.engine.force_exit_days:
                self._close(when, price, "force_7d")
                return

            if self.position == 1:
                if price <= self.entry_price * (1 - self.engine.stop_loss_pct):
                    self._close(when, price, "stop_loss_10pct")
                    return
                if self.trailing_anchor and price <= self.trailing_anchor * (1 - self.engine.trailing_pct):
                    self._close(when, price, "trailing_take_profit")
                    return
            else:
                if price >= self.entry_price * (1 + self.engine.stop_loss_pct):
                    self._close(when, price, "stop_loss_10pct")
                    return
                if self.trailing_anchor and price >= self.trailing_anchor * (1 + self.engine.trailing_pct):
                    self._close(when, price, "trailing_take_profit")
                    return

        if self.position == 0:
            if signal == "LONG":
                self._open(when, price, 1)
            elif signal == "SHORT":
                self._open(when, price, -1)
        elif self.position == 1 and signal == "SHORT":
            self._close(when, price, "reverse")
            self._open(when, price, -1)
        elif self.position == -1 and signal == "LONG":
            self._close(when, price, "reverse")
            self._open(when, price, 1)

    def run_backtest(self, feature_df: pd.DataFrame) -> dict[str, Any]:
        self.reset()
        clean = feature_df.dropna(subset=["signal", "close"])

        if clean.empty:
            return {
                "initial_cash": self.initial_cash,
                "final_cash": round(float(self.cash), 2),
                "total_return_pct": 0.0,
                "close_count": 0,
                "win_rate_pct": 0.0,
                "trades": [],
            }

        for ts, row in clean.iterrows():
            self.step(ts.to_pydatetime(), float(row["close"]), str(row["signal"]))

        if self.position != 0:
            self._close(clean.index[-1].to_pydatetime(), float(clean["close"].iloc[-1]), "eod")

        closes = [t for t in self.trade_log if t["action"] == "CLOSE"]
        wins = [t for t in closes if t["pnl_ratio"] > 0]
        total_return = self.cash / self.initial_cash - 1

        return {
            "initial_cash": self.initial_cash,
            "final_cash": round(float(self.cash), 2),
            "total_return_pct": round(float(total_return * 100), 2),
            "close_count": len(closes),
            "win_rate_pct": round((len(wins) / len(closes) * 100), 2) if closes else 0.0,
            "trades": self.trade_log[-50:],
        }


class SignalService:
    def __init__(self, symbol: str = "^TWII") -> None:
        self.provider = DataProvider(symbol=symbol)
        self.engine = TrendSignalEngine()
        self.lock = Lock()
        self.latest_payload: dict[str, Any] = {}

    def _build_for_interval(self, interval: str, period: str) -> dict[str, Any]:
        bars = self.provider.fetch_bars(interval=interval, period=period)
        feats = self.engine.build_features(bars)
        last = feats.iloc[-1]

        trader = PaperTrader(engine=self.engine)
        backtest_summary = trader.run_backtest(feats)

        return {
            "interval": interval,
            "as_of": feats.index[-1].isoformat(),
            "latest_price": round(float(last["close"]), 2),
            "latest_signal": str(last["signal"]),
            "ema_fast": round(float(last["ema_fast"]), 2) if not pd.isna(last["ema_fast"]) else None,
            "ema_slow": round(float(last["ema_slow"]), 2) if not pd.isna(last["ema_slow"]) else None,
            "momentum": round(float(last["mom"] * 100), 2) if not pd.isna(last["mom"]) else None,
            "rsi": round(float(last["rsi"]), 2) if not pd.isna(last["rsi"]) else None,
            "backtest": backtest_summary,
        }

    def refresh(self) -> dict[str, Any]:
        with self.lock:
            payload = {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "symbol": self.provider.symbol,
                "rules": {
                    "force_exit_days": self.engine.force_exit_days,
                    "stop_loss_pct": self.engine.stop_loss_pct,
                    "trailing_pct": self.engine.trailing_pct,
                },
                # yfinance 30m/60m 只能抓近 60 天，日 K 才能拉長
                "timeframes": {
                    "30m": self._build_for_interval("30m", "59d"),
                    "60m": self._build_for_interval("60m", "729d"),
                    "1d": self._build_for_interval("1d", "10y"),
                },
            }
            self.latest_payload = payload
            return payload

    def get_latest(self, max_stale_min: int = 2) -> dict[str, Any]:
        if not self.latest_payload:
            return self.refresh()

        updated = datetime.fromisoformat(self.latest_payload["updated_at"])
        if datetime.now(timezone.utc) - updated > timedelta(minutes=max_stale_min):
            return self.refresh()
        return self.latest_payload
