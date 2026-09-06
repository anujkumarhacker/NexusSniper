import sqlite3
import os
import time

DB_PATH = os.path.join(os.path.dirname(__file__), "nexus_sniper.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS bot_state (
        id INTEGER PRIMARY KEY, timestamp REAL, equity REAL, free_margin REAL,
        peak_equity REAL, status TEXT, consecutive_losses INTEGER, cb_locked_until REAL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS active_positions (
        symbol TEXT PRIMARY KEY, side TEXT, size REAL, entry_price REAL, stop_distance REAL,
        current_sl REAL, take_profit REAL, initial_sl REAL, margin_locked REAL, leverage INTEGER,
        r_multiple REAL, open_time REAL, be_hit INTEGER DEFAULT 0, lock1_hit INTEGER DEFAULT 0,
        lock2_hit INTEGER DEFAULT 0, lock3_hit INTEGER DEFAULT 0, lock4_hit INTEGER DEFAULT 0
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS active_brackets (
        id INTEGER PRIMARY KEY AUTOINCREMENT, symbol TEXT, order_id TEXT, order_type TEXT, price REAL, tier TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS pending_entries (
        symbol TEXT PRIMARY KEY, order_id TEXT, side TEXT, entry_price REAL, stop_loss REAL,
        risk_distance REAL, placed_time REAL, target_5r REAL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS closed_trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL, symbol TEXT, side TEXT,
        entry_price REAL, exit_price REAL, net_pnl REAL, realized_r REAL, outcome TEXT, equity_after REAL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS system_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, timestamp REAL, level TEXT, message TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS watchlist (
        symbol TEXT PRIMARY KEY, er REAL, price REAL, status TEXT
    )""")

    conn.commit()
    conn.close()

def log(msg, level="INFO"):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO system_logs (timestamp, level, message) VALUES (?, ?, ?)", (time.time(), level, msg))
        c.execute("DELETE FROM system_logs WHERE id NOT IN (SELECT id FROM system_logs ORDER BY id DESC LIMIT 500)")
        conn.commit()
        conn.close()
    except Exception: pass

def update_global_state(equity, free_margin, peak_eq, status, losses, cb_until):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT INTO bot_state (timestamp, equity, free_margin, peak_equity, status, consecutive_losses, cb_locked_until)
            VALUES (?, ?, ?, ?, ?, ?, ?)""", (time.time(), equity, free_margin, peak_eq, status, losses, cb_until))
        c.execute("DELETE FROM bot_state WHERE id NOT IN (SELECT id FROM bot_state ORDER BY id DESC LIMIT 10)")
        conn.commit()
        conn.close()
    except Exception: pass

def save_position(pos):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT OR REPLACE INTO active_positions 
            (symbol, side, size, entry_price, stop_distance, current_sl, take_profit, initial_sl, margin_locked, leverage, r_multiple, open_time, be_hit, lock1_hit, lock2_hit, lock3_hit, lock4_hit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pos['symbol'], pos['side'], pos['size'], pos['entry_price'], pos['stop_distance'], pos['current_sl'], pos['take_profit'], pos['initial_sl'], pos['margin_locked'], pos['leverage'], pos.get('r_multiple', 0.0), pos['open_time'], int(pos.get('be_hit', 0)), int(pos.get('lock1_hit', 0)), int(pos.get('lock2_hit', 0)), int(pos.get('lock3_hit', 0)), int(pos.get('lock4_hit', 0))))
        conn.commit()
        conn.close()
    except Exception as e: log(f"Failed to save pos {pos['symbol']}: {e}", "ERROR")

def remove_position(symbol):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM active_positions WHERE symbol=?", (symbol,))
        conn.commit()
        conn.close()
    except Exception: pass

def record_bracket_order(symbol, order_id, order_type, price, tier):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO active_brackets (symbol, order_id, order_type, price, tier) VALUES (?, ?, ?, ?, ?)", (symbol, order_id, order_type, price, tier))
        conn.commit()
        conn.close()
    except Exception: pass

def get_bracket_orders(symbol):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT order_id FROM active_brackets WHERE symbol=?", (symbol,))
        rows = c.fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception: return []

def purge_symbol_brackets(symbol):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM active_brackets WHERE symbol=?", (symbol,))
        conn.commit()
        conn.close()
    except Exception: pass

def record_trade_completion(symbol, side, entry, exit_px, net_pnl, r_mult, outcome, equity_after):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""INSERT INTO closed_trades 
            (timestamp, symbol, side, entry_price, exit_price, net_pnl, realized_r, outcome, equity_after)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""", (time.time(), symbol, side, entry, exit_px, net_pnl, r_mult, outcome, equity_after))
        conn.commit()
        conn.close()
    except Exception: pass

def get_all_active_positions():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        rows = c.execute("SELECT * FROM active_positions").fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception: return []

def update_watchlist(watchlist_data):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("DELETE FROM watchlist")
        for data in watchlist_data:
            c.execute("INSERT INTO watchlist (symbol, er, price, status) VALUES (?, ?, ?, ?)",
                      (data['symbol'], data['er'], data['price'], data['status']))
        conn.commit()
        conn.close()
    except Exception as e: log(f"Watchlist update error: {e}")

def get_telemetry_bundle():
    data = {"state": {}, "positions": [], "closed_trades": [], "logs": [], "watchlist": []}
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        
        st = c.execute("SELECT * FROM bot_state ORDER BY id DESC LIMIT 1").fetchone()
        if st: data["state"] = dict(st)
        
        data["positions"] = [dict(p) for p in c.execute("SELECT * FROM active_positions").fetchall()]
        data["closed_trades"] = [dict(t) for t in c.execute("SELECT * FROM closed_trades ORDER BY id ASC").fetchall()]
        data["logs"] = [dict(l) for l in c.execute("SELECT * FROM system_logs ORDER BY id DESC LIMIT 50").fetchall()]
        data["watchlist"] = [dict(w) for w in c.execute("SELECT * FROM watchlist ORDER BY er DESC").fetchall()]
        conn.close()
    except Exception as e:
        data["error"] = str(e)
    return data
