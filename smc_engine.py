import numpy as np
import pandas as pd
import config

class SMCEngine:
    @staticmethod
    def calculate_efficiency_ratio(close_series, period=config.ER_PERIOD):
        if len(close_series) < period + 1: return 0.0
        c = close_series.to_numpy()
        net_change = np.abs(c[-1] - c[-period])
        sum_changes = np.sum(np.abs(np.diff(c[-period:])))
        if sum_changes == 0: return 0.0
        return float(net_change / sum_changes)

    @staticmethod
    def find_fractal_swings(high_arr, low_arr, n=config.FRACTAL_WINDOW):
        length = len(high_arr)
        if length < (2 * n + 1): return [], []
        swing_highs, swing_lows = [], []
        for i in range(n, length - n):
            if high_arr[i] == np.max(high_arr[i - n : i + n + 1]): swing_highs.append(high_arr[i])
            if low_arr[i] == np.min(low_arr[i - n : i + n + 1]): swing_lows.append(low_arr[i])
        return swing_highs, swing_lows

    @classmethod
    def evaluate_pair(cls, symbol, df_1h, df_15m, df_1m):
        try:
            if df_1h.empty or df_15m.empty or df_1m.empty: return None
            if len(df_1h) < 7: return None # Guard against new coin crash
                
            er_1h = cls.calculate_efficiency_ratio(df_1h['close'])
            if er_1h < config.ER_TREND_THRESHOLD: return None 

            c_1h = df_1h['close'].to_numpy()
            h1_bias = 1 if c_1h[-1] > c_1h[-6] else -1

            h_15m, l_15m, c_15m = df_15m['high'].to_numpy(), df_15m['low'].to_numpy(), df_15m['close'].to_numpy()
            sh_pools, sl_pools = cls.find_fractal_swings(h_15m, l_15m)
            curr_15m_high, curr_15m_low, curr_15m_close = h_15m[-1], l_15m[-1], c_15m[-1]

            h_1m, l_1m = df_1m['high'].to_numpy(), df_1m['low'].to_numpy()

            if sl_pools and h1_bias >= 0:
                target_low = min(sl_pools[-5:]) 
                if curr_15m_low < target_low * (1.0 - config.SWEEP_MIN_DEPTH_PCT) and curr_15m_close > target_low:
                    for m in range(len(df_1m) - 1, max(len(df_1m) - 6, 2), -1):
                        if l_1m[m] > h_1m[m - 2]:
                            entry_price = l_1m[m]  
                            stop_loss = curr_15m_low * (1.0 - 0.0002)
                            risk_dist = entry_price - stop_loss
                            if risk_dist > 0 and (risk_dist / entry_price) <= 0.02:
                                return {
                                    'symbol': symbol, 'side': 'long', 'entry_price': entry_price, 'stop_loss': stop_loss,
                                    'risk_distance': risk_dist, 'target_price': entry_price + (risk_dist * config.TERMINAL_TP_R),
                                    'target_5r': entry_price + (risk_dist * config.GTC_RUNAWAY_R_MULTIPLE), 'er': er_1h
                                }

            if sh_pools and h1_bias <= 0:
                target_high = max(sh_pools[-5:])
                if curr_15m_high > target_high * (1.0 + config.SWEEP_MIN_DEPTH_PCT) and curr_15m_close < target_high:
                    for m in range(len(df_1m) - 1, max(len(df_1m) - 6, 2), -1):
                        if h_1m[m] < l_1m[m - 2]:
                            entry_price = h_1m[m]
                            stop_loss = curr_15m_high * (1.0 + 0.0002)
                            risk_dist = stop_loss - entry_price
                            if risk_dist > 0 and (risk_dist / entry_price) <= 0.02:
                                return {
                                    'symbol': symbol, 'side': 'short', 'entry_price': entry_price, 'stop_loss': stop_loss,
                                    'risk_distance': risk_dist, 'target_price': entry_price - (risk_dist * config.TERMINAL_TP_R),
                                    'target_5r': entry_price - (risk_dist * config.GTC_RUNAWAY_R_MULTIPLE), 'er': er_1h
                                }
            return None
        except Exception as e:
            print(f"SMC Math Engine Error on {symbol}: {e}")
            return None
