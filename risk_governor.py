import time
from datetime import datetime, timezone
import config
import state_store

class RiskGovernor:
    def __init__(self):
        self.day_start_equity = config.INITIAL_CAPITAL
        self.current_day_str = None
        self.peak_equity = config.INITIAL_CAPITAL
        self.consecutive_losses = 0
        self.cb_locked_until = 0

    # --- FIX 1: Recovery hook ---
    def restore_state(self, peak_equity, consecutive_losses, cb_locked_until):
        if peak_equity: self.peak_equity = peak_equity
        if consecutive_losses: self.consecutive_losses = consecutive_losses
        if cb_locked_until: self.cb_locked_until = cb_locked_until
        state_store.log(f"Risk Governor Restored: Peak ${self.peak_equity:.2f} | {self.consecutive_losses} Losses")

    def sync_daily_anchors(self, current_equity):
        utc_now = datetime.now(timezone.utc)
        day_str = utc_now.strftime('%Y-%m-%d')
        if day_str != self.current_day_str:
            self.current_day_str = day_str
            self.day_start_equity = current_equity
            state_store.log(f"Daily Risk Anchor Reset: Starting Equity = ${current_equity:,.2f}")
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

    def evaluate_circuit_breakers(self, current_equity):
        self.sync_daily_anchors(current_equity)
        
        if time.time() < self.cb_locked_until:
            rem_hrs = (self.cb_locked_until - time.time()) / 3600.0
            return False, f"CIRCUIT BREAKER ACTIVE ({rem_hrs:.1f}h rem)"

        daily_dd = (self.day_start_equity - current_equity) / self.day_start_equity
        if daily_dd >= config.MAX_DAILY_DRAWDOWN_PCT:
            self._trigger_circuit_breaker(f"10% Daily Drawdown Limit Hit (-{daily_dd*100:.2f}%)")
            return False, "CIRCUIT BREAKER TRIPPED"

        hwm_dd = (self.peak_equity - current_equity) / self.peak_equity
        if hwm_dd >= config.MAX_HWM_DRAWDOWN_PCT:
            self._trigger_circuit_breaker(f"20% Peak HWM Drawdown Hit (-{hwm_dd*100:.2f}%)")
            return False, "CIRCUIT BREAKER TRIPPED"

        if self.consecutive_losses >= config.MAX_CONSECUTIVE_LOSSES:
            self._trigger_circuit_breaker(f"10 Consecutive Losses Reached")
            return False, "CIRCUIT BREAKER TRIPPED"

        return True, "HEALTHY"

    def _trigger_circuit_breaker(self, reason):
        self.cb_locked_until = time.time() + (config.CIRCUIT_BREAKER_LOCKOUT_HOURS * 3600)
        state_store.log(f"🛑 CRITICAL: {reason}. Trading locked.", "ERROR")
        self.consecutive_losses = 0
        self.peak_equity = self.day_start_equity 

    def record_trade_result(self, net_pnl):
        if net_pnl < 0: self.consecutive_losses += 1
        else: self.consecutive_losses = 0

    def calculate_position_size(self, equity, free_margin, entry_price, stop_distance, allowed_leverage):
        dollar_risk = equity * config.RISK_PER_TRADE_PCT
        raw_size = dollar_risk / stop_distance
        notional = raw_size * entry_price
        required_margin = notional / allowed_leverage

        if required_margin > (free_margin * 0.95):
            available_margin = free_margin * 0.95
            notional = available_margin * allowed_leverage
            raw_size = notional / entry_price
            required_margin = available_margin
            dollar_risk = raw_size * stop_distance
            if dollar_risk < (equity * 0.002):
                return 0.0, 0.0, 0.0

        return raw_size, notional, required_margin
