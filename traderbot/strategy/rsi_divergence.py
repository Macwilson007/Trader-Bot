"""
RSI Divergence Strategy
========================
Detects bullish/bearish divergence between price and RSI.
Best suited for range-bound coins like XRP, DOGE, ADA.
"""
import pandas as pd
import numpy as np


class RSIDivergenceStrategy:
    def __init__(self, rsi_period=14, div_lookback=14, ema_filter=50,
                 atr_period=14, atr_sl=1.3, atr_tp=2.5):
        self.rsi_period = rsi_period
        self.div_lookback = div_lookback
        self.ema_filter = ema_filter
        self.atr_period = atr_period
        self.atr_sl = atr_sl
        self.atr_tp = atr_tp

    def _calc_rsi(self, close):
        delta = close.diff()
        gain = delta.where(delta > 0, 0).rolling(self.rsi_period).mean()
        loss = (-delta).where(delta < 0, 0).rolling(self.rsi_period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    def _find_swing_lows(self, series, window=5):
        """Find indices of local minima."""
        lows = []
        arr = series.values
        for i in range(window, len(arr) - window):
            if arr[i] == min(arr[i - window:i + window + 1]):
                lows.append(i)
        return lows

    def _find_swing_highs(self, series, window=5):
        """Find indices of local maxima."""
        highs = []
        arr = series.values
        for i in range(window, len(arr) - window):
            if arr[i] == max(arr[i - window:i + window + 1]):
                highs.append(i)
        return highs

    def get_signal(self, df):
        if len(df) < self.ema_filter + 20:
            return None, None, None, None

        close = df['close']
        h, l, c = df['high'], df['low'], close

        rsi = self._calc_rsi(close)
        ema = close.ewm(span=self.ema_filter, adjust=False).mean()

        # ATR
        tr = pd.concat([h - l, abs(h - c.shift()), abs(l - c.shift())], axis=1).max(axis=1)
        atr = tr.rolling(self.atr_period).mean()

        curr_atr = atr.iloc[-1]
        price = close.iloc[-1]
        curr_ema = ema.iloc[-1]
        curr_rsi = rsi.iloc[-1]

        if pd.isna(curr_atr) or pd.isna(curr_rsi):
            return None, None, None, None

        # Look at recent window for divergence
        window = df.iloc[-self.div_lookback * 2:]
        w_close = window['close'].reset_index(drop=True)
        w_rsi = self._calc_rsi(df['close']).iloc[-len(window):].reset_index(drop=True)

        direction = None

        # Bullish divergence: price lower low, RSI higher low
        price_lows = self._find_swing_lows(w_close, window=3)
        rsi_lows = self._find_swing_lows(w_rsi, window=3)

        if len(price_lows) >= 2 and len(rsi_lows) >= 2:
            pl1, pl2 = price_lows[-2], price_lows[-1]
            if (w_close.iloc[pl2] < w_close.iloc[pl1] and
                    w_rsi.iloc[pl2] > w_rsi.iloc[pl1] and
                    curr_rsi < 40 and
                    abs(pl2 - len(w_close) + 1) < 5):
                direction = "BUY"

        # Bearish divergence: price higher high, RSI lower high
        if direction is None:
            price_highs = self._find_swing_highs(w_close, window=3)
            rsi_highs = self._find_swing_highs(w_rsi, window=3)

            if len(price_highs) >= 2 and len(rsi_highs) >= 2:
                ph1, ph2 = price_highs[-2], price_highs[-1]
                if (w_close.iloc[ph2] > w_close.iloc[ph1] and
                        w_rsi.iloc[ph2] < w_rsi.iloc[ph1] and
                        curr_rsi > 60 and
                        abs(ph2 - len(w_close) + 1) < 5):
                    direction = "SELL"

        if not direction:
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
