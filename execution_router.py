import asyncio
import time
import config
import state_store

class ExecutionRouter:
    def __init__(self, mesh, risk_gov):
        self.mesh = mesh
        self.risk_gov = risk_gov

    async def get_market_max_leverage(self, symbol):
        try:
            exchange = self.mesh.rest_exchange
            tiers = await exchange.fetch_market_leverage_tiers(symbol)
            if tiers and len(tiers) > 0:
                max_allowed = float(tiers[0].get('maxLeverage', config.DEFAULT_LEVERAGE))
                return min(config.DEFAULT_LEVERAGE, int(max_allowed))
        except Exception: pass
        return config.DEFAULT_LEVERAGE

    async def place_gtc_entry(self, setup, equity, free_margin):
        sym = setup['symbol']
        side = setup['side']
        entry_px = setup['entry_price']
        stop_dist = setup['risk_distance']
        
        allowed_lev = await self.get_market_max_leverage(sym)
        exchange = self.mesh.rest_exchange
        
        try: await exchange.set_margin_mode(config.MARGIN_MODE, sym)
        except Exception: pass
        try: await exchange.set_leverage(allowed_lev, sym)
        except Exception: pass

        size, notional, req_margin = self.risk_gov.calculate_position_size(equity, free_margin, entry_px, stop_dist, allowed_lev)
        if size <= 0: return None

        qty_str = exchange.amount_to_precision(sym, size)
        px_str = exchange.price_to_precision(sym, entry_px)
        order_side = 'buy' if side == 'long' else 'sell'

        try:
            order = await exchange.create_order(sym, 'LIMIT', order_side, float(qty_str), float(px_str), params={'timeInForce': 'GTC'})
            state_store.log(f"⚡ GTC Entry Deployed: {sym} {order_side.upper()} {qty_str} @ ${px_str}")
            return {
                'order_id': order['id'], 'symbol': sym, 'side': side, 'size': float(qty_str),
                'entry_price': float(px_str), 'stop_distance': stop_dist, 'initial_sl': setup['stop_loss'],
                'target_5r': setup['target_5r'], 'target_tp': setup['target_price'],
                'margin_locked': req_margin, 'leverage': allowed_lev, 'placed_time': time.time()
            }
        except Exception as e:
            state_store.log(f"GTC Entry Placement Failed for {sym}: {e}", "ERROR")
            return None

    async def evaluate_gtc_cancellations(self, pending_entries, current_ers):
        for sym, entry in list(pending_entries.items()):
            live_px = self.mesh.get_live_price(sym)
            if not live_px: continue
            
            cancel_reason = None
            is_long = entry['side'] == 'long'
            
            if (time.time() - entry['placed_time']) > config.GTC_MAX_AGE_SECONDS: cancel_reason = "60m Time Decay"
            elif (is_long and live_px <= entry['initial_sl']) or (not is_long and live_px >= entry['initial_sl']): cancel_reason = "Structural Invalidation Breached"
            elif (is_long and live_px >= entry['target_5r']) or (not is_long and live_px <= entry['target_5r']): cancel_reason = "5R Runaway Liquidity Exhaustion"
            elif current_ers.get(sym, 1.0) < config.ER_TREND_THRESHOLD: cancel_reason = f"1h ER Degraded to Chop"

            if cancel_reason:
                try:
                    await self.mesh.rest_exchange.cancel_order(entry['order_id'], sym)
                    state_store.log(f"🚫 GTC Entry Revoked: {sym} - Reason: {cancel_reason}")
                except Exception as e:
                    state_store.log(f"Failed to cancel GTC order for {sym}: {e}", "WARN")
                del pending_entries[sym]

    async def place_layered_stop(self, sym, side, size, sl_price, tier):
        opp_side = 'sell' if side == 'long' else 'buy'
        exchange = self.mesh.rest_exchange
        sl_str = exchange.price_to_precision(sym, sl_price)
        qty_str = exchange.amount_to_precision(sym, size)

        try:
            res = await exchange.create_order(sym, 'STOP_MARKET', opp_side, float(qty_str), params={'stopPrice': float(sl_str), 'reduceOnly': True})
            state_store.record_bracket_order(sym, res['id'], 'STOP_MARKET', float(sl_str), tier)
            state_store.log(f"🛡️ Layered Stop Deployed [{tier}]: {sym} @ ${sl_str}")
            return res['id']
        except Exception as e:
            state_store.log(f"Layered Stop Failed for {sym} [{tier}]: {e}", "ERROR")
            return None

    async def sweep_orphan_orders(self, sym):
        exchange = self.mesh.rest_exchange
        known_brackets = state_store.get_bracket_orders(sym)
        for order_id in known_brackets:
            try: await exchange.cancel_order(order_id, sym)
            except Exception: pass
        state_store.purge_symbol_brackets(sym)

        try:
            orders = await exchange.fetch_open_orders(sym)
            for o in orders:
                try: await exchange.cancel_order(o['id'], sym)
                except Exception: pass
            if orders: state_store.log(f"🧹 Orphan Sweeper: Destroyed {len(orders)} residual brackets on {sym}.")
        except Exception as e:
            state_store.log(f"Orphan sweeper scan failed for {sym}: {e}", "WARN")
