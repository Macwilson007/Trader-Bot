"""
Multi-Timeframe EMA Crossover Strategy
========================================
Uses simulated H4 data (resampled from H1) for trend direction,
then uses H1 EMA crossover for entry timing. Only takes signals
aligned with the higher timeframe trend.
"""
import pandas as pd
import numpy as np


class MTFEmaCrossoverStrategy:
    def __init__(self, fast=10, slow=30, htf_fast=50, htf_slow=200,
                 adx_period=14, adx_min=15, atr_period=14,
                 atr_sl=1.2, atr_tp=3.0, atr_vol_thresh=3.0):
        self.fast = fast
        self.slow = slow
        self.htf_fast = htf_fast
        self.htf_slow = htf_slow
        self.adx_period = adx_period
        self.adx_min = adx_min
        self.atr_period = atr_period
        self.atr_sl = atr_sl
        self.atr_tp = atr_tp
        self.atr_vol_thresh = atr_vol_thresh

    def _resample_h4(self, df):
        """Resample H1 OHLCV to H4."""
        tmp = df.set_index('time')
        h4 = tmp.resample('4h').agg({
            'open': 'first', 'high': 'max', 'low': 'min',
            'close': 'last', 'volume': 'sum'
        }).dropna()
        return h4

    def get_signal(self, df):
        if len(df) < 250:
            return None, None, None, None

        # H4 trend filter
        h4 = self._resample_h4(df)
        if len(h4) < self.htf_slow + 5:
            return None, None, None, None

        h4_ema_fast = h4['close'].ewm(span=self.htf_fast, adjust=False).mean()
        h4_ema_slow = h4['close'].ewm(span=self.htf_slow, adjust=False).mean()

        h4_trend = None
        if h4_ema_fast.iloc[-1] > h4_ema_slow.iloc[-1]:
            h4_trend = "UP"
        elif h4_ema_fast.iloc[-1] < h4_ema_slow.iloc[-1]:
            h4_trend = "DOWN"

        if h4_trend is None:
            return None, None, None, None

        # H1 entry logic
        close = df['close']
        h, l, c = df['high'], df['low'], close

        ema_f = close.ewm(span=self.fast, adjust=False).mean()
        ema_s = close.ewm(span=self.slow, adjust=False).mean()

        # ATR
        tr = pd.concat([h - l, abs(h - c.shift()), abs(l - c.shift())], axis=1).max(axis=1)
        atr = tr.rolling(self.atr_period).mean()

        # ADX
        pdm = h.diff().clip(lower=0)
        mdm = (-l.diff()).clip(lower=0)
        pdi = 100 * pdm.rolling(self.adx_period).mean() / atr
        mdi = 100 * mdm.rolling(self.adx_period).mean() / atr
        dx = 100 * abs(pdi - mdi) / (pdi + mdi)
        adx = dx.rolling(self.adx_period).mean()

        curr_atr = atr.iloc[-1]
        curr_adx = adx.iloc[-1]
        price = close.iloc[-1]

        if pd.isna(curr_atr) or pd.isna(curr_adx):
            return None, None, None, None

        # Volatility filter
        mean_atr = atr.tail(20).mean()
        atr_ratio = curr_atr / mean_atr if mean_atr > 0 else 1
        if atr_ratio > self.atr_vol_thresh:
            return None, None, None, None

        if curr_adx < self.adx_min:
            return None, None, None, None

        # EMA crossover on H1
        curr_f, prev_f = ema_f.iloc[-1], ema_f.iloc[-2]
        curr_s, prev_s = ema_s.iloc[-1], ema_s.iloc[-2]

        direction = None
        if h4_trend == "UP" and prev_f <= prev_s and curr_f > curr_s:
            direction = "BUY"
        elif h4_trend == "DOWN" and prev_f >= prev_s and curr_f < curr_s:
            direction = "SELL"

        if not direction:
            return None, None, None, None

        sl_dist = curr_atr * self.atr_sl
        tp_dist = curr_atr * self.atr_tp

        return direction, curr_atr, atr_ratio, {
            "sl_distance": sl_dist,
            "tp1": tp_dist,
            "tp2": tp_dist,
        }
