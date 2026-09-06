from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import state_store

app = FastAPI(title="NexusSniper Mission Control")

@app.get("/api/telemetry")
async def get_telemetry():
    try:
        bundle = state_store.get_telemetry_bundle()
        trades = bundle.get("closed_trades", [])
        total_trades = len(trades)
        wins = [t['net_pnl'] for t in trades if t['net_pnl'] > 0]
        losses = [t['net_pnl'] for t in trades if t['net_pnl'] < 0]
        
        win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0.0
        gp = sum(wins)
        gl = abs(sum(losses))
        pf = (gp / gl) if gl > 0 else (99.99 if gp > 0 else 0.0)
        exp = (sum(t['net_pnl'] for t in trades) / total_trades) if total_trades > 0 else 0.0

        bundle["analytics"] = {"win_rate": round(win_rate, 1), "profit_factor": round(pf, 2), "expectancy": round(exp, 2), "total_trades": total_trades}
        return bundle
    except Exception as e:
        return {"error": str(e)}

@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>NexusSniper │ Terminal</title>
        <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>⚡</text></svg>">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
        <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700;800&family=Inter:wght@400;600;800&display=swap" rel="stylesheet">
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
        <style>
            :root {
                --bg: #000000; --card: #0c0d12; --border: #222736;
                --green: #00ff88; --red: #ff3366; --yellow: #ffb800; --cyan: #00e5ff;
                --text-white: #ffffff;
            }
            body { background: var(--bg); color: var(--text-white); font-family: 'Inter', sans-serif; padding: 1.5rem; }
            .font-mono { font-family: 'JetBrains Mono', monospace; }
            .card-panel { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 1.25rem; margin-bottom: 1.5rem; }
            .metric-val { font-size: 1.5rem; font-weight: 800; font-family: 'JetBrains Mono', monospace; color: var(--text-white); margin-top: 5px; }
            .header-cyan { color: var(--cyan) !important; font-size: 0.85rem; font-weight: 800; letter-spacing: 1px; text-transform: uppercase; }
            
            .table { --bs-table-bg: transparent !important; color: var(--text-white); margin-bottom: 0; }
            .table td, .table th { background-color: transparent !important; border-bottom: 1px solid var(--border); vertical-align: middle; color: var(--text-white) !important; }
            .table th { color: var(--cyan) !important; font-size: 0.75rem; text-transform: uppercase; font-family: 'Inter', sans-serif; font-weight: 800; border-bottom: 2px solid var(--border); }
            .table td { font-family: 'JetBrains Mono', monospace; font-size: 0.85rem; font-weight: 600; }
            .table tbody tr:hover td { background-color: rgba(255,255,255,0.06) !important; }
            
            .badge-pulse { background: rgba(0,255,136,0.15); color: var(--green); border: 1px solid var(--green); padding: 5px 12px; border-radius: 6px; font-weight: 800; font-size: 0.8rem; }
            .badge-timer { background: rgba(0,229,255,0.15); color: var(--cyan); border: 1px solid var(--cyan); padding: 5px 12px; border-radius: 6px; font-weight: 800; font-size: 0.8rem; margin-right: 10px; }
            .badge-long { background: rgba(0,255,136,0.15); color: var(--green); border: 1px solid rgba(0,255,136,0.4); padding: 3px 8px; border-radius: 4px; font-weight: bold; }
            .badge-short { background: rgba(255,51,102,0.15); color: var(--red); border: 1px solid rgba(255,51,102,0.4); padding: 3px 8px; border-radius: 4px; font-weight: bold; }
            
            .badge-chop { background: #ffb800 !important; color: #000000 !important; font-weight: 800 !important; padding: 4px 10px; border-radius: 4px; display: inline-block; }
            .log-box { background: #000000; border: 1px solid var(--border); height: 260px; overflow-y: auto; padding: 10px; border-radius: 6px; font-size: 0.82rem; }
            .btn-action { background: rgba(0,229,255,0.15); color: var(--cyan); border: 1px solid var(--cyan); font-size: 0.75rem; font-weight: bold; transition: all 0.2s; }
            .btn-success-copy { background: rgba(0,255,136,0.3) !important; color: var(--green) !important; border-color: var(--green) !important; }
            .btn-danger-copy { background: rgba(255,51,102,0.3) !important; color: var(--red) !important; border-color: var(--red) !important; }
        </style>
    </head>
    <body>
        <div class="container-fluid">
            <!-- Header -->
            <div class="d-flex justify-content-between align-items-center mb-4 pb-2 border-bottom border-dark">
                <div>
                    <h3 class="fw-bold mb-0 text-white font-mono">⚡ NEXUSSNIPER (NP) TERMINAL</h3>
                    <div style="color: var(--cyan); font-weight: 800; margin-top: 5px;" class="font-mono">Institutional SMC FVG + 1:28 Trailing Ratchet Matrix</div>
                </div>
                <div class="d-flex align-items-center">
                    <span class="badge-timer font-mono" id="candle-timer">NEXT 15M CLOSE: --:--</span>
                    <span class="badge-pulse font-mono">● LIVE WS PIPELINE</span>
                </div>
            </div>

            <!-- Top KPI Matrix -->
            <div class="d-flex flex-wrap justify-content-between gap-3 mb-4">
                <div class="card-panel text-center flex-fill px-2 mb-0"><div class="header-cyan font-mono">TOTAL EQUITY</div><div class="metric-val" id="eq-val">$0.00</div></div>
                <div class="card-panel text-center flex-fill px-2 mb-0"><div class="header-cyan font-mono">FREE MARGIN</div><div class="metric-val" id="margin-val">$0.00</div></div>
                <div class="card-panel text-center flex-fill px-2 mb-0"><div class="header-cyan font-mono" style="color: var(--yellow) !important;">ACTIVE EXPOSURE</div><div class="metric-val" id="pos-count">0 / 10</div></div>
                <div class="card-panel text-center flex-fill px-2 mb-0"><div class="header-cyan font-mono">RESOLVED TRADES</div><div class="metric-val" id="trades-val">0</div></div>
                <div class="card-panel text-center flex-fill px-2 mb-0"><div class="header-cyan font-mono">WIN RATE</div><div class="metric-val" style="color: var(--green);" id="wr-val">0.0%</div></div>
                <div class="card-panel text-center flex-fill px-2 mb-0"><div class="header-cyan font-mono">PROFIT FACTOR</div><div class="metric-val text-info" id="pf-val">0.00</div></div>
                <div class="card-panel text-center flex-fill px-2 mb-0"><div class="header-cyan font-mono">EXPECTANCY</div><div class="metric-val" id="exp-val">$0.00</div></div>
                <div class="card-panel text-center flex-fill px-2 mb-0"><div class="header-cyan font-mono">SYSTEM STATUS</div><div class="metric-val font-mono fs-6" id="status-val">ACTIVE</div></div>
            </div>

            <!-- Active Exposure Table -->
            <div class="card-panel">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h5 class="fw-bold mb-0 text-white font-mono">📡 Active Exposure & Trailing Safety Nets</h5>
                    <button class="btn btn-sm btn-action font-mono" id="btn-copy-pos" onclick="copyPositions(this)">COPY POSITIONS</button>
                </div>
                <div class="table-responsive">
                    <table class="table">
                        <thead>
                            <tr>
                                <th>Symbol</th><th>Side</th><th>Size</th><th>Entry</th><th>Stop Loss</th>
                                <th>Target 28R</th><th>Margin ($)</th><th>R-Multiple</th><th>Status</th>
                            </tr>
                        </thead>
                        <tbody id="pos-body">
                            <tr><td colspan="9" class="text-center py-4 text-white">No active exposure. Scanning for FVG sweeps...</td></tr>
                        </tbody>
                    </table>
                </div>
            </div>

            <div class="card-panel">
                <h5 class="fw-bold mb-3 text-white font-mono">📈 Cumulative Equity Curve</h5>
                <div style="height: 240px; width: 100%;"><canvas id="equityChart"></canvas></div>
            </div>

            <div class="row g-3">
                <div class="col-lg-4">
                    <div class="card-panel h-100 mb-0">
                        <h6 class="fw-bold mb-3 header-cyan font-mono">📜 Trade History</h6>
                        <div class="table-responsive" style="max-height: 260px; overflow-y: auto;">
                            <table class="table">
                                <thead><tr><th>Symbol</th><th>Outcome</th><th>PnL ($)</th><th>Eq After</th></tr></thead>
                                <tbody id="history-body"></tbody>
                            </table>
                        </div>
                    </div>
                </div>
                
                <div class="col-lg-4">
                    <div class="card-panel h-100 mb-0">
                        <h6 class="fw-bold mb-3 header-cyan font-mono">🌐 SMC Macro Watchlist (Top 20)</h6>
                        <div class="table-responsive" style="max-height: 260px; overflow-y: auto;">
                            <table class="table">
                                <thead><tr><th>Asset</th><th>ER (1h)</th><th>Status</th></tr></thead>
                                <tbody id="watchlist-body"></tbody>
                            </table>
                        </div>
                    </div>
                </div>

                <div class="col-lg-4">
                    <div class="card-panel h-100 mb-0">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <h6 class="fw-bold mb-0 header-cyan font-mono">📋 System Audit Log</h6>
                            <button class="btn btn-sm btn-action font-mono" id="btn-copy-log" onclick="copyLogs(this)">COPY LOGS</button>
                        </div>
                        <div class="log-box font-mono" id="logs-box"></div>
                    </div>
                </div>
            </div>
        </div>

        <script>
            let cachedPositions = [];
            let chart = null;
            const fmt = (num, dec=4) => Number(num || 0).toFixed(dec);

            function updateCountdown() {
                const now = new Date();
                const m = now.getUTCMinutes();
                const s = now.getUTCSeconds();
                const remM = 14 - (m % 15);
                const remS = 59 - s;
                document.getElementById('candle-timer').innerText = `NEXT 15M CLOSE: ${String(remM).padStart(2, '0')}:${String(remS).padStart(2, '0')}`;
            }

            function initChart() {
                const ctx = document.getElementById('equityChart').getContext('2d');
                chart = new Chart(ctx, {
                    type: 'line',
                    data: { labels: ['Start'], datasets: [{ label: 'Equity ($)', data: [5000], borderColor: '#00e5ff', backgroundColor: 'rgba(0, 229, 255, 0.1)', borderWidth: 2, tension: 0.15, fill: true, pointRadius: 2 }] },
                    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { x: { grid: { color: '#222736' }, ticks: { color: '#ffffff' } }, y: { grid: { color: '#222736' }, ticks: { color: '#ffffff' } } } }
                });
            }

            function triggerSuccess(btn) {
                const orig = btn.innerText;
                btn.innerText = "COPIED! ✔";
                btn.classList.add("btn-success-copy");
                setTimeout(() => { btn.innerText = orig; btn.classList.remove("btn-success-copy"); }, 1500);
            }

            function triggerError(btn) {
                const orig = btn.innerText;
                btn.innerText = "NO EXPOSURE";
                btn.classList.add("btn-danger-copy");
                setTimeout(() => { btn.innerText = orig; btn.classList.remove("btn-danger-copy"); }, 1500);
            }

            function copyToClipboard(text, btn) {
                const ta = document.createElement("textarea");
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                triggerSuccess(btn);
            }

            function copyLogs(btn) { copyToClipboard(document.getElementById('logs-box').innerText, btn); }
            
            function copyPositions(btn) {
                if(!cachedPositions || cachedPositions.length === 0) {
                    triggerError(btn);
                    return;
                }
                let out = "SYM\\tSIDE\\tSIZE\\tENTRY\\tSL\\tTP\\n";
                cachedPositions.forEach(p => { out += `${p.symbol}\\t${p.side}\\t${p.size}\\t${p.entry_price}\\t${p.current_sl}\\t${p.take_profit}\\n`; });
                copyToClipboard(out, btn);
            }

            async function updateTelemetry() {
                try {
                    const res = await fetch('/api/telemetry');
                    if(!res.ok) return;
                    const d = await res.json();
                    const st = d.state || {};
                    const an = d.analytics || {};
                    cachedPositions = d.positions || [];

                    document.getElementById('eq-val').innerText = '$' + Number(st.equity || 5000).toLocaleString('en-US', {minimumFractionDigits:2});
                    document.getElementById('margin-val').innerText = '$' + Number(st.free_margin || 5000).toLocaleString('en-US', {minimumFractionDigits:2});
                    document.getElementById('pos-count').innerText = `${cachedPositions.length} / 10`;
                    document.getElementById('trades-val').innerText = an.total_trades || 0;
                    document.getElementById('wr-val').innerText = `${an.win_rate || 0}%`;
                    document.getElementById('pf-val').innerText = (an.profit_factor || 0.0).toFixed(2);
                    document.getElementById('exp-val').innerText = '$' + (an.expectancy || 0.0).toFixed(2);
                    
                    const statusEl = document.getElementById('status-val');
                    statusEl.innerText = st.status || "ACTIVE";
                    statusEl.style.color = (st.status && st.status.includes("CIRCUIT")) ? "var(--red)" : "var(--green)";

                    const pb = document.getElementById('pos-body');
                    pb.innerHTML = cachedPositions.length ? cachedPositions.map(p => {
                        let statusTag = '<span class="badge" style="background:#b366ff; color:#fff;">Initial SL</span>';
                        if(p.lock4_hit) statusTag = '<span class="badge bg-info text-dark">17R Lock</span>';
                        else if(p.lock3_hit) statusTag = '<span class="badge" style="background:#00e5ff; color:#000;">12R Lock</span>';
                        else if(p.lock2_hit) statusTag = '<span class="badge bg-warning text-dark">7R Lock</span>';
                        else if(p.lock1_hit) statusTag = '<span class="badge bg-warning text-dark">2.5R Lock</span>';
                        else if(p.be_hit) statusTag = '<span class="badge bg-success">Breakeven</span>';

                        return `<tr>
                            <td class="fw-bold text-white">${p.symbol.split('/')[0]}</td>
                            <td><span class="${p.side === 'long' ? 'badge-long' : 'badge-short'}">${p.side.toUpperCase()}</span></td>
                            <td>${fmt(p.size, 2)}</td>
                            <td>$${fmt(p.entry_price)}</td>
                            <td style="color:var(--yellow); font-weight:bold;">$${fmt(p.current_sl)}</td>
                            <td style="color:var(--cyan); font-weight:bold;">$${fmt(p.take_profit)}</td>
                            <td>$${fmt(p.margin_locked, 2)}</td>
                            <td class="${p.r_multiple >= 0 ? 'text-success' : 'text-danger'}" style="font-weight:bold;">${fmt(p.r_multiple, 2)}R</td>
                            <td>${statusTag}</td>
                        </tr>`;
                    }).join('') : '<tr><td colspan="9" class="text-center py-4 text-white">No active exposure. Scanning for FVG sweeps...</td></tr>';

                    const hb = document.getElementById('history-body');
                    const trades = (d.closed_trades || []).slice(-10).reverse();
                    hb.innerHTML = trades.length ? trades.map(t => {
                        const outBadge = t.outcome.includes('PROFIT') || t.outcome.includes('TARGET') ? `<span class="text-success fw-bold">${t.outcome}</span>` : 
                                         (t.outcome.includes('BREAKEVEN') ? `<span class="text-info fw-bold">${t.outcome}</span>` : `<span class="text-danger fw-bold">${t.outcome}</span>`);
                        return `<tr>
                            <td class="fw-bold text-white">${t.symbol.split('/')[0]}</td>
                            <td>${outBadge}</td>
                            <td class="${t.net_pnl >= 0 ? 'text-success' : 'text-danger'}" style="font-weight:bold;">${t.net_pnl >= 0 ? '+' : ''}$${fmt(t.net_pnl, 2)}</td>
                            <td class="text-white">$${fmt(t.equity_after, 2)}</td>
                        </tr>`
                    }).join('') : '<tr><td colspan="4" class="text-center py-3 text-white">No closed trades.</td></tr>';

                    const wb = document.getElementById('watchlist-body');
                    const watch = d.watchlist || [];
                    wb.innerHTML = watch.length ? watch.map(w => {
                        let stBadge = `<span class="badge bg-secondary">${w.status}</span>`;
                        if(w.status === 'CHOP') {
                            stBadge = `<span class="badge-chop">CHOP</span>`;
                        } else if(w.status.includes('LONG')) {
                            stBadge = `<span class="badge bg-success text-white">LONG SETUP</span>`;
                        } else if(w.status.includes('SHORT')) {
                            stBadge = `<span class="badge bg-danger text-white">SHORT SETUP</span>`;
                        } else if(w.status.includes('GTC')) {
                            stBadge = `<span class="badge bg-info text-dark">${w.status}</span>`;
                        }
                        
                        return `<tr>
                            <td class="fw-bold text-white">${w.symbol.split('/')[0]}</td>
                            <td class="${w.er >= 0.25 ? 'text-info' : 'text-white'}" style="font-weight:bold;">${fmt(w.er, 2)}</td>
                            <td>${stBadge}</td>
                        </tr>`
                    }).join('') : '<tr><td colspan="3" class="text-center py-3 text-white">Awaiting Watchlist Scan...</td></tr>';

                    const lb = document.getElementById('logs-box');
                    lb.innerHTML = (d.logs || []).slice(0, 50).map(l => `
                        <div style="margin-bottom: 4px;">
                            <span style="color:var(--cyan); font-weight:bold;">[${new Date(l.timestamp * 1000).toLocaleTimeString()}]</span> 
                            <span style="color:${l.level === 'ERROR' ? 'var(--red)' : (l.level === 'WARN' ? 'var(--yellow)' : '#ffffff')}">${l.message}</span>
                        </div>
                    `).join('');

                    if (chart && (d.closed_trades || []).length) {
                        const data = [5000];
                        d.closed_trades.forEach(t => { data.push(t.equity_after); });
                        chart.data.labels = data.map((_, i) => i === 0 ? 'Start' : `T${i}`);
                        chart.data.datasets[0].data = data;
                        chart.update('none');
                    }
                } catch(e) { 
                    console.error("Telemetry error:", e); 
                }
            }
            
            window.onload = () => { 
                initChart(); 
                updateTelemetry(); 
                updateCountdown();
                setInterval(updateTelemetry, 1500); 
                setInterval(updateCountdown, 1000);
            };
        </script>
    </body>
    </html>
    """

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
