import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta

class SignalService:
    def __init__(self, symbol="^TWII"):
        self.symbol = symbol
        self.point_value = 10      
        self.fee = 20              
        self.tax_rate = 0.00002    
        self.slippage = 2          
        self.initial_margin = 20000 
        self.amount_stop_limit = -20000 

    def _is_expiry_day(self, dt):
        # 確保 dt 是 tz-naive
        dt_naive = dt.replace(tzinfo=None) if dt.tzinfo else dt
        first_day = datetime(dt_naive.year, dt_naive.month, 1)
        first_wed = first_day + timedelta(days=(2 - first_day.weekday() + 7) % 7)
        third_wed = first_wed + timedelta(weeks=2)
        return dt_naive.date() == third_wed.date()

    def fetch_data(self, interval, period):
        df = yf.download(self.symbol, interval=interval, period=period, progress=False)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        df.columns = [c.lower() for c in df.columns]
        
        # --- 核心修正：統一時區格式 ---
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)
        
        return df

    def compute_indicators(self, df):
        df = df.copy()
        df['ema_f'] = df['close'].ewm(span=12).mean()
        df['ema_s'] = df['close'].ewm(span=26).mean()
        
        high, low, close_prev = df['high'], df['low'], df['close'].shift(1)
        tr = pd.concat([high - low, (high - close_prev).abs(), (low - close_prev).abs()], axis=1).max(axis=1)
        df['atr'] = tr.rolling(window=14).mean()
        df['atr_ma'] = df['atr'].rolling(window=20).mean()
        df['vol_ok'] = df['atr'] > df['atr_ma']
        
        df['trend_sig'] = '盤整'
        df.loc[(df['ema_f'] > df['ema_s']), 'trend_sig'] = '多'
        df.loc[(df['ema_f'] < df['ema_s']), 'trend_sig'] = '空'
        
        last = df.iloc[-1]
        return {
            "dir": last['trend_sig'], "df": df, "vol_ok": last['vol_ok'], 
            "atr_val": last['atr'], "atr_ma_val": last['atr_ma']
        }

    def run_backtest(self, df_30m, df_60m, df_1d, capital, start, end, stop_loss, trailing):
        # 確保所有傳入的 DataFrame 索引都是 tz-naive
        df_30m.index = df_30m.index.tz_localize(None) if df_30m.index.tz else df_30m.index
        df_60m.index = df_60m.index.tz_localize(None) if df_60m.index.tz else df_60m.index
        df_1d.index = df_1d.index.tz_localize(None) if df_1d.index.tz else df_1d.index

        s_60m = df_60m[['trend_sig']].resample('30min').ffill().rename(columns={'trend_sig': 'sig_60m'})
        s_1d = df_1d[['trend_sig']].resample('30min').ffill().rename(columns={'trend_sig': 'sig_1d'})
        
        # 現在 join 不會再噴 TypeError 了
        df = df_30m.join(s_60m).join(s_1d)
        
        # 處理日期範圍 (確保 start/end 轉為不帶時區的 datetime)
        start_ts = pd.to_datetime(start).replace(tzinfo=None)
        end_ts = pd.to_datetime(end).replace(tzinfo=None)
        df = df.loc[start_ts:end_ts].copy()
        
        if df.empty: return None
        
        trades, equity = [], [capital]
        in_pos, pos_type, entry_p, entry_d, peak_p = False, None, 0, None, 0
        
        for i in range(len(df)):
            p, d = float(df['close'].iloc[i]), df.index[i]
            is_exp = self._is_expiry_day(d)
            s30, s60, s1d = df['trend_sig'].iloc[i], df['sig_60m'].iloc[i], df['sig_1d'].iloc[i]

            if not in_pos:
                if s30=='多' and s60=='多' and s1d=='多' and df['vol_ok'].iloc[i] and not is_exp:
                    in_pos, pos_type, entry_p, entry_d, peak_p = True, 'long', p + self.slippage, d, p
                elif s30=='空' and s60=='空' and s1d=='空' and df['vol_ok'].iloc[i] and not is_exp:
                    in_pos, pos_type, entry_p, entry_d, peak_p = True, 'short', p - self.slippage, d, p
            else:
                raw_diff = (p - entry_p) if pos_type == 'long' else (entry_p - p)
                current_raw_pnl = raw_diff * self.point_value
                reason = ""
                if current_raw_pnl <= self.amount_stop_limit:
                    reason = "金額停損 (2萬)"
                elif pos_type == 'long':
                    peak_p = max(peak_p, p)
                    if p < entry_p * (1 - stop_loss): reason = "固定停損"
                    elif p < peak_p * (1 - trailing): reason = "移動停利"
                else:
                    peak_p = min(peak_p, p)
                    if p > entry_p * (1 + stop_loss): reason = "固定停損"
                    elif p > peak_p * (1 + trailing): reason = "移動停利"
                
                if (d - entry_d).days >= 7: reason = "7天強平"
                elif is_exp: reason = "結算日避險"
                
                if reason:
                    exit_p = p - self.slippage if pos_type == 'long' else p + self.slippage
                    cost = (entry_p + exit_p) * self.point_value * self.tax_rate + (self.fee * 2)
                    net_pnl = raw_diff * self.point_value - cost
                    trades.append({
                        "時間": entry_d, "類型": "做多" if pos_type == 'long' else "放空",
                        "原因": reason, "進場價": round(entry_p), "出場價": round(exit_p),
                        "損益": round(net_pnl)
                    })
                    equity.append(equity[-1] + net_pnl)
                    in_pos, pos_type = False, None

        if not trades: return None
        tdf = pd.DataFrame(trades)
        equity_series = pd.Series(equity)
        return {
            "total_pnl": tdf['損益'].sum(),
            "mdd": (equity_series.cummax() - equity_series).max(),
            "win_rate": len(tdf[tdf['損益']>0])/len(tdf),
            "trades": tdf
        }
