"""
Bollinger Band Squeeze Breakout Strategy
=========================================
Detects volatility contraction (squeeze) then trades the breakout direction.
Best suited for BTC and trending crypto.
"""
import pandas as pd
import numpy as np


class BBSqueezeStrategy:
    def __init__(self, bb_period=20, bb_std=2.0, squeeze_lookback=20,
                 vol_mult=1.2, atr_period=14, atr_sl=2.0, atr_tp=5.0):
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.squeeze_lookback = squeeze_lookback
        self.vol_mult = vol_mult
        self.atr_period = atr_period
        self.atr_sl = atr_sl
        self.atr_tp = atr_tp

    def get_signal(self, df):
        if len(df) < self.bb_period + self.squeeze_lookback + 10:
            return None, None, None, None

        close = df['close']
        volume = df['volume']
        h, l, c = df['high'], df['low'], close

        # Bollinger Bands
        sma = close.rolling(self.bb_period).mean()
        std = close.rolling(self.bb_period).std()
        upper = sma + self.bb_std * std
        lower = sma - self.bb_std * std
        bandwidth = (upper - lower) / sma

        # ATR
        tr = pd.concat([h - l, abs(h - c.shift()), abs(l - c.shift())], axis=1).max(axis=1)
        atr = tr.rolling(self.atr_period).mean()

        curr_bw = bandwidth.iloc[-1]
        prev_bw = bandwidth.iloc[-2]
        min_bw = bandwidth.iloc[-self.squeeze_lookback - 1:-1].min()
        curr_atr = atr.iloc[-1]
        price = close.iloc[-1]
        prev_price = close.iloc[-2]

        if pd.isna(curr_bw) or pd.isna(min_bw) or pd.isna(curr_atr):
            return None, None, None, None

        # Was in squeeze (previous bandwidth near the minimum)
        was_squeezed = prev_bw <= min_bw * 1.15

        if not was_squeezed:
            return None, None, None, None

        # Breakout: bandwidth expanding AND price closing outside bands
        expanding = curr_bw > prev_bw

        if not expanding:
            return None, None, None, None

        # Volume confirmation
        avg_vol = volume.tail(20).mean()
        curr_vol = volume.iloc[-1]
        vol_ok = curr_vol > avg_vol * self.vol_mult

        if not vol_ok:
            return None, None, None, None

        # Direction from breakout
        curr_upper = upper.iloc[-1]
        curr_lower = lower.iloc[-1]

        if price > curr_upper:
            direction = "BUY"
        elif price < curr_lower:
            direction = "SELL"
        else:
            return None, None, None, None

        sl_dist = curr_atr * self.atr_sl
        tp_dist = curr_atr * self.atr_tp

        mean_atr = atr.tail(20).mean()
        atr_ratio = curr_atr / mean_atr if mean_atr > 0 else 1

        return direction, curr_atr, atr_ratio, {
            "sl_distance": sl_dist,
            "tp1": tp_dist,
            "tp2": tp_dist,
        }
