import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

class SignalService:
    def __init__(self, symbol="^TWII"):
        self.symbol = symbol
        self.point_value = 50      # 微台 1 點 50 元
        self.fee = 20              # 單邊手續費 20 元
        self.tax_rate = 0.00002    # 期交稅 0.002%
        self.slippage = 2          # 單邊滑價補償 2 點
        self.initial_margin = 20000 # 每口預估保證金

    def _is_expiry_day(self, dt):
        """判斷是否為台指期結算日 (每月第三個週三)"""
        # 如果是帶有時區的 Timestamp，轉為 naive datetime 比較安全
        dt_naive = dt.replace(tzinfo=None)
        first_day = datetime(dt_naive.year, dt_naive.month, 1)
        # weekday: 0=Mon, 2=Wed
        first_wed = first_day + timedelta(days=(2 - first_day.weekday() + 7) % 7)
        third_wed = first_wed + timedelta(weeks=2)
        return dt_naive.date() == third_wed.date()

    def fetch_data(self, interval, period):
        df = yf.download(self.symbol, interval=interval, period=period, progress=False)
        # 解決 yfinance MultiIndex 問題：只取第一層欄位名
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        return df

    def compute_indicators(self, df):
        df = df.copy()
        # 趨勢指標：EMA 12/26
        df['ema_f'] = df['close'].ewm(span=12).mean()
        df['ema_s'] = df['close'].ewm(span=26).mean()
        
        # ATR 波動過濾器 (14週期)
        high, low, close_prev = df['high'], df['low'], df['close'].shift(1)
        tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()
        df['atr_ma'] = df['atr'].rolling(window=20).mean() # ATR 的 20 期平均
        df['vol_ok'] = df['atr'] > df['atr_ma'] # 只有當前波動 > 平均波動才開倉
        
        # RSI 
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        df['rsi'] = 100 - (100 / (1 + (gain / loss.replace(0, np.nan))))
        df['rsi'] = df['rsi'].fillna(50)
        
        last = df.iloc[-1]
        score = 0
        if last['close'] > last['ema_f']: score += 35
        if last['ema_f'] > last['ema_s']: score += 35
        if last['vol_ok']: score += 30
        
        direction = "多" if score >= 70 else "空" if score <= 30 else "觀望"
        return {"dir": direction, "prob": score, "df": df}

    def run_backtest(self, df, capital, start, end, stop_loss, trailing):
        # 確保資料含有指標，並過濾日期區間
        if 'ema_f' not in df.columns:
            df = self.compute_indicators(df)['df']
        
        df = df.loc[start:end].copy()
        if df.empty: return None
            
        trades = []
        equity_curve = [capital]
        in_pos, entry_p, entry_d, max_p = False, 0, None, 0
        
        for i in range(len(df)):
            p = float(df['close'].iloc[i])
            d = df.index[i]
            is_exp = self._is_expiry_day(d)
            
            if not in_pos:
                # 進場條件：EMA多頭 + 波動率達標 + 非結算日
