const cards = document.getElementById('cards');
const meta = document.getElementById('meta');
const refreshBtn = document.getElementById('refreshBtn');

function renderFrame(frame) {
  const s = frame.latest_signal;
  const b = frame.backtest;
  return `
    <article class="card">
      <h2>${frame.interval}</h2>
      <p>最新價格：<strong>${frame.latest_price}</strong></p>
      <p>訊號：<strong class="signal-${s}">${s}</strong></p>
      <p class="small">EMA12: ${frame.ema_fast} / EMA34: ${frame.ema_slow}</p>
      <p class="small">Momentum(10): ${frame.momentum}% / RSI: ${frame.rsi}</p>
      <p class="small">K棒時間：${new Date(frame.as_of).toLocaleString()}</p>
      <hr />
      <h3>虛擬交易 + 回測摘要</h3>
      <p>初始資金：${b.initial_cash.toLocaleString()}</p>
      <p>最終資金：${b.final_cash.toLocaleString()}</p>
      <p>總報酬：${b.total_return_pct}% / 勝率：${b.win_rate_pct}%</p>
      <p>平倉次數：${b.close_count}</p>
      <pre>${JSON.stringify(b.trades.slice(-5), null, 2)}</pre>
    </article>
  `;
}

async function loadData(force = false) {
  const endpoint = force ? '/api/refresh' : '/api/signal';
  const method = force ? 'POST' : 'GET';
  const res = await fetch(endpoint, { method });
  const data = await res.json();

  if (data.detail) {
    meta.textContent = `錯誤：${data.detail}`;
    return;
  }

  meta.textContent = `標的：${data.symbol} ｜ 更新：${new Date(data.updated_at).toLocaleString()} ｜ 規則：7天強平 / 10%停損 / ${Math.round(data.rules.trailing_pct * 100)}%追蹤停利`;

  cards.innerHTML = Object.values(data.timeframes)
    .map(renderFrame)
    .join('');
}

refreshBtn.addEventListener('click', () => loadData(true));
loadData();
setInterval(loadData, 30000);
