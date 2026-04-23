import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

class SignalService:
    def __init__(self, symbol="^TWII"):
        self.symbol = symbol
        self.opt_multiplier = 50   # 選擇權 1 點 50 元
        self.point_value = 10      # 微台對比用
        
    def fetch_data(self, interval, period):
        df = yf.download(self.symbol, interval=interval, period=period, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        if df.index.tz: df.index = df.index.tz_localize(None)
        return df

    def compute_indicators(self, df):
        df = df.copy()
        df['ema_f'] = df['close'].ewm(span=12).mean()
        df['ema_s'] = df['close'].ewm(span=26).mean()
        
        # ATR 波動計算 (判斷 IV 環境)
        high, low, close_prev = df['high'], df['low'], df['close'].shift(1)
        tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()
        df['atr_ma'] = df['atr'].rolling(window=20).mean()
        
        # 趨勢判定
        df['trend_sig'] = '盤整'
        df.loc[(df['ema_f'] > df['ema_s']), 'trend_sig'] = '多'
        df.loc[(df['ema_f'] < df['ema_s']), 'trend_sig'] = '空'
        
        last = df.iloc[-1]
        curr_price = last['close']
        
        # --- 選擇權建議邏輯 ---
        # 尋找最近的 100 整數點位作為履約價建議
        base_strike = round(curr_price / 100) * 100
        
        recommendation = {}
        if last['trend_sig'] == '多':
            recommendation = {
                "type": "買進買權 (Buy Call)",
                "strike": base_strike + 100, # 買價外一檔比較便宜
                "delta_est": 0.45
            }
        elif last['trend_sig'] == '空':
            recommendation = {
                "type": "買進賣權 (Buy Put)",
                "strike": base_strike - 100, # 買價外一檔
                "delta_est": -0.45
            }

        return {
            "dir": last['trend_sig'], "df": df, 
            "vol_ok": last['atr'] > last['atr_ma'],
            "atr_val": last['atr'],
            "opt_rec": recommendation,
            "curr_price": curr_price
        }

    def track_option_pnl(self, entry_price, current_price, opt_type, delta=0.5):
        """簡單估算選擇權損益 (Delta 估算法)"""
        price_diff = current_price - entry_price
        # 選擇權損益 = 點數差 * Delta * 50元
        estimated_pnl = price_diff * delta * self.opt_multiplier
        return round(estimated_pnl)
