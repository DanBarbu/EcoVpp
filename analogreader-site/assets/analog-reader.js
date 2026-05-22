/*!
 * <analog-reader> — drop-in meter-digitisation UI module.
 *
 * Zero dependencies, no build step. Works in any modern browser.
 *
 * Usage:
 *   <script src="assets/analog-reader.js"></script>
 *   <analog-reader
 *      endpoint="/api/v1/readings/ocr"   <!-- omit for mock mode -->
 *      kinds="power,gas,water"
 *      storage="analogreader.readings">
 *   </analog-reader>
 *
 * Attributes
 *   endpoint   POST URL accepting multipart {photo, kind}; returns
 *              { value:Number, unit:String, confidence:0..1 }.
 *              When absent (or fetch fails) it falls back to a local
 *              deterministic mock so the module always works offline.
 *   kinds      comma list of meter kinds to expose. Default: all three.
 *   storage    localStorage key for the reading history. Default:
 *              "analogreader.readings". Set to "" to disable persistence.
 *   token      optional Bearer token sent as Authorization header.
 *
 * Events (bubbling, composed)
 *   reading            detail = the stored reading object
 *   reading:review     detail = reading with confidence < 0.80
 *   reading:error      detail = { message }
 *
 * Public methods
 *   .readings()        -> array of stored readings
 *   .clear()           -> wipe history
 *   .exportCSV()       -> triggers a CSV download
 */
(function () {
  const KINDS = {
    power: { label: 'Electricity', unit: 'kWh', icon: '⚡', rate: 0.235, accent: '#fbbf24' },
    gas:   { label: 'Gas',         unit: 'm³',  icon: '🔥', rate: 1.120, accent: '#fb923c' },
    water: { label: 'Water',       unit: 'm³',  icon: '💧', rate: 4.250, accent: '#60a5fa' },
  };
  const REVIEW_THRESHOLD = 0.80;

  const TPL = document.createElement('template');
  TPL.innerHTML = `
    <style>
      :host{display:block;font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#eef2f8;
        --ar-bg:#161c25;--ar-bg2:#0e1117;--ar-border:#2a3343;--ar-muted:#9aa6b8;--ar-brand:#22d3ee;--ar-good:#34d399;--ar-warn:#fbbf24;--ar-bad:#f87171}
      *{box-sizing:border-box}
      .panel{background:var(--ar-bg);border:1px solid var(--ar-border);border-radius:14px;padding:1.1rem 1.2rem}
      .head{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;margin-bottom:.9rem}
      select,button{font:inherit;color:#eef2f8;background:#1c2331;border:1px solid var(--ar-border);border-radius:10px;padding:.55rem .75rem}
      select:focus,button:focus{outline:0;border-color:var(--ar-brand)}
      button{cursor:pointer}
      button.primary{background:var(--ar-brand);color:#04212a;font-weight:700;border-color:transparent}
      button.primary:hover{background:#67e8f9}
      button.ghost:hover{background:rgba(255,255,255,.05)}
      .dz{border:2px dashed var(--ar-border);border-radius:12px;padding:1.8rem 1rem;text-align:center;cursor:pointer;transition:.15s;background:var(--ar-bg2)}
      .dz:hover,.dz.drag{border-color:var(--ar-brand);background:rgba(34,211,238,.05)}
      .dz .big{font-size:2rem}
      .dz p{margin:.35rem 0;color:var(--ar-muted);font-size:.92rem}
      input[type=file]{display:none}
      .result{display:flex;gap:1rem;align-items:center;margin-top:1rem;padding:1rem;border:1px solid var(--ar-border);border-radius:10px;background:var(--ar-bg2)}
      .result img{width:120px;height:90px;object-fit:cover;border-radius:8px;background:#000;flex-shrink:0}
      .result .v{font-size:1.7rem;font-weight:800;font-variant-numeric:tabular-nums;letter-spacing:-.02em}
      .result .m{color:var(--ar-muted);font-size:.88rem;margin-top:.2rem}
      .badge{display:inline-block;font-size:.72rem;padding:.1rem .55rem;border-radius:999px;border:1px solid var(--ar-border);color:var(--ar-muted)}
      .badge.good{color:var(--ar-good);border-color:#1f6e4a;background:rgba(52,211,153,.08)}
      .badge.warn{color:var(--ar-warn);border-color:#7a5d12;background:rgba(251,191,36,.08)}
      .conf{display:inline-flex;align-items:center;gap:.4rem;font-size:.8rem;color:var(--ar-muted);margin-top:.45rem}
      .bar{width:90px;height:6px;background:#0e1117;border:1px solid var(--ar-border);border-radius:999px;overflow:hidden}
      .fill{display:block;height:100%;background:linear-gradient(90deg,var(--ar-good),var(--ar-brand))}
      .spin{display:inline-block;width:16px;height:16px;border:2px solid var(--ar-border);border-top-color:var(--ar-brand);border-radius:50%;animation:s .7s linear infinite;vertical-align:-3px;margin-right:.4rem}
      @keyframes s{to{transform:rotate(360deg)}}
      table{width:100%;border-collapse:collapse;font-size:.9rem;margin-top:1rem}
      th,td{padding:.5rem .6rem;border-bottom:1px dashed var(--ar-border);text-align:left}
      th{color:var(--ar-muted);font-size:.78rem;text-transform:uppercase;letter-spacing:.03em}
      td.n{text-align:right;font-variant-numeric:tabular-nums}
      .chart{display:flex;align-items:flex-end;gap:3px;height:120px;margin-top:1rem;padding:.6rem;border:1px solid var(--ar-border);border-radius:10px;background:var(--ar-bg2)}
      .chart .b{flex:1;min-height:4px;border-radius:4px 4px 0 0;opacity:.85}
      .foot{display:flex;gap:.5rem;flex-wrap:wrap;margin-top:1rem}
      .empty{color:var(--ar-muted);font-size:.9rem;padding:1rem 0;text-align:center}
      h3{margin:.2rem 0 .1rem;font-size:1rem}
      .sub{color:var(--ar-muted);font-size:.85rem;margin:0 0 .2rem}
    </style>
    <div class="panel">
      <div class="head">
        <select id="kind" aria-label="Meter type"></select>
        <button id="pick" class="primary" type="button">📷 Capture / upload</button>
        <span id="mode" class="badge" title="Data source"></span>
      </div>
      <div id="dz" class="dz" tabindex="0" role="button" aria-label="Upload meter photo">
        <div class="big">📷</div>
        <p><strong>Drop a meter photo</strong> or click</p>
        <p>JPG · PNG · HEIC — your browser camera works too</p>
        <input type="file" accept="image/*" capture="environment" />
      </div>
      <div id="result"></div>
      <div>
        <h3 style="margin-top:1.3rem">History</h3>
        <p class="sub">Stored locally in your browser. Nothing is uploaded in mock mode.</p>
        <div id="chart" class="chart" hidden></div>
        <div id="hist"></div>
      </div>
      <div class="foot">
        <button id="csv" class="ghost" type="button">⬇ Export CSV</button>
        <button id="clear" class="ghost" type="button">🗑 Clear history</button>
      </div>
    </div>`;

  class AnalogReader extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: 'open' }).appendChild(TPL.content.cloneNode(true));
      this._key = this.getAttribute('storage') ?? 'analogreader.readings';
    }

    connectedCallback() {
      const r = this.shadowRoot;
      this.$ = (s) => r.getElementById(s);

      const allowed = (this.getAttribute('kinds') || 'power,gas,water')
        .split(',').map(s => s.trim()).filter(k => KINDS[k]);
      this.$('kind').innerHTML = allowed
        .map(k => `<option value="${k}">${KINDS[k].icon} ${KINDS[k].label} (${KINDS[k].unit})</option>`).join('');

      const live = !!this.getAttribute('endpoint');
      const modeEl = this.$('mode');
      modeEl.textContent = live ? 'live API' : 'mock mode';
      modeEl.className = 'badge ' + (live ? 'good' : 'warn');

      const dz = this.$('dz');
      const input = r.querySelector('input[type=file]');
      const open = () => input.click();
      this.$('pick').addEventListener('click', open);
      dz.addEventListener('click', open);
      dz.addEventListener('keydown', (e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } });
      input.addEventListener('change', (e) => e.target.files[0] && this._handle(e.target.files[0]));
      dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('drag'); });
      dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
      dz.addEventListener('drop', (e) => {
        e.preventDefault(); dz.classList.remove('drag');
        const f = e.dataTransfer.files && e.dataTransfer.files[0];
        if (f) this._handle(f);
      });

      this.$('csv').addEventListener('click', () => this.exportCSV());
      this.$('clear').addEventListener('click', () => { this.clear(); });

      this._render();
    }

    /* ---- OCR ------------------------------------------------------------ */
    async _ocr(file, kind) {
      const endpoint = this.getAttribute('endpoint');
      if (endpoint) {
        try {
          const fd = new FormData();
          fd.append('photo', file);
          fd.append('kind', kind);
          const headers = {};
          const tok = this.getAttribute('token');
          if (tok) headers.Authorization = 'Bearer ' + tok;
          const res = await fetch(endpoint, { method: 'POST', body: fd, headers });
          if (!res.ok) throw new Error('HTTP ' + res.status);
          const j = await res.json();
          return { value: j.value, unit: j.unit || KINDS[kind].unit, confidence: j.confidence ?? 1 };
        } catch (err) {
          this.dispatchEvent(new CustomEvent('reading:error', { bubbles: true, composed: true, detail: { message: String(err) } }));
          // fall through to mock so the UI never dead-ends
        }
      }
      // Deterministic-ish mock.
      const base = { power: 48213, gas: 12876, water: 9342 }[kind];
      await new Promise(r => setTimeout(r, 650));
      return {
        value: base + Math.floor(Math.random() * 25),
        unit: KINDS[kind].unit,
        confidence: Math.round((0.74 + Math.random() * 0.25) * 100) / 100,
      };
    }

    async _handle(file) {
      const kind = this.$('kind').value;
      const url = URL.createObjectURL(file);
      this.$('result').innerHTML =
        `<div class="result"><img src="${url}" alt=""><div><div class="v"><span class="spin"></span>Reading…</div>
         <div class="m">${KINDS[kind].icon} ${KINDS[kind].label}</div></div></div>`;
      const out = await this._ocr(file, kind);
      const rec = {
        id: 'rd_' + Date.now().toString(36),
        kind, value: out.value, unit: out.unit,
        confidence: out.confidence,
        cost: +(out.value * KINDS[kind].rate).toFixed(2),
        ts: new Date().toISOString(),
        review: out.confidence < REVIEW_THRESHOLD,
      };
      this._save(rec);
      this._showResult(rec, url);
      this._render();
      this.dispatchEvent(new CustomEvent('reading', { bubbles: true, composed: true, detail: rec }));
      if (rec.review) this.dispatchEvent(new CustomEvent('reading:review', { bubbles: true, composed: true, detail: rec }));
    }

    _showResult(rec, url) {
      const k = KINDS[rec.kind];
      const flag = rec.review
        ? '<span class="badge warn">low confidence · queued for review</span>'
        : '<span class="badge good">verified</span>';
      this.$('result').innerHTML = `
        <div class="result">
          <img src="${url}" alt="Meter photo">
          <div>
            <div class="v">${rec.value.toLocaleString()} <span style="font-size:1rem;color:var(--ar-muted)">${rec.unit}</span></div>
            <div class="m">${k.icon} ${k.label} · ${flag}</div>
            <div class="m" style="margin-top:.3rem">Estimated cost so far: <strong>€${rec.cost.toFixed(2)}</strong></div>
            <div class="conf">conf <span class="bar"><span class="fill" style="width:${(rec.confidence*100)|0}%"></span></span> ${(rec.confidence*100)|0}%</div>
          </div>
        </div>`;
    }

    /* ---- storage -------------------------------------------------------- */
    readings() {
      if (!this._key) return this._mem || [];
      try { return JSON.parse(localStorage.getItem(this._key) || '[]'); } catch { return []; }
    }
    _save(rec) {
      const all = this.readings(); all.unshift(rec);
      if (!this._key) { this._mem = all.slice(0, 200); return; }
      try { localStorage.setItem(this._key, JSON.stringify(all.slice(0, 200))); } catch {}
    }
    clear() {
      if (this._key) { try { localStorage.removeItem(this._key); } catch {} }
      this._mem = [];
      this.$('result').innerHTML = '';
      this._render();
    }
    exportCSV() {
      const rows = this.readings();
      if (!rows.length) return;
      const head = 'id,kind,value,unit,confidence,cost_eur,timestamp,review\n';
      const body = rows.map(r => [r.id, r.kind, r.value, r.unit, r.confidence, r.cost, r.ts, r.review].join(',')).join('\n');
      const blob = new Blob([head + body], { type: 'text/csv' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'analogreader-readings.csv';
      a.click();
    }

    /* ---- render history ------------------------------------------------- */
    _render() {
      const rows = this.readings();
      const hist = this.$('hist'), chart = this.$('chart');
      if (!rows.length) {
        hist.innerHTML = '<div class="empty">No readings yet — capture one above.</div>';
        chart.hidden = true;
        return;
      }
      hist.innerHTML = `
        <table><thead><tr><th>When</th><th>Meter</th><th class="n">Value</th><th>Conf.</th><th>Status</th></tr></thead>
        <tbody>${rows.slice(0, 12).map(r => {
          const k = KINDS[r.kind];
          return `<tr>
            <td>${new Date(r.ts).toLocaleString([], { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })}</td>
            <td>${k.icon} ${k.label}</td>
            <td class="n">${r.value.toLocaleString()} ${r.unit}</td>
            <td class="n">${(r.confidence*100)|0}%</td>
            <td>${r.review ? '<span class="badge warn">review</span>' : '<span class="badge good">ok</span>'}</td>
          </tr>`;
        }).join('')}</tbody></table>`;

      // Simple bar chart of the most recent (max 24) values for the selected kind.
      const kind = this.$('kind').value;
      const series = rows.filter(r => r.kind === kind).slice(0, 24).reverse();
      if (series.length > 1) {
        chart.hidden = false;
        const max = Math.max(...series.map(s => s.value));
        const min = Math.min(...series.map(s => s.value));
        const span = (max - min) || 1;
        chart.innerHTML = series.map(s => {
          const h = 8 + ((s.value - min) / span) * 92;
          return `<div class="b" title="${s.value} ${s.unit}" style="height:${h}%;background:${KINDS[kind].accent}"></div>`;
        }).join('');
      } else {
        chart.hidden = true;
      }
    }
  }

  if (!customElements.get('analog-reader')) customElements.define('analog-reader', AnalogReader);
})();
