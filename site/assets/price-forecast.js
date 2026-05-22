/*!
 * <price-forecast> — drop-in weather-driven electricity price forecast module.
 *
 * Shows the 10-minute price curve produced by the ECO-VPP price-forecast
 * service (weather + METOC Lagrangian nowcast), with the weather inputs that
 * drive it. Zero dependencies, no build step.
 *
 * Usage:
 *   <script src="assets/price-forecast.js"></script>
 *   <price-forecast
 *      endpoint="/api/v1/price/forecast"   <!-- omit for in-browser mock -->
 *      hours="6">
 *   </price-forecast>
 *
 * Attributes
 *   endpoint   GET URL returning the service payload
 *              { provider, resolution_min, points:[{timestamp, price_eur_mwh,
 *                price_eur_kwh, residual_load_kw, renewable_kw, demand_kw}] }.
 *              When absent (or fetch fails) a browser-side model generates the
 *              same shape from a mock weather series, so the module always works.
 *   hours      forecast horizon to display. Default 6.
 *   refresh    auto-refresh seconds. Default 300 (0 = off).
 *
 * Events: price (detail = nearest point), price:error (detail = {message}).
 * Methods: .points(), .refresh().
 */
(function () {
  const STEP_MIN = 10;

  // Mirror of services/price-forecast/model.py merit-order coefficients so the
  // browser fallback matches the backend shape.
  const M = {
    PV_KW: 5000, WIND_KW: 2000, PV_EFF: 0.85,
    BASE_KW: 3000, PEAK_KW: 9000, HEAT_KW_DEG: 180, COOL_KW_DEG: 140,
    P_ZERO: 45, SLOPE_PER_MW: 22, FLOOR: 0, CAP: 400,
  };

  function pvKw(gti) { return M.PV_KW * (gti / 1000) * M.PV_EFF; }
  function windKw(ms) {
    if (ms < 3 || ms >= 25) return 0;
    if (ms >= 12) return M.WIND_KW;
    return M.WIND_KW * Math.pow((ms - 3) / 9, 3);
  }
  function demandKw(tempC, date) {
    const h = date.getUTCHours() + date.getUTCMinutes() / 60;
    let shape = 0.5 * (Math.sin((h - 8) / 24 * 2 * Math.PI) + Math.sin((h - 19) / 12 * 2 * Math.PI));
    shape = Math.max(0, Math.min(1, 0.5 + 0.5 * shape));
    let load = M.BASE_KW + (M.PEAK_KW - M.BASE_KW) * shape;
    if (tempC < 15) load += (15 - tempC) * M.HEAT_KW_DEG;
    else if (tempC > 24) load += (tempC - 24) * M.COOL_KW_DEG;
    return load;
  }
  function meritPrice(residualKw) {
    const mw = residualKw / 1000;
    return Math.max(M.FLOOR, Math.min(M.CAP, M.P_ZERO + M.SLOPE_PER_MW * mw));
  }

  // Mock weather: diurnal irradiance bell + gentle wind + temperature wave.
  function mockSeries(hours) {
    const pts = [];
    const now = Date.now();
    const steps = Math.round((hours * 60) / STEP_MIN);
    for (let i = 0; i <= steps; i++) {
      const t = new Date(now + i * STEP_MIN * 60000);
      const hod = t.getUTCHours() + t.getUTCMinutes() / 60;
      // irradiance: zero at night, bell peaking ~13:00 UTC
      const solar = Math.max(0, Math.sin((hod - 6) / 12 * Math.PI));
      const gti = 950 * solar * (0.8 + 0.2 * Math.random());
      const wind = 4 + 4 * Math.sin(hod / 24 * 2 * Math.PI + 1) + Math.random();
      const temp = 12 + 9 * Math.sin((hod - 15) / 24 * 2 * Math.PI);
      const renewable = pvKw(gti) + windKw(wind);
      const demand = demandKw(temp, t);
      const residual = demand - renewable;
      pts.push({
        timestamp: t.toISOString(),
        gti: Math.round(gti), wind: +wind.toFixed(1), temp: +temp.toFixed(1),
        price_eur_mwh: +meritPrice(residual).toFixed(2),
        price_eur_kwh: +(meritPrice(residual) / 1000).toFixed(5),
        renewable_kw: Math.round(renewable), demand_kw: Math.round(demand),
        residual_load_kw: Math.round(residual),
      });
    }
    return { provider: 'browser-mock', resolution_min: STEP_MIN, points: pts };
  }

  const TPL = document.createElement('template');
  TPL.innerHTML = `
    <style>
      :host{display:block;font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#e6edf3}
      *{box-sizing:border-box}
      .panel{background:#161b22;border:1px solid #283041;border-radius:14px;padding:1.1rem 1.2rem}
      .top{display:flex;flex-wrap:wrap;gap:.8rem;align-items:baseline;justify-content:space-between;margin-bottom:.4rem}
      .now{font-size:1.9rem;font-weight:800;letter-spacing:-.02em}
      .now small{font-size:1rem;color:#9aa4b2;font-weight:500}
      .meta{color:#9aa4b2;font-size:.85rem}
      .prov{font-size:.72rem;padding:.1rem .55rem;border-radius:999px;border:1px solid #283041;color:#9aa4b2}
      .prov.live{color:#34d399;border-color:#1f6e4a;background:rgba(52,211,153,.08)}
      .chart{position:relative;height:140px;display:flex;align-items:flex-end;gap:2px;margin:.8rem 0 .3rem}
      .bar{flex:1;min-height:3px;border-radius:3px 3px 0 0;background:linear-gradient(180deg,#7c9cff,#3b4a8a);opacity:.9;position:relative}
      .bar:hover{opacity:1}
      .bar.cheap{background:linear-gradient(180deg,#34d399,#1f6e4a)}
      .bar.dear{background:linear-gradient(180deg,#f59e0b,#b45309)}
      .axis{display:flex;justify-content:space-between;color:#6b7280;font-size:.72rem}
      .legend{display:flex;gap:1rem;flex-wrap:wrap;margin-top:.7rem;color:#9aa4b2;font-size:.82rem}
      .legend b{color:#e6edf3;font-variant-numeric:tabular-nums}
      .spark{display:flex;align-items:flex-end;gap:1px;height:26px;margin-top:.2rem}
      .spark i{flex:1;background:#475569;border-radius:1px;min-height:2px;display:block}
      .spark.sun i{background:#f59e0b}.spark.wind i{background:#60a5fa}.spark.temp i{background:#f87171}
      .wx{display:grid;grid-template-columns:repeat(3,1fr);gap:.8rem;margin-top:.8rem}
      .wx .c{background:#0e1117;border:1px solid #283041;border-radius:10px;padding:.6rem .7rem}
      .wx .c h4{margin:0;font-size:.78rem;color:#9aa4b2;font-weight:600}
      .err{color:#fbbf24;font-size:.82rem;margin-top:.4rem}
    </style>
    <div class="panel">
      <div class="top">
        <div>
          <div class="now" id="now">€–<small>/MWh</small></div>
          <div class="meta" id="meta">loading forecast…</div>
        </div>
        <span class="prov" id="prov">…</span>
      </div>
      <div class="chart" id="chart"></div>
      <div class="axis"><span id="ax0">now</span><span id="ax1"></span></div>
      <div class="wx">
        <div class="c"><h4>☀️ Irradiance</h4><div class="spark sun" id="sp-sun"></div></div>
        <div class="c"><h4>💨 Wind</h4><div class="spark wind" id="sp-wind"></div></div>
        <div class="c"><h4>🌡️ Temp</h4><div class="spark temp" id="sp-temp"></div></div>
      </div>
      <div class="legend">
        <span>Next 10-min: <b id="lg-next">–</b></span>
        <span>Min: <b id="lg-min">–</b></span>
        <span>Max: <b id="lg-max">–</b></span>
        <span>Resolution: <b id="lg-res">10 min</b></span>
      </div>
      <div class="err" id="err" hidden></div>
    </div>`;

  class PriceForecast extends HTMLElement {
    constructor() { super(); this.attachShadow({ mode: 'open' }).appendChild(TPL.content.cloneNode(true)); }

    connectedCallback() {
      this.$ = (id) => this.shadowRoot.getElementById(id);
      this._hours = parseFloat(this.getAttribute('hours') || '6');
      this.refresh();
      const every = parseInt(this.getAttribute('refresh') ?? '300', 10);
      if (every > 0) this._timer = setInterval(() => this.refresh(), every * 1000);
    }
    disconnectedCallback() { if (this._timer) clearInterval(this._timer); }

    points() { return this._data ? this._data.points : []; }

    async refresh() {
      const endpoint = this.getAttribute('endpoint');
      let data = null;
      if (endpoint) {
        try {
          const r = await fetch(endpoint, { headers: { Accept: 'application/json' } });
          if (!r.ok) throw new Error('HTTP ' + r.status);
          data = await r.json();
          if (!data.points || !data.points.length) throw new Error('empty forecast');
          this.$('err').hidden = true;
        } catch (e) {
          this.$('err').hidden = false;
          this.$('err').textContent = 'Live endpoint unavailable (' + e.message + ') — showing modelled fallback.';
          this.dispatchEvent(new CustomEvent('price:error', { bubbles: true, composed: true, detail: { message: String(e) } }));
        }
      }
      if (!data) data = mockSeries(this._hours);
      this._data = data;
      this._render();
    }

    _render() {
      const d = this._data, pts = d.points;
      if (!pts.length) return;
      const prices = pts.map(p => p.price_eur_mwh);
      const lo = Math.min(...prices), hi = Math.max(...prices);
      const now = Date.now();
      const nearest = pts.reduce((a, b) =>
        Math.abs(new Date(b.timestamp) - now) < Math.abs(new Date(a.timestamp) - now) ? b : a);
      const nextPt = pts.find(p => new Date(p.timestamp) > now) || nearest;

      this.$('now').innerHTML = `€${nearest.price_eur_mwh.toFixed(0)}<small>/MWh · €${(nearest.price_eur_mwh/1000).toFixed(3)}/kWh</small>`;
      this.$('meta').textContent = `${pts.length} steps · ${(this._hours)}h horizon`;
      const prov = this.$('prov');
      prov.textContent = d.provider;
      prov.className = 'prov' + (d.provider && d.provider !== 'browser-mock' && d.provider !== 'interpolation-fallback' ? ' live' : '');

      // Price chart, coloured by cheap/dear tertiles.
      const t1 = lo + (hi - lo) / 3, t2 = lo + 2 * (hi - lo) / 3;
      this.$('chart').innerHTML = pts.map(p => {
        const h = hi > lo ? 6 + ((p.price_eur_mwh - lo) / (hi - lo)) * 94 : 50;
        const cls = p.price_eur_mwh <= t1 ? 'cheap' : p.price_eur_mwh >= t2 ? 'dear' : '';
        const ts = new Date(p.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        return `<div class="bar ${cls}" style="height:${h}%" title="${ts} · €${p.price_eur_mwh}/MWh"></div>`;
      }).join('');
      this.$('ax1').textContent = new Date(pts[pts.length - 1].timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

      // Weather sparklines (use service fields if present, else mock fields).
      const spark = (id, key, fallbackKey) => {
        const vals = pts.map(p => p[key] ?? p[fallbackKey] ?? 0);
        const mx = Math.max(...vals, 1);
        this.$(id).innerHTML = vals.map(v => `<i style="height:${Math.max(8, (v / mx) * 100)}%"></i>`).join('');
      };
      // service payload exposes renewable_kw/demand_kw not raw weather; mock exposes gti/wind/temp.
      spark('sp-sun', 'gti', 'renewable_kw');
      spark('sp-wind', 'wind', 'renewable_kw');
      spark('sp-temp', 'temp', 'demand_kw');

      this.$('lg-next').textContent = `€${nextPt.price_eur_mwh.toFixed(0)}/MWh`;
      this.$('lg-min').textContent = `€${lo.toFixed(0)}`;
      this.$('lg-max').textContent = `€${hi.toFixed(0)}`;
      this.$('lg-res').textContent = `${d.resolution_min || STEP_MIN} min`;

      this.dispatchEvent(new CustomEvent('price', { bubbles: true, composed: true, detail: nearest }));
    }
  }

  if (!customElements.get('price-forecast')) customElements.define('price-forecast', PriceForecast);
})();
