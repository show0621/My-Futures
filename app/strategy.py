import pandas as pd
import numpy as np
import yfinance as yf

class SignalService:
    def __init__(self, symbol="^TWII"):
        self.symbol = symbol
        self.point_value = 50      # 微台 1 點 50 元
        self.fee = 20              # 單邊手續費
        self.tax_rate = 0.00002
        self.slippage_points = 2   # 每筆交易預設滑價 2 點（模擬還原度損耗）

    def fetch_data(self, interval, period):
        df = yf.download(self.symbol, interval=interval, period=period, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        return df

    def compute_indicators(self, df):
        df = df.copy()
        df['ema_fast'] = df['close'].ewm(span=12).mean()
        df['ema_slow'] = df['close'].ewm(span=26).mean()
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / loss.replace(0, np.nan))))
        return df

    def run_backtest(self, df, initial_capital, start_date, end_date, stop_loss_pct=0.02, trailing_pct=0.015):
        # 日期過濾
        df = df.loc[start_date:end_date].copy()
        if df.empty: return None

        trades = []
        equity = initial_capital
        in_pos = False
        entry_p, entry_d, max_p = 0, None, 0

        for i in range(len(df)):
            p = float(df['close'].iloc[i])
            d = df.index[i]
            
            if not in_pos:
                if df['ema_fast'].iloc[i] > df['ema_slow'].iloc[i]:
                    # 進場：考慮滑價
                    in_pos, entry_p, entry_d, max_p = True, p + self.slippage_points, d, p
            else:
                max_p = max(max_p, p)
                days = (d - entry_d).days
                reason = ""
                if p < entry_p * (1 - stop_loss_pct): reason = "固定停損"
                elif p < max_p * (1 - trailing_pct): reason = "移動停利"
                elif days >= 7: reason = "7天強平"
                
                if reason:
                    # 出場：考慮滑價
                    exit_price = p - self.slippage_points
                    cost = (entry_p + exit_price) * self.point_value * self.tax_rate + (self.fee * 2)
                    net_pnl = (exit_price - entry_p) * self.point_value - cost
                    equity += net_pnl
                    trades.append({
                        "進場時間": entry_d,
                        "出場時間": d,
                        "進場價": round(entry_p, 1),
                        "出場價": round(exit_price, 1),
                        "出場原因": reason,
                        "淨損益": round(net_pnl),
                        "帳戶餘額": round(equity)
                    })
                    in_pos = False

        return pd.DataFrame(trades) if trades else None
