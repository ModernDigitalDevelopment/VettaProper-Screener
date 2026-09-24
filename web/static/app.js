/* Vetta Proper Screener — UI */
'use strict';

let DEFAULTS = {}, PRESETS = {}, LAST = null, CURRENT = {}, PROVIDERS = {}, PROVIDER = 'polygon';

/* Which criteria are exposed as toggles, and how they render.
   Every one of these was a variable in the backtest grid. */
const FIELDS = [
  { group: 'Structure', items: [
    { k: 'structure', t: 'select', label: 'Structure',
      opts: [['bull_put','Bull put spread'],['bear_call','Bear call spread'],['iron_condor','Iron condor']] },
    { k: 'short_delta', t: 'num', label: 'Target short delta', step: 0.01, min: 0.05, max: 0.60 },
    { k: 'delta_tol', t: 'num', label: 'Delta tolerance (±)', step: 0.01, min: 0.01, max: 0.30,
      help: 'Wide tolerance lets the ranking pick; tight tolerance forces a delta.' },
    { k: 'width', t: 'num', label: 'Strike width ($)', step: 1, min: 1, max: 50 },
  ]},
  { group: 'Expiry', items: [
    { k: 'target_dte', t: 'num', label: 'Target DTE', step: 1, min: 1, max: 60 },
    { k: 'dte_tol', t: 'num', label: 'DTE tolerance (±)', step: 1, min: 0, max: 15 },
  ]},
  { group: 'Edge gates', items: [
    { k: 'min_risk_reward', t: 'num', label: 'Min risk:reward', step: 0.05, min: 0, max: 1,
      help: '0.20 = collect $1 for every $5 at risk. 0 disables.' },
    { k: 'use_ivrv', t: 'bool', label: 'Use IV/RV filter',
      help: 'OFF by default: in testing it REDUCED performance once trend and earnings filters were applied.' },
    { k: 'min_ivrv', t: 'num', label: 'Min IV/RV', step: 0.05, min: 0, max: 3, dep: 'use_ivrv' },
  ]},
  { group: 'Event blackout', items: [
    { k: 'earnings_blackout_days', t: 'num', label: 'Blackout window (days)', step: 1, min: 0, max: 30,
      help: 'Highest-value single filter in testing. 0 disables.' },
    { k: 'blackout_exdiv', t: 'bool', label: 'Also block ex-dividend' },
  ]},
  { group: 'Trend', items: [
    { k: 'trend_mode', t: 'select', label: 'Trend filter',
      opts: [['s10_50','Price>50SMA and 10SMA>50SMA (best)'],['s10_30','Price>50SMA and 10SMA>30SMA'],
             ['below50','Price<50SMA (bearish)'],['none','No trend filter']] },
  ]},
  { group: 'Liquidity', items: [
    { k: 'max_rel_spread', t: 'num', label: 'Max bid/ask spread', step: 0.01, min: 0.01, max: 0.5,
      help: '0.10 = spread no wider than 10% of mid.' },
    { k: 'min_open_interest', t: 'num', label: 'Min open interest', step: 5, min: 0, max: 1000 },
    { k: 'min_credit', t: 'num', label: 'Min credit ($)', step: 0.05, min: 0, max: 5 },
  ]},
  { group: 'Sizing & portfolio', items: [
    { k: 'equity', t: 'num', label: 'Account equity ($)', step: 1000, min: 1000 },
    { k: 'max_pct_per_position', t: 'num', label: 'Risk per position', step: 0.005, min: 0.005, max: 0.25,
      help: 'Fraction of equity at risk. 0.05 = 5%.' },
    { k: 'max_per_sector', t: 'num', label: 'Max per sector', step: 1, min: 1, max: 10,
      help: 'Sector concentration caused 84% of the loss in the predecessor system.' },
    { k: 'max_open', t: 'num', label: 'Max open positions', step: 1, min: 1, max: 50 },
    { k: 'max_new_per_day', t: 'num', label: 'Max new per day', step: 1, min: 1, max: 20 },
  ]},
  { group: 'Exits', items: [
    { k: 'profit_target', t: 'num', label: 'Profit target', step: 0.05, min: 0.1, max: 1,
      help: '0.80 = close at 80% of max profit.' },
    { k: 'exit_days_before_expiry', t: 'num', label: 'Exit days before expiry', step: 1, min: 0, max: 10 },
  ]},
  { group: 'Ranking', items: [
    { k: 'rank_mode', t: 'select', label: 'Rank by',
      opts: [['score','Fitted delta × risk-reward (validated)'],['rr','Risk:reward only'],
             ['cw','Credit / width'],['delta','Lowest delta']],
      help: 'Fitted model beat credit/width by +21% net in backtest.' },
  ]},
];

const $ = s => document.querySelector(s);
const fmt = (n,d=2) => n==null ? '—' : Number(n).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d});
const money = n => n==null ? '—' : '$'+Number(n).toLocaleString(undefined,{maximumFractionDigits:0});

async function init(){
  const r = await fetch('/api/criteria/defaults').then(r=>r.json());
  DEFAULTS = r.defaults; PRESETS = r.presets;
  CURRENT = {...DEFAULTS};

  const sel = $('#preset-select');
  sel.innerHTML = Object.entries(PRESETS)
    .map(([k,v])=>`<option value="${k}">${v.label}</option>`).join('')
    + '<option value="__custom">Custom</option>';
  sel.value = 'validated_conservative';
  applyPreset('validated_conservative');

  sel.onchange = e => { if(e.target.value!=='__custom') applyPreset(e.target.value); };
  $('#reset-btn').onclick = () => { sel.value='validated_conservative'; applyPreset('validated_conservative'); };
  $('#scan-btn').onclick = runScan;

  await initProviders();
  $('#show-all').onchange = () => LAST && render(LAST);
  $('#order-cancel').onclick = () => $('#order-modal').classList.add('hidden');

  loadStatus();
}

function applyPreset(name){
  const p = PRESETS[name];
  CURRENT = {...DEFAULTS, ...(p?.criteria||{})};
  const m = p?.measured;
  $('#preset-measured').innerHTML = m
    ? `Backtested: <span class="text-emerald-400">${m.win_rate}% win</span> · ${m.trades} trades ·
       PF ${m.profit_factor} · <span class="text-amber-400">${m.max_dd_pct}% max DD</span> ·
       peak risk ${m.peak_risk_pct}% · ${m.period}`
    : '';
  buildForm();
}

function buildForm(){
  const wrap = $('#criteria-form');
  wrap.innerHTML = FIELDS.map(g => `
    <div>
      <div class="text-[11px] uppercase tracking-wide text-slate-500 mb-1.5 font-semibold">${g.group}</div>
      <div class="space-y-2">${g.items.map(renderField).join('')}</div>
    </div>`).join('');

  wrap.querySelectorAll('[data-k]').forEach(el => {
    el.onchange = () => {
      const k = el.dataset.k;
      CURRENT[k] = el.type==='checkbox' ? el.checked
                 : el.type==='number'   ? parseFloat(el.value)
                 : el.value;
      $('#preset-select').value = '__custom';
      $('#preset-measured').innerHTML =
        '<span class="text-amber-400">Custom configuration — not backtested as a set.</span>';
      buildForm();
    };
  });
}

function renderField(f){
  const v = CURRENT[f.k];
  const disabled = f.dep && !CURRENT[f.dep] ? 'opacity-40 pointer-events-none' : '';
  const help = f.help ? `<p class="text-[10px] text-slate-500 mt-0.5 leading-tight">${f.help}</p>` : '';
  let input;
  if (f.t === 'bool') {
    input = `<label class="flex items-center gap-2 cursor-pointer">
      <input type="checkbox" data-k="${f.k}" ${v?'checked':''} class="accent-emerald-500">
      <span class="text-xs text-slate-300">${f.label}</span></label>`;
    return `<div class="${disabled}">${input}${help}</div>`;
  }
  if (f.t === 'select') {
    input = `<select data-k="${f.k}" class="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs">
      ${f.opts.map(([k2,l])=>`<option value="${k2}" ${v===k2?'selected':''}>${l}</option>`).join('')}</select>`;
  } else {
    input = `<input type="number" data-k="${f.k}" value="${v}" step="${f.step||1}"
      ${f.min!=null?`min="${f.min}"`:''} ${f.max!=null?`max="${f.max}"`:''}
      class="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs">`;
  }
  return `<div class="${disabled}">
    <label class="block text-[11px] text-slate-400 mb-0.5">${f.label}</label>${input}${help}</div>`;
}

async function initProviders(){
  const r = await fetch('/api/providers').then(r=>r.json()).catch(()=>null);
  if(!r) return;
  PROVIDERS = r.providers; PROVIDER = r.active;
  const sel = $('#provider-select');
  sel.innerHTML = Object.entries(PROVIDERS).map(([k,v])=>
    `<option value="${k}" ${k===PROVIDER?'selected':''} ${v.configured?'':'disabled'}>
       ${v.label}${v.configured?'':' \u2014 not configured'}</option>`).join('');
  sel.onchange = e => { PROVIDER = e.target.value; showProviderNote(); };
  showProviderNote();
}

function showProviderNote(){
  const v = PROVIDERS[PROVIDER]; if(!v) return;
  const warn = !v.bulk_chain;
  $('#provider-note').innerHTML = warn
    ? `<span class="text-amber-400"><i class="fas fa-triangle-exclamation mr-1"></i>${v.notes}
       Full-universe scans are blocked for this source \u2014 it needs a watchlist.</span>`
    : v.notes;
  if(warn) checkIbkr();
}

async function checkIbkr(){
  const s = await fetch('/api/ibkr/status').then(r=>r.json()).catch(()=>null);
  if(!s || s.authenticated) return;
  $('#provider-note').innerHTML +=
    `<span class="block mt-1 text-red-400"><i class="fas fa-plug-circle-xmark mr-1"></i>
     ${s.reachable?'Gateway reachable but not authenticated.':'Gateway unreachable.'}
     ${s.remedy||''}</span>`;
}

async function loadStatus(){
  const h = await fetch('/api/health').then(r=>r.json()).catch(()=>({}));
  const pill = (ok,label,warn) =>
    `<span class="px-2 py-1 rounded ${ok?(warn?'bg-amber-900/50 text-amber-300':'bg-emerald-900/50 text-emerald-300'):'bg-slate-800 text-slate-500'}">
      <i class="fas fa-circle text-[6px] mr-1 align-middle"></i>${label}</span>`;
  $('#status-pills').innerHTML =
    pill(h.polygon_configured,'Polygon') +
    pill(h.alpaca_configured,'Alpaca') +
    pill(h.ibkr_configured,'IBKR') +
    pill(true, h.alpaca_armed||h.ibkr_armed ? 'ARMED' : 'Dry run', h.alpaca_armed||h.ibkr_armed);
}

async function runScan(){
  const btn = $('#scan-btn');
  btn.disabled = true;
  btn.innerHTML = '<i class="fas fa-spinner fa-spin mr-2"></i>Scanning…';
  $('#results').innerHTML = '<div class="text-slate-500">Fetching chains…</div>';
  try {
    const res = await fetch('/api/scan', {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({criteria: CURRENT, provider: PROVIDER})
    });
    if(!res.ok){ throw new Error((await res.json()).detail || res.statusText); }
    LAST = await res.json();
    render(LAST);
  } catch(e){
    $('#results').innerHTML = `<div class="text-red-400 text-sm">
      <i class="fas fa-triangle-exclamation mr-2"></i>${e.message}</div>`;
    $('#stats').innerHTML=''; 
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<i class="fas fa-magnifying-glass-chart mr-2"></i>Run Screener';
  }
}

function render(d){
  const s = d.stats || {};
  const card = (label,val,cls='') =>
    `<div class="bg-slate-900 border border-slate-800 rounded p-3">
      <div class="text-[10px] uppercase text-slate-500 tracking-wide">${label}</div>
      <div class="text-lg font-semibold ${cls}">${val}</div></div>`;
  const riskCls = s.total_risk_pct_of_equity > 60 ? 'text-red-400'
                : s.total_risk_pct_of_equity > 35 ? 'text-amber-400' : 'text-emerald-400';
  $('#stats').innerHTML =
    card('Universe', s.universe) +
    card('Passed filters', s.eligible_after_filters) +
    card('Selected', s.selected, 'text-emerald-400') +
    card('Capital at risk', money(s.total_risk)+` (${s.total_risk_pct_of_equity}%)`, riskCls) +
    card('Max profit', money(s.max_profit));

  $('#warnings').innerHTML = (d.warnings||[]).map(w =>
    `<div class="bg-amber-950/50 border border-amber-800 text-amber-300 rounded p-3 text-xs mb-2">
      <i class="fas fa-triangle-exclamation mr-2"></i>${w}</div>`).join('');

  const rows = $('#show-all').checked ? d.all_candidates : d.selected;
  $('#result-count').textContent = `${rows.length} shown`;

  if(!rows.length){
    $('#results').innerHTML = '<div class="text-slate-500 text-sm">No positions met the criteria.</div>';
  } else {
    $('#results').innerHTML = `
    <div class="overflow-x-auto"><table class="w-full text-xs">
      <thead class="text-slate-500 border-b border-slate-800">
        <tr class="text-left">
          <th class="pb-2 pr-3">#</th><th class="pb-2 pr-3">Symbol</th><th class="pb-2 pr-3">Sector</th>
          <th class="pb-2 pr-3">Legs</th><th class="pb-2 pr-3">DTE</th>
          <th class="pb-2 pr-3 text-right">Δ</th><th class="pb-2 pr-3 text-right">Credit</th>
          <th class="pb-2 pr-3 text-right">R:R</th><th class="pb-2 pr-3 text-right">Score</th>
          <th class="pb-2 pr-3 text-right">Qty</th><th class="pb-2 pr-3 text-right">Risk</th>
          <th class="pb-2 pr-3 text-right">Max P</th><th class="pb-2"></th>
        </tr></thead>
      <tbody>${rows.map((c,i)=>row(c,i)).join('')}</tbody>
    </table></div>`;
    document.querySelectorAll('[data-order]').forEach(b=>{
      b.onclick = () => openOrder(rows[parseInt(b.dataset.order)]);
    });
    document.querySelectorAll('[data-why]').forEach(b=>{
      b.onclick = () => {
        const el = document.getElementById('why-'+b.dataset.why);
        el.classList.toggle('hidden');
      };
    });
  }

  const rej = Object.entries(d.rejections||{});
  if(rej.length){
    $('#rejections').classList.remove('hidden');
    $('#rejection-list').innerHTML = rej.map(([k,v])=>
      `<span class="bg-slate-800 rounded px-2 py-1 text-slate-400">${k.replace(/_/g,' ')}: <b class="text-slate-200">${v}</b></span>`).join('');
  } else $('#rejections').classList.add('hidden');
}

function row(c,i){
  const legs = c.legs.map(l=>`${l.action==='SELL'?'−':'+'}${l.strike}${l.right[0]}`).join(' / ');
  return `
  <tr class="border-b border-slate-800/60 hover:bg-slate-800/30">
    <td class="py-2 pr-3 text-slate-600">${i+1}</td>
    <td class="py-2 pr-3 font-semibold text-white">${c.symbol}</td>
    <td class="py-2 pr-3 text-slate-400">${c.sector}</td>
    <td class="py-2 pr-3 font-mono text-slate-300">${legs}</td>
    <td class="py-2 pr-3">${c.dte}</td>
    <td class="py-2 pr-3 text-right">${fmt(c.short_delta,2)}</td>
    <td class="py-2 pr-3 text-right text-emerald-400">${fmt(c.credit,2)}</td>
    <td class="py-2 pr-3 text-right">${fmt(c.risk_reward,2)}</td>
    <td class="py-2 pr-3 text-right text-sky-400">${fmt(c.rank_score*100,1)}%</td>
    <td class="py-2 pr-3 text-right">${c.contracts||'—'}</td>
    <td class="py-2 pr-3 text-right text-amber-400">${money(c.total_risk)}</td>
    <td class="py-2 pr-3 text-right text-emerald-400">${money(c.max_profit)}</td>
    <td class="py-2 text-right whitespace-nowrap">
      <button data-why="${i}" class="text-slate-500 hover:text-sky-400 mr-2" title="Why this rank?">
        <i class="fas fa-circle-info"></i></button>
      <button data-order="${i}" class="bg-slate-800 hover:bg-emerald-700 rounded px-2 py-1 text-[11px]">Order</button>
    </td>
  </tr>
  <tr id="why-${i}" class="hidden"><td colspan="13" class="px-3 pb-2 text-[11px] text-slate-400 bg-slate-900/50">
    <i class="fas fa-calculator mr-1"></i>${c.rank_explanation}
    &nbsp;·&nbsp; breakeven ${fmt(c.breakeven,2)} &nbsp;·&nbsp; max loss/contract ${money(c.max_loss_per_contract)}
  </td></tr>`;
}

let PENDING = null;
function openOrder(c){
  PENDING = c;
  $('#order-detail').innerHTML = `
    <div><b class="text-white">${c.symbol}</b> ${c.structure.replace('_',' ')} · ${c.expiration}</div>
    ${c.legs.map(l=>`<div class="font-mono text-slate-400">${l.action} ${l.right} ${l.strike}</div>`).join('')}
    <div class="pt-2">Qty <b>${c.contracts}</b> · net credit <b class="text-emerald-400">${fmt(c.credit,2)}</b></div>
    <div>Risk <b class="text-amber-400">${money(c.total_risk)}</b> · max profit <b class="text-emerald-400">${money(c.max_profit)}</b></div>`;
  $('#order-result').innerHTML = '';
  $('#order-modal').classList.remove('hidden');
  $('#order-modal').classList.add('flex');
  $('#order-send').onclick = sendOrder;
}

async function sendOrder(){
  const btn = $('#order-send'); btn.disabled = true; btn.textContent='Sending…';
  try{
    const res = await fetch('/api/order',{method:'POST',headers:{'Content-Type':'application/json'},
      body: JSON.stringify({
        broker: $('#order-broker').value, symbol: PENDING.symbol,
        structure: PENDING.structure, quantity: PENDING.contracts,
        limit_price: PENDING.credit,
        legs: PENDING.legs.map(l=>({action:l.action,right:l.right,strike:l.strike,expiration:l.expiration}))
      })}).then(r=>r.json());
    const cls = res.state==='ACCEPTED' ? 'text-emerald-400'
              : res.state==='DRY_RUN' ? 'text-sky-400'
              : res.state==='SENT_UNKNOWN' ? 'text-amber-400' : 'text-red-400';
    $('#order-result').innerHTML =
      `<div class="${cls}"><b>${res.state}</b> — ${res.message}</div>
       <div class="text-slate-600 mt-1 font-mono text-[10px]">${res.client_order_id}</div>`;
  }catch(e){
    $('#order-result').innerHTML = `<div class="text-red-400">${e.message}</div>`;
  }finally{ btn.disabled=false; btn.textContent='Send'; }
}

init();
