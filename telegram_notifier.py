import aiohttp
import asyncio
import config

async def send_alert(message_html: str):
    if not getattr(config, 'ENABLE_TELEGRAM', False) or not config.TELEGRAM_BOT_TOKEN or "YOUR_" in config.TELEGRAM_BOT_TOKEN: return

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

def format_entry_alert(pos):
    icon = "🟢" if pos['side'] == 'long' else "🔴"
    sym = pos['symbol'].split('/')[0]
    risk_usd = pos['stop_distance'] * pos['size']
    tp_usd = abs(pos['take_profit'] - pos['entry_price']) * pos['size']
    return (f"{icon} <b>NEW {pos['side'].upper()} POSITION FILLED</b>\n━━━━━━━━━━━━━━━━━━━━\n🏷 <b>Asset:</b> <code>{sym}</code>\n💵 <b>Entry Price:</b> <code>${pos['entry_price']:.4f}</code>\n📦 <b>Size:</b> <code>{pos['size']}</code>\n🛡 <b>Init Stop:</b> <code>${pos['initial_sl']:.4f}</code> <i>(-${risk_usd:.2f})</i>\n🎯 <b>Terminal Target:</b> <code>${pos['take_profit']:.4f}</code> <i>(+${tp_usd:.2f})</i>\n💰 <b>Margin Locked:</b> <code>${pos['margin_locked']:.2f}</code>\n━━━━━━━━━━━━━━━━━━━━")

def format_ratchet_alert(pos, tier, r_gain, locked_pnl):
    sym = pos['symbol'].split('/')[0]
    pnl_sign = "+" if locked_pnl >= 0 else "-"
    return (f"🔒 <b>RATCHET DEPLOYED: {tier}</b>\n━━━━━━━━━━━━━━━━━━━━\n🏷 <b>Asset:</b> <code>{sym}</code>\n📈 <b>Expansion Gain:</b> <code>{r_gain:+.2f}R</code>\n🛡 <b>New Stop Level:</b> <code>${pos['current_sl']:.4f}</code>\n💵 <b>Secured Profit:</b> <code>{pnl_sign}${abs(locked_pnl):.2f}</code>\nℹ️ <i>Older safety net orders preserved.</i>\n━━━━━━━━━━━━━━━━━━━━")

def format_closed_alert(sym, outcome, pnl, r_mult, exit_px, equity):
    icon = "🎯" if "TP" in outcome else ("🔒" if "PROFIT" in outcome else ("🛡️" if "BE" in outcome else "🛑"))
    pnl_sign = "+" if pnl >= 0 else "-"
    return (f"{icon} <b>POSITION RESOLVED: {sym.split('/')[0]}</b>\n━━━━━━━━━━━━━━━━━━━━\n📋 <b>Outcome:</b> <code>{outcome}</code>\n🏁 <b>Exit Price:</b> <code>${exit_px:.4f}</code>\n📈 <b>Realized Multiple:</b> <code>{r_mult:+.2f}R</code>\n💵 <b>Net PnL:</b> <code>{pnl_sign}${abs(pnl):.2f}</code>\n━━━━━━━━━━━━━━━━━━━━\n💰 <b>Total Equity:</b> <code>${equity:,.2f}</code>")
