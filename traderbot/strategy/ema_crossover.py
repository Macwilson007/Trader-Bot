import pandas as pd
import numpy as np


class EMACrossoverStrategy:
    def __init__(self, fast_period=10, slow_period=30, trend_period=200, adx_period=14, adx_min=15, atr_period=14, atr_multiplier=1.2, tp_r=3.0, atr_vol_threshold=3.0):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.trend_period = trend_period
        self.adx_period = adx_period
        self.adx_min = adx_min
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.tp_r = tp_r
        self.atr_vol_threshold = atr_vol_threshold
    
    def calculate_indicators(self, df):
        # EMA calculations
        ema_fast = df['close'].ewm(span=self.fast_period, adjust=False).mean()
        ema_slow = df['close'].ewm(span=self.slow_period, adjust=False).mean()
        ema_trend = df['close'].ewm(span=self.trend_period, adjust=False).mean()
        
        # ATR calculations
        h, l, c = df['high'], df['low'], df['close']
        tr = pd.concat([h - l, abs(h - c.shift()), abs(l - c.shift())], axis=1).max(axis=1)
        atr = tr.rolling(window=self.atr_period).mean()
        
        # ADX calculations
        pdm = h.diff().clip(lower=0)
        mdm = (-l.diff()).clip(lower=0)
        plus_di = 100 * (pdm.rolling(self.adx_period).mean() / atr)
        minus_di = 100 * (mdm.rolling(self.adx_period).mean() / atr)
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(self.adx_period).mean()
        
        return ema_fast, ema_slow, ema_trend, atr, adx
    
    def get_signal(self, df):
        if len(df) < self.trend_period + 10:
            return None, None, None, None
        
        ema_fast, ema_slow, ema_trend, atr, adx = self.calculate_indicators(df)
        
        curr_f, prev_f = ema_fast.iloc[-1], ema_fast.iloc[-2]
        curr_s, prev_s = ema_slow.iloc[-1], ema_slow.iloc[-2]
        curr_t = ema_trend.iloc[-1]
        curr_adx = adx.iloc[-1]
        curr_atr = atr.iloc[-1]
        price = df['close'].iloc[-1]
        
        # VOLATILITY FILTER
        mean_atr = atr.tail(20).mean()
        atr_ratio = curr_atr / mean_atr if mean_atr > 0 else 1
        if atr_ratio > self.atr_vol_threshold:
            return None, None, None, None
            
        # MOMENTUM FILTER (ADX)
        if curr_adx < self.adx_min:
            return None, None, None, None
            
        direction = None
        
        # TREND FILTER (EMA 200) + CROSSOVER
        if price > curr_t: # Uptrend
            if prev_f <= prev_s and curr_f > curr_s:
                direction = "BUY"
        elif price < curr_t: # Downtrend
            if prev_f >= prev_s and curr_f < curr_s:
                direction = "SELL"
                
        if not direction:
            return None, None, None, None
            
        sl_dist = curr_atr * self.atr_multiplier
        tp_dist = curr_atr * self.tp_r
        
        return direction, curr_atr, atr_ratio, {
            "sl_distance": sl_dist,
            "tp1": tp_dist,
            "tp2": tp_dist
        }


if __name__ == "__main__":
    print("EMA Crossover Strategy loaded")
    strategy = EMACrossoverStrategy()
    print("Params: Fast EMA=20, Slow EMA=50, ATR SL=1.5x, TP=2.0R")
