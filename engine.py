"""
NexusSniper (NP) - Master Event Loop & Supervisor
Synchronized to Wall-Clock 15-Minute Candle Closes (:00, :15, :30, :45 UTC).
"""
import asyncio
import signal
import sys
import os
import time
import re
import traceback
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import numpy as np

import config
import state_store
from network_mesh import NetworkMesh
from smc_engine import SMCEngine
from risk_governor import RiskGovernor
from execution_router import ExecutionRouter
import telegram_notifier

shutdown_event = asyncio.Event()

def handle_exit(sig, frame):
    print("\n[!] Graceful shutdown signal received...")
    state_store.log("Graceful shutdown signal received...")
    shutdown_event.set()

signal.signal(signal.SIGINT, handle_exit)
signal.signal(signal.SIGTERM, handle_exit)

def _cpu_bound_smc_eval(sym, df_1h, df_15m, df_1m):
    try:
        return SMCEngine.evaluate_pair(sym, df_1h, df_15m, df_1m)
    except Exception as e:
        print(f"❌ [CPU Worker Crash] {sym}: {e}")
        return None

def get_15m_bar_slot(dt):
    """Returns a unique slot identifier for the current 15m window."""
    minute_slot = (dt.minute // 15) * 15
    return f"{dt.strftime('%Y-%m-%d %H')}:{minute_slot:02d}"

def get_seconds_until_next_15m():
    """Calculates remaining seconds until the next :00, :15, :30, :45 UTC mark."""
    now = datetime.now(timezone.utc)
    rem_min = 14 - (now.minute % 15)
    rem_sec = 59 - now.second
    return (rem_min * 60) + rem_sec

class NexusSniperEngine:
    def __init__(self):
        self.mesh = NetworkMesh()
        self.risk_gov = RiskGovernor()
        self.router = ExecutionRouter(self.mesh, self.risk_gov)
        self.pending_entries = {}      
        self.tracked_symbols = []
        self.current_ers = {}
        self.cpu_pool = ProcessPoolExecutor(max_workers=max(1, os.cpu_count() - 1))
        self.cb_active_state = False 
        self.last_scanned_bar_slot = None

    async def initialize(self):
        try:
            state_store.init_db()
            await self.mesh.initialize()
            
            # 1. Screen initial universe
            await self.screen_universe()
            
            watchlist_payload = [{'symbol': sym, 'er': 0.0, 'price': 0.0, 'status': 'INITIALIZING'} for sym in self.tracked_symbols]
            state_store.update_watchlist(watchlist_payload)

            asyncio.create_task(self.mesh.start_ticker_stream(self.tracked_symbols))
            msg = "Supervisor initialized. Entering unified asynchronous event loop."
            print(f"✅ {msg}")
            state_store.log(msg)
            
            await telegram_notifier.send_alert(telegram_notifier.format_startup_alert(len(self.tracked_symbols)))

            # 2. IMMEDIATE BOOTSTRAP SCAN: Audit the most recently closed 15m bar right away
            print("\n⚡ [BOOTSTRAP] Performing immediate audit of the most recently closed 15m candle...")
            bal = await self.mesh.rest_exchange.fetch_balance()
            equity = float(bal.get('USDT', {}).get('total', config.INITIAL_CAPITAL))
            free_margin = float(bal.get('USDT', {}).get('free', config.INITIAL_CAPITAL))
            loop = asyncio.get_running_loop()
            
            await self.scan_for_setups(equity, free_margin, [], loop)
            
            # Mark current slot so we don't re-scan until the next candle close
            self.last_scanned_bar_slot = get_15m_bar_slot(datetime.now(timezone.utc))
            
            rem_secs = get_seconds_until_next_15m()
            print(f"⏳ Bootstrap complete. Next synchronized scan in {rem_secs // 60}m {rem_secs % 60}s (at the 15m candle close).\n")

        except Exception as e:
            print(f"❌ Initialization Error: {e}\n{traceback.format_exc()}")
            raise

    async def screen_universe(self):
        try:
            tickers = await self.mesh.rest_exchange.fetch_tickers()
            btc_sym = 'BTC/USDT:USDT' if 'BTC/USDT:USDT' in tickers else 'BTC/USDT'
            btc_chg = float(tickers.get(btc_sym, {}).get('percentage', 0.0))

            vol_threshold = getattr(config, 'MIN_24H_QUOTE_VOLUME', 500_000_000)
            top_target = getattr(config, 'TOP_PAIRS_COUNT', 20)

            valid_candidates = []
            for sym, t in tickers.items():
                if config.BASE_QUOTE not in sym or 'BTC' in sym: continue
                
                base_ticker = sym.replace('/', '').split(':')[0]
                if not re.match(r'^[A-Z0-9]{3,12}USDT$', base_ticker): continue

                quote_vol = float(t.get('quoteVolume') or t.get('baseVolume') or 0.0)
                pct_chg = float(t.get('percentage') or 0.0)
                valid_candidates.append({'symbol': sym, 'volume': quote_vol, 'rs_score': pct_chg - btc_chg})

            filtered = [c for c in valid_candidates if c['volume'] >= vol_threshold]

            if len(filtered) < top_target:
                valid_candidates.sort(key=lambda x: x['volume'], reverse=True)
                filtered = valid_candidates[:max(top_target * 2, 40)]

            filtered.sort(key=lambda x: x['rs_score'], reverse=True)
            half = top_target // 2
            top_longs = [c['symbol'] for c in filtered[:half]]
            top_shorts = [c['symbol'] for c in filtered[-half:]]

            selected = list(dict.fromkeys(top_longs + top_shorts))
            if btc_sym not in selected: selected.append(btc_sym)

            self.tracked_symbols = selected
            log_msg = f"Nexus SMC Screener Locked {len(self.tracked_symbols)} valid pairs (10 Long RS + 10 Short RS + BTC)."
            print(f"🔍 {log_msg}")
            state_store.log(log_msg)
        except Exception as e:
            err_msg = f"Screener Exception: {e}. Falling back to config.WATCHLIST"
            print(f"⚠️ {err_msg}")
            state_store.log(err_msg, "WARN")
            fallback = [f"{s.replace('USDT', '')}/USDT:USDT" for s in config.WATCHLIST]
            if 'BTC/USDT:USDT' not in fallback: fallback.append('BTC/USDT:USDT')
            self.tracked_symbols = fallback

    async def run(self):
        last_heartbeat = time.time()
        loop = asyncio.get_running_loop()
        
        try:
            while not shutdown_event.is_set():
                try:
                    bal = await self.mesh.rest_exchange.fetch_balance()
                    equity = float(bal.get('USDT', {}).get('total', config.INITIAL_CAPITAL))
                    free_margin = float(bal.get('USDT', {}).get('free', config.INITIAL_CAPITAL))
                except Exception as e:
                    print(f"⚠️ API Rejection on Balance Fetch: {str(e)[:80]}...")
                    await asyncio.sleep(4.0)
                    continue

                healthy, cb_msg = self.risk_gov.evaluate_circuit_breakers(equity)
                state_store.update_global_state(
                    equity, free_margin, self.risk_gov.peak_equity,
                    cb_msg, self.risk_gov.consecutive_losses, self.risk_gov.cb_locked_until
                )

                if not healthy and not self.cb_active_state:
                    self.cb_active_state = True
                    await telegram_notifier.send_alert(telegram_notifier.format_cb_alert(cb_msg, config.CIRCUIT_BREAKER_LOCKOUT_HOURS))
                elif healthy and self.cb_active_state:
                    self.cb_active_state = False
                    await telegram_notifier.send_alert(telegram_notifier.format_cb_lifted_alert())

                # Evaluate active position stops and pending limit order expiry every tick
                await self.router.evaluate_gtc_cancellations(self.pending_entries, self.current_ers)
                await self.manage_active_positions(equity)
                active_pos = state_store.get_all_active_positions()

                # --- 15-MINUTE CANDLE CLOSE SYNCHRONIZATION (:00, :15, :30, :45 UTC) ---
                now_utc = datetime.now(timezone.utc)
                current_slot = get_15m_bar_slot(now_utc)
                
                # Check if we are at the close of a 15m candle (second >= 2 provides exchange finalization buffer)
                is_candle_close = (now_utc.minute % 15 == 0) and (now_utc.second >= 2)

                if is_candle_close and (current_slot != self.last_scanned_bar_slot):
                    self.last_scanned_bar_slot = current_slot
                    formatted_time = now_utc.strftime('%H:%M:%S UTC')
                    print(f"\n🔔 [15M CANDLE CLOSE DETECTED: {formatted_time}]")
                    state_store.log(f"15m Candle Close at {now_utc.strftime('%H:%M')} UTC. Executing Synchronized Audit...")

                    # 1. Rebalance universe
                    await self.screen_universe()
                    
                    # 2. Cancel pending GTC orders for pairs that dropped out of the universe
                    for sym in list(self.pending_entries.keys()):
                        if sym not in self.tracked_symbols:
                            try:
                                await self.mesh.rest_exchange.cancel_order(self.pending_entries[sym]['order_id'], sym)
                            except Exception: pass
                            del self.pending_entries[sym]

                    # 3. Scan the completed 15m candle across all pairs
                    if healthy and len(active_pos) < config.MAX_CONCURRENT_POSITIONS:
                        await self.scan_for_setups(equity, free_margin, active_pos, loop)

                    # 4. Push the synchronized 15-minute telemetry digest to Telegram
                    await self.broadcast_telemetry(equity, active_pos)

                # --- LIVE HEARTBEAT & COUNTDOWN LOGGER ---
                if (time.time() - last_heartbeat) >= 20:
                    last_heartbeat = time.time()
                    rem_secs = get_seconds_until_next_15m()
                    mins, secs = divmod(rem_secs, 60)
                    print(f"⚙️ [SMC ENGINE] Active: {len(active_pos)} | Pending GTC: {len(self.pending_entries)} | Next 15m Candle Close in: {mins:02d}m {secs:02d}s")

                await asyncio.sleep(1.5)
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"❌ Main Loop Exception: {e}\n{traceback.format_exc()}")
        finally:
            self.cpu_pool.shutdown(wait=True, cancel_futures=True)
            await self.mesh.close()

    async def scan_for_setups(self, equity, free_margin, active_pos, loop):
        active_syms = {p['symbol'] for p in active_pos}.union(set(self.pending_entries.keys()))
        fetch_tasks = {}
        
        for sym in self.tracked_symbols:
            if sym in active_syms or 'BTC' in sym: 
                continue
            fetch_tasks[sym] = asyncio.gather(
                self.mesh.fetch_ohlcv_hybrid(sym, config.TIMEFRAME_MACRO, limit=50),
                self.mesh.fetch_ohlcv_hybrid(sym, config.TIMEFRAME_SETUP, limit=50),
                self.mesh.fetch_ohlcv_hybrid(sym, config.TIMEFRAME_ENTRY, limit=30)
            )
        
        if not fetch_tasks: return
            
        fetched_data = {}
        for sym, task in fetch_tasks.items():
            try:
                res = await task
                if not any(df.empty for df in res): fetched_data[sym] = res
            except Exception: pass

        eval_tasks = []
        for sym, (df_1h, df_15m, df_1m) in fetched_data.items():
            eval_tasks.append(loop.run_in_executor(self.cpu_pool, _cpu_bound_smc_eval, sym, df_1h, df_15m, df_1m))
        
        results = await asyncio.gather(*eval_tasks, return_exceptions=True)
        
        watchlist_payload = []
        for sym, setup in zip(fetched_data.keys(), results):
            if isinstance(setup, Exception): continue
                
            live_px = self.mesh.get_live_price(sym) or 0.0
            er_val = self.current_ers.get(sym, 0.0)
            try:
                c = fetched_data[sym][0]['close'].to_numpy()
                if len(c) > config.ER_PERIOD:
                    nc = abs(c[-1] - c[-config.ER_PERIOD])
                    sc = sum(abs(np.diff(c[-config.ER_PERIOD:])))
                    er_val = nc / sc if sc > 0 else 0.0
            except Exception: pass
            
            self.current_ers[sym] = er_val
            
            if er_val < config.ER_TREND_THRESHOLD: status = "CHOP"
            elif setup and setup['side'] == 'long': status = "LONG FVG"
            elif setup and setup['side'] == 'short': status = "SHORT FVG"
            else: status = "WATCHING"
            
            watchlist_payload.append({'symbol': sym, 'er': er_val, 'price': live_px, 'status': status})

            if setup:
                try:
                    entry_data = await self.router.place_gtc_entry(setup, equity, free_margin)
                    if entry_data:
                        self.pending_entries[sym] = entry_data
                        status = f"GTC {setup['side'].upper()}"
                        watchlist_payload[-1]['status'] = status
                except Exception as e:
                    print(f"❌ Failed to place GTC for {sym}: {e}")

        state_store.update_watchlist(watchlist_payload)

    async def manage_active_positions(self, equity):
        try:
            positions = await self.mesh.rest_exchange.fetch_positions()
            live_active = {p['symbol']: p for p in positions if float(p.get('contracts', 0.0)) > 0}
        except Exception as e:
            return

        for sym, pending in list(self.pending_entries.items()):
            if sym in live_active:
                pos = live_active[sym]
                actual_entry = float(pos.get('entryPrice', pending['entry_price']))
                actual_size = float(pos.get('contracts', pending['size']))
                
                new_pos_record = {
                    'symbol': sym, 'side': pending['side'], 'size': actual_size,
                    'entry_price': actual_entry, 'stop_distance': pending['stop_distance'],
                    'current_sl': pending['initial_sl'], 'take_profit': pending['target_tp'],
                    'initial_sl': pending['initial_sl'], 'margin_locked': pending['margin_locked'],
                    'leverage': pending['leverage'], 'open_time': time.time()
                }
                
                print(f"🚀 POS FILLED: {sym} {pending['side'].upper()} | Entry: {actual_entry}")
                await self.router.place_layered_stop(sym, pending['side'], actual_size, pending['initial_sl'], 'INITIAL_SL')
                state_store.save_position(new_pos_record)
                await telegram_notifier.send_alert(telegram_notifier.format_entry_alert(new_pos_record))
                del self.pending_entries[sym]

        db_positions = state_store.get_all_active_positions()
        for p in db_positions:
            sym = p['symbol']
            
            if sym not in live_active:
                await self.finalize_closed_position(sym, p, equity)
                continue

            live_px = self.mesh.get_live_price(sym)
            if not live_px: continue

            entry = p['entry_price']
            dist = p['stop_distance']
            side = p['side']
            is_long = side == 'long'
            
            r_gain = (live_px - entry) / dist if is_long else (entry - live_px) / dist
            p['r_multiple'] = r_gain

            try:
                if r_gain >= config.RATCHET_4_TRIGGER_R and not p['lock4_hit']:
                    sl = entry + (dist * config.RATCHET_4_LOCK_R) if is_long else entry - (dist * config.RATCHET_4_LOCK_R)
                    p['current_sl'] = sl; p['lock4_hit'] = 1
                    await self.router.place_layered_stop(sym, side, p['size'], sl, 'LOCK_17R')
                    await telegram_notifier.send_alert(telegram_notifier.format_ratchet_alert(p, "17R LOCK", r_gain, dist * 17.0 * p['size']))

                elif r_gain >= config.RATCHET_3_TRIGGER_R and not p['lock3_hit']:
                    sl = entry + (dist * config.RATCHET_3_LOCK_R) if is_long else entry - (dist * config.RATCHET_3_LOCK_R)
                    p['current_sl'] = sl; p['lock3_hit'] = 1
                    await self.router.place_layered_stop(sym, side, p['size'], sl, 'LOCK_12R')
                    await telegram_notifier.send_alert(telegram_notifier.format_ratchet_alert(p, "12R LOCK", r_gain, dist * 12.0 * p['size']))

                elif r_gain >= config.RATCHET_2_TRIGGER_R and not p['lock2_hit']:
                    sl = entry + (dist * config.RATCHET_2_LOCK_R) if is_long else entry - (dist * config.RATCHET_2_LOCK_R)
                    p['current_sl'] = sl; p['lock2_hit'] = 1
                    await self.router.place_layered_stop(sym, side, p['size'], sl, 'LOCK_7R')
                    await telegram_notifier.send_alert(telegram_notifier.format_ratchet_alert(p, "7R LOCK", r_gain, dist * 7.0 * p['size']))

                elif r_gain >= config.RATCHET_1_TRIGGER_R and not p['lock1_hit']:
                    sl = entry + (dist * config.RATCHET_1_LOCK_R) if is_long else entry - (dist * config.RATCHET_1_LOCK_R)
                    p['current_sl'] = sl; p['lock1_hit'] = 1
                    await self.router.place_layered_stop(sym, side, p['size'], sl, 'LOCK_2.5R')
                    await telegram_notifier.send_alert(telegram_notifier.format_ratchet_alert(p, "2.5R LOCK", r_gain, dist * 2.5 * p['size']))

                elif r_gain >= config.BE_TRIGGER_R and not p['be_hit']:
                    buffer = entry * 0.0004
                    sl = entry + buffer if is_long else entry - buffer
                    p['current_sl'] = sl; p['be_hit'] = 1
                    await self.router.place_layered_stop(sym, side, p['size'], sl, 'BREAKEVEN')
                    await telegram_notifier.send_alert(telegram_notifier.format_ratchet_alert(p, "BREAKEVEN", r_gain, 0.0))

                state_store.save_position(p)
            except Exception as e:
                pass

    async def finalize_closed_position(self, sym, pos, current_equity):
        print(f"🏁 RESOLVING EXIT: {sym}")
        state_store.log(f"Position exit detected on {sym}. Purging safety net brackets...")
        await self.router.sweep_orphan_orders(sym)

        net_pnl = 0.0
        exit_px = pos['current_sl']
        raw_sym = sym.split('/')[0] + 'USDT'
        
        try:
            income = await self.mesh.rest_exchange.fapiPrivateGetIncome({
                'symbol': raw_sym,
                'startTime': int(pos['open_time'] * 1000) - 10000,
                'endTime': int(time.time() * 1000) + 5000,
                'limit': 20
            })
            for item in income:
                if item.get('asset') == 'USDT':
                    net_pnl += float(item.get('income', 0.0))
        except Exception:
            gross = (exit_px - pos['entry_price']) * pos['size'] if pos['side'] == 'long' else (pos['entry_price'] - exit_px) * pos['size']
            net_pnl = gross - (pos['size'] * exit_px * 0.0008)

        r_mult = net_pnl / (pos['stop_distance'] * pos['size']) if (pos['stop_distance'] * pos['size']) > 0 else 0.0
        
        if r_mult >= 25.0: outcome = "TARGET 28R HIT"
        elif r_mult >= 1.0: outcome = "PROFIT RATCHET HIT"
        elif r_mult >= -0.1: outcome = "BREAKEVEN HIT"
        else: outcome = "STOP LOSS HIT"

        state_store.remove_position(sym)
        state_store.record_trade_completion(sym, pos['side'], pos['entry_price'], exit_px, net_pnl, r_mult, outcome, current_equity)
        self.risk_gov.record_trade_result(net_pnl)
        
        await telegram_notifier.send_alert(telegram_notifier.format_closed_alert(sym, outcome, net_pnl, r_mult, exit_px, current_equity))

    async def broadcast_telemetry(self, equity, active_positions):
        now_time = datetime.now(timezone.utc).strftime('%H:%M UTC')
        if not active_positions:
            msg = f"📡 <b>15-MIN PORTFOLIO TELEMETRY ({now_time})</b>\n━━━━━━━━━━━━━━━━━━━━\n💰 <b>Equity:</b> <code>${equity:,.2f}</code>\n📦 <b>Active Trades:</b> <code>0/{config.MAX_CONCURRENT_POSITIONS}</code>\n⚡ <i>15m candle closed. Scanning universe for FVG setups...</i>"
        else:
            msg = f"📡 <b>15-MIN PORTFOLIO TELEMETRY ({now_time})</b>\n━━━━━━━━━━━━━━━━━━━━\n💰 <b>Equity:</b> <code>${equity:,.2f}</code>\n📦 <b>Active Trades:</b> <code>{len(active_positions)}/{config.MAX_CONCURRENT_POSITIONS}</code>\n\n"
            for p in active_positions:
                icon = "🟢" if p['side'] == 'long' else "🔴"
                msg += f"{icon} <b>{p['symbol'].split('/')[0]}</b> ({p['side'].upper()}) │ Multiple: <code>{p.get('r_multiple', 0.0):+.2f}R</code>\n"
        await telegram_notifier.send_alert(msg)

async def main():
    engine = NexusSniperEngine()
    try:
        await engine.initialize()
        await engine.run()
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"❌ FATAL ERROR IN MAIN: {e}\n{traceback.format_exc()}")
    finally:
        print("[!] Shutting down Thread Pools and APIs...")
        engine.cpu_pool.shutdown(wait=True, cancel_futures=True)
        await engine.mesh.close()

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[!] Manual interruption. Exiting safely.")
        sys.exit(0)
