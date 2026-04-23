import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

class SignalService:
    def __init__(self, symbol="^TWII"):
        self.symbol = symbol
        self.point_value = 50      # 微台 1 點 50 元
        self.fee = 20              # 單邊手續費 20 元
        self.tax_rate = 0.00002    # 期交稅
        
    def fetch_data(self, interval, period):
        df = yf.download(self.symbol, interval=interval, period=period, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        return df

    def compute_indicators(self, df):
        df = df.copy()
        # 均線運算
        df['ema_fast'] = df['close'].ewm(span=12).mean()
        df['ema_slow'] = df['close'].ewm(span=26).mean()
        # RSI 運算
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        # 避免除以 0
        rs = gain / loss.replace(0, np.nan)
        df['rsi'] = 100 - (100 / (1 + rs))
        df['rsi'] = df['rsi'].fillna(50)
        
        # 多空機率計算
        last = df.iloc[-1]
        score = 0
        if last['close'] > last['ema_fast']: score += 35
        if last['ema_fast'] > last['ema_slow']: score += 35
        if last['rsi'] > 50: score += 30
        
        direction = "多" if score >= 70 else "空" if score <= 30 else "盤整"
        return {"dir": direction, "prob": score, "df": df}

    def run_backtest(self, df, stop_loss_pct=0.02, trailing_pct=0.015):
        # 重要：如果傳入的 df 沒指標，先跑一次運算
        if 'ema_fast' not in df.columns:
            df = self.compute_indicators(df)['df']
            
        trades = []
        in_pos = False
        entry_p, entry_d, max_p = 0, None, 0
        
        for i in range(len(df)):
            p = float(df['close'].iloc[i])
            d = df.index[i]
            
            if not in_pos:
                # 金叉進場邏輯
                if df['ema_fast'].iloc[i] > df['ema_slow'].iloc[i]:
                    in_pos, entry_p, entry_d, max_p = True, p, d, p
            else:
                max_p = max(max_p, p)
                days = (d - entry_d).days
                
                reason = ""
                if p < entry_p * (1 - stop_loss_pct): reason = "固定停損"
                elif p < max_p * (1 - trailing_pct): reason = "移動停利"
                elif days >= 7: reason = "7天強平"
                
                if reason:
                    cost = (entry_p + p) * self.point_value * self.tax_rate + (self.fee * 2)
                    net_pnl = (p - entry_p) * self.point_value - cost
                    trades.append({
                        "進場日期": entry_d.strftime('%Y-%m-%d %H:%M'),
                        "出場日期": d.strftime('%Y-%m-%d %H:%M'),
                        "類型": "做多",
                        "進場價": round(entry_p),
                        "出場價": round(p),
                        "出場原因": reason,
                        "淨損益": round(net_pnl)
                    })
                    in_pos = False
        return trades
