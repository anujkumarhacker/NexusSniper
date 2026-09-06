import aiohttp
import asyncio
import config

async def send_alert(message_html: str):
    if not getattr(config, 'ENABLE_TELEGRAM', False) or not config.TELEGRAM_BOT_TOKEN or "YOUR_" in config.TELEGRAM_BOT_TOKEN: 
        return

    url = f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": config.TELEGRAM_CHAT_ID, "text": message_html, "parse_mode": "HTML", "disable_web_page_preview": True}

    for _ in range(2):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=4)) as resp:
                    if resp.status == 200: return
                    await asyncio.sleep(1)
        except Exception:
            await asyncio.sleep(1)

def format_startup_alert(pairs_count):
    risk = getattr(config, 'RISK_PER_TRADE_PCT', 0.015) * 100
    return (f"🚀 <b>NEXUSSNIPER ENGINE ONLINE</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"⚙️ <b>Mode:</b> <code>Binance Futures Testnet</code>\n"
            f"🔍 <b>Universe:</b> <code>Monitoring {pairs_count} Pairs</code>\n"
            f"🛡️ <b>Risk:</b> <code>{risk:.1f}% Per Trade</code>\n"
            f"✅ <i>All systems nominal. Event loop active.</i>")

def format_cb_alert(reason, hours):
    return (f"🛑 <b>CIRCUIT BREAKER TRIPPED</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"⚠️ <b>Reason:</b> <code>{reason}</code>\n"
            f"🔒 <b>Action:</b> <code>Trading halted for {hours}h</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n<i>Capital preservation protocol engaged.</i>")

def format_cb_lifted_alert():
    return f"✅ <b>CIRCUIT BREAKER LIFTED</b>\n━━━━━━━━━━━━━━━━━━━━\n<i>Trading operations automatically resumed.</i>"

def format_gtc_placed_alert(sym, side, px):
    icon = "🟢" if side == 'long' else "🔴"
    return (f"⏳ <b>PENDING GTC DEPLOYED</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷 <b>Asset:</b> <code>{sym.replace('USDT', '')}</code>\n"
            f"🎯 <b>Action:</b> <code>{side.upper()} Limit</code>\n"
            f"💵 <b>At Price:</b> <code>${px:.5f}</code>\n"
            f"<i>Awaiting FVG fill...</i>")

def format_gtc_cancelled_alert(sym, reason):
    return (f"🚫 <b>GTC ORDER REVOKED</b>\n━━━━━━━━━━━━━━━━━━━━\n"
            f"🏷 <b>Asset:</b> <code>{sym.replace('USDT', '')}</code>\n"
            f"⚠️ <b>Reason:</b> <code>{reason}</code>\n"
            f"<i>Order removed from exchange.</i>")

def format_entry_alert(pos):
    icon = "🟢" if pos['side'] == 'long' else "🔴"
    sym = pos['symbol'].replace('USDT', '')
    risk_usd = pos['stop_distance'] * pos['size']
    tp_usd = abs(pos['take_profit'] - pos['entry_price']) * pos['size']
    return (f"{icon} <b>NEW {pos['side'].upper()} POSITION FILLED</b>\n━━━━━━━━━━━━━━━━━━━━\n🏷 <b>Asset:</b> <code>{sym}</code> ({pos['leverage']}x Isolated)\n💵 <b>Entry Price:</b> <code>${pos['entry_price']:.4f}</code>\n📦 <b>Size:</b> <code>{pos['size']}</code>\n🛡 <b>Init Stop:</b> <code>${pos['initial_sl']:.4f}</code> <i>(-${risk_usd:.2f})</i>\n🎯 <b>Terminal Target:</b> <code>${pos['take_profit']:.4f}</code> <i>(+${tp_usd:.2f})</i>\n💰 <b>Margin Locked:</b> <code>${pos['margin_locked']:.2f}</code>\n━━━━━━━━━━━━━━━━━━━━")

def format_ratchet_alert(pos, tier, r_gain, locked_pnl):
    sym = pos['symbol'].replace('USDT', '')
    pnl_sign = "+" if locked_pnl >= 0 else "-"
    return (f"🔒 <b>RATCHET DEPLOYED: {tier}</b>\n━━━━━━━━━━━━━━━━━━━━\n🏷 <b>Asset:</b> <code>{sym}</code>\n📈 <b>Expansion Gain:</b> <code>{r_gain:+.2f}R</code>\n🛡 <b>New Stop Level:</b> <code>${pos['current_sl']:.4f}</code>\n💵 <b>Secured Profit:</b> <code>{pnl_sign}${abs(locked_pnl):.2f}</code>\nℹ️ <i>Older safety net orders preserved.</i>\n━━━━━━━━━━━━━━━━━━━━")

def format_closed_alert(sym, outcome, pnl, r_mult, exit_px, equity):
    icon = "🎯" if "TP" in outcome else ("🔒" if "PROFIT" in outcome else ("🛡️" if "BE" in outcome else "🛑"))
    pnl_sign = "+" if pnl >= 0 else "-"
    return (f"{icon} <b>POSITION RESOLVED: {sym.replace('USDT', '')}</b>\n━━━━━━━━━━━━━━━━━━━━\n📋 <b>Outcome:</b> <code>{outcome}</code>\n🏁 <b>Exit Price:</b> <code>${exit_px:.4f}</code>\n📈 <b>Realized Multiple:</b> <code>{r_mult:+.2f}R</code>\n💵 <b>Net PnL:</b> <code>{pnl_sign}${abs(pnl):.2f}</code>\n━━━━━━━━━━━━━━━━━━━━\n💰 <b>Total Equity:</b> <code>${equity:,.2f}</code>")
