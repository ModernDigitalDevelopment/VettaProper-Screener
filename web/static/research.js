/* Research page — renders measured backtest data. */
'use strict';

const XTAB = {
  cols: ['0.00-0.15','0.15-0.20','0.20-0.26','0.26-0.34','0.34-0.50','0.50+'],
  rows: [
    { d: '0.20-0.26', v: [5.2, -0.5, null, null, null, null] },
    { d: '0.26-0.30', v: [3.2, 5.4, 9.0, 9.3, 13.2, null] },
    { d: '0.30-0.34', v: [1.2, 6.5, 7.7, 6.2, 18.7, null] },
    { d: '0.34-0.40', v: [1.0, 4.0, 11.4, 6.9, 5.5, 25.1] },
    { d: '0.40-0.51', v: [-4.0, 6.2, 14.0, 2.5, 11.5, 14.0] },
  ],
};

const RUNS = [
  { label:'5% · 1/sector · R:R≥0.2 · ranked',  n:240, win:77.5, exp:277, net:66526, pf:1.86, dd:19.8, peak:53, rec:true },
  { label:'5% · 2/sector · δ0.25±0.07 · ranked', n:300, win:83.7, exp:172, net:51738, pf:1.70, dd:31.0, peak:57 },
  { label:'5% · 1/sector · R:R≥0.2 · max 8 open', n:215, win:73.5, exp:253, net:54501, pf:1.58, dd:36.2, peak:39 },
  { label:'5% · 2/sector · ranked',            n:304, win:75.0, exp:244, net:74144, pf:1.60, dd:44.4, peak:58 },
  { label:'5% · 2/sector · credit/width rank', n:302, win:71.9, exp:202, net:61015, pf:1.40, dd:42.2, peak:58 },
  { label:'5% · 2/sector · R:R≥0.2 · ranked',  n:301, win:73.8, exp:250, net:75168, pf:1.60, dd:44.4, peak:58 },
  { label:'10% · 1/sector · R:R≥0.2 · max 6 open', n:174, win:73.6, exp:418, net:72800, pf:1.54, dd:41.0, peak:59 },
  { label:'10% · 1/sector · R:R≥0.2 · max 6', n:174, win:73.0, exp:417, net:72564, pf:1.47, dd:54.3, peak:59 },
  { label:'7.5% · 1/sector · R:R≥0.2 · max 8', n:215, win:73.5, exp:367, net:78842, pf:1.56, dd:57.1, peak:58 },
  { label:'10% · 2/sector · ranked',           n:304, win:75.0, exp:438, net:133115, pf:1.53, dd:94.9, peak:117, bad:true },
  { label:'10% · 2/sector · credit/width rank',n:302, win:71.9, exp:412, net:124396, pf:1.41, dd:82.5, peak:117, bad:true },
];

const MONTHLY = {
  labels: ['Mar','Apr','May','Jun','Oct','Nov','Dec'],
  values: [7292, -1000, 413, 19422, 2587, 15299, 22513],
};

function heat(v){
  if (v == null) return 'background:#0f172a;color:#334155';
  const t = Math.max(-5, Math.min(25, v));
  if (t < 0)  return `background:rgba(239,68,68,${0.15 + Math.abs(t)/20});color:#fecaca`;
  const a = 0.08 + (t/25) * 0.55;
  return `background:rgba(16,185,129,${a});color:#d1fae5`;
}

function renderXtab(){
  const el = document.getElementById('xtab');
  el.innerHTML =
    `<thead><tr>
      <th class="text-left text-slate-500 font-medium px-3 py-2">delta \\ R:R</th>
      ${XTAB.cols.map(c=>`<th class="px-3 py-2 text-slate-500 font-medium">${c}</th>`).join('')}
    </tr></thead>
    <tbody>${XTAB.rows.map(r=>`
      <tr><td class="px-3 py-2 text-slate-400 font-mono">${r.d}</td>
      ${r.v.map(v=>`<td class="px-3 py-2 text-center font-mono" style="${heat(v)}">
        ${v==null?'—':v.toFixed(1)+'%'}</td>`).join('')}</tr>`).join('')}
    </tbody>`;
}

function renderRuns(){
  const el = document.getElementById('runs-table');
  el.innerHTML =
    `<thead class="text-slate-500 border-b border-slate-800"><tr class="text-left">
      <th class="pb-2 pr-3">Configuration</th><th class="pb-2 pr-3 text-right">Trades</th>
      <th class="pb-2 pr-3 text-right">Win %</th><th class="pb-2 pr-3 text-right">Expectancy</th>
      <th class="pb-2 pr-3 text-right">Net</th><th class="pb-2 pr-3 text-right">PF</th>
      <th class="pb-2 pr-3 text-right">Max DD</th><th class="pb-2 text-right">Peak risk</th>
    </tr></thead><tbody>${RUNS.map(r=>`
      <tr class="border-b border-slate-800/60 ${r.bad?'opacity-60':''} ${r.rec?'bg-emerald-950/30':''}">
        <td class="py-2 pr-3 ${r.rec?'text-emerald-300 font-medium':'text-slate-300'}">
          ${r.rec?'<i class="fas fa-star text-emerald-400 mr-1.5"></i>':''}${r.label}</td>
        <td class="py-2 pr-3 text-right text-slate-400">${r.n}</td>
        <td class="py-2 pr-3 text-right">${r.win}%</td>
        <td class="py-2 pr-3 text-right">$${r.exp}</td>
        <td class="py-2 pr-3 text-right text-emerald-400">$${r.net.toLocaleString()}</td>
        <td class="py-2 pr-3 text-right">${r.pf}</td>
        <td class="py-2 pr-3 text-right ${r.dd>50?'text-red-400':r.dd>30?'text-amber-400':'text-slate-300'}">${r.dd}%</td>
        <td class="py-2 text-right ${r.peak>100?'text-red-400 font-bold':r.peak>70?'text-amber-400':'text-slate-300'}">${r.peak}%</td>
      </tr>`).join('')}</tbody>`;
}

function renderCharts(){
  const grid = { color:'#1e293b' }, tick = { color:'#94a3b8', font:{size:10} };

  new Chart(document.getElementById('rank-chart'), {
    type:'bar',
    data:{ labels:['Credit/width rank','Fitted δ×R:R rank'],
      datasets:[
        { label:'Net P&L ($)', data:[61015,74144], backgroundColor:['#475569','#10b981'], yAxisID:'y' },
      ]},
    options:{ responsive:true, plugins:{legend:{display:false}},
      scales:{ y:{ grid, ticks:{...tick, callback:v=>'$'+(v/1000)+'k'} }, x:{ grid:{display:false}, ticks:tick } } }
  });

  new Chart(document.getElementById('monthly-chart'), {
    type:'bar',
    data:{ labels:MONTHLY.labels, datasets:[{
      data:MONTHLY.values,
      backgroundColor:MONTHLY.values.map(v=>v<0?'#ef4444':v>10000?'#10b981':'#0ea5e9'),
    }]},
    options:{ responsive:true, plugins:{legend:{display:false},
      tooltip:{callbacks:{label:c=>'$'+c.raw.toLocaleString()}}},
      scales:{ y:{ grid, ticks:{...tick, callback:v=>'$'+(v/1000)+'k'} }, x:{ grid:{display:false}, ticks:tick } } }
  });
}

renderXtab(); renderRuns(); renderCharts();
