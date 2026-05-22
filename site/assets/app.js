/* ECO-VPP shared site script: header, footer, mobile nav, demo dashboard. */
(function () {
  const NAV = [
    { href: '/', label: 'Home' },
    { href: '/features.html', label: 'Features' },
    { href: '/pilots.html', label: 'Pilots' },
    { href: '/about.html', label: 'About' },
    { href: '/demo.html', label: 'Live demo' },
    { href: '/contact.html', label: 'Contact' },
  ];

  // Resolve "/" links so they work both at the root (Pages, Vercel, Netlify)
  // and when opened as a flat directory of files (file://) — by always going
  // through document.baseURI.
  function resolve(href) {
    if (href === '/') return basePath() || './';
    if (href.startsWith('/')) return basePath() + href.slice(1);
    return href;
  }
  function basePath() {
    const m = location.pathname.match(/^(.*\/)([^/]*)$/);
    return m ? m[1] : '/';
  }

  function active(href) {
    const path = location.pathname.replace(/\/index\.html$/, '/');
    if (href === '/') return path === '/' || path.endsWith('/');
    return path.endsWith(href);
  }

  function mountHeader() {
    const el = document.getElementById('site-header');
    if (!el) return;
    el.innerHTML = `
      <div class="inner">
        <a class="logo" href="${resolve('/')}"><span class="dot"></span> ECO-VPP</a>
        <button class="nav-toggle" aria-label="Toggle menu">☰</button>
        <nav class="nav" id="site-nav">
          ${NAV.map(n => `<a href="${resolve(n.href)}" class="${active(n.href) ? 'active' : ''}">${n.label}</a>`).join('')}
          <a class="cta" href="https://github.com/DanBarbu/EcoVpp">GitHub</a>
        </nav>
      </div>`;
    el.querySelector('.nav-toggle').addEventListener('click', () => {
      el.querySelector('#site-nav').classList.toggle('open');
    });
  }

  function mountFooter() {
    const el = document.getElementById('site-footer');
    if (!el) return;
    el.innerHTML = `
      <div class="inner">
        <div>
          <a class="logo" href="${resolve('/')}"><span class="dot"></span> ECO-VPP</a>
          <p style="margin-top:.7rem">White-label orchestration platform for energy communities. RED II Collective Self-Consumption, GSY-e P2P market, Energy Web settlement.</p>
        </div>
        <div>
          <h4>Platform</h4>
          <a href="${resolve('/features.html')}">Features</a>
          <a href="${resolve('/demo.html')}">Live demo</a>
          <a href="${resolve('/pilots.html')}">Pilot sites</a>
        </div>
        <div>
          <h4>Project</h4>
          <a href="${resolve('/about.html')}">About</a>
          <a href="https://github.com/DanBarbu/EcoVpp">GitHub repo</a>
          <a href="https://github.com/DanBarbu/EcoVpp/blob/main/docs/architecture.md">Architecture</a>
        </div>
        <div>
          <h4>Get involved</h4>
          <a href="${resolve('/contact.html')}">Contact</a>
          <a href="https://github.com/DanBarbu/EcoVpp/issues">Report an issue</a>
          <a href="https://github.com/DanBarbu/EcoVpp/blob/main/LICENSE">License</a>
        </div>
        <div class="copy">
          © ${new Date().getFullYear()} ECO-VPP contributors. Apache-2.0. Built for the Horizon Europe Clean Energy Transition call (HORIZON-CL5-2026-02-D3-20).
        </div>
      </div>`;
  }

  /* ------------------------------------------------------------ Live demo */
  function eur(v) { return '€' + v.toFixed(3) + '/kWh'; }
  function fmtTime(d) { return d.toTimeString().slice(0, 5); }

  const ASSETS = [
    { id: 'apt-01', label: 'Apt 1 · meter', type: 'meter' },
    { id: 'apt-02', label: 'Apt 2 · meter', type: 'meter' },
    { id: 'apt-04', label: 'Apt 4 · meter', type: 'meter' },
    { id: 'roof-01', label: 'Rooftop · 12 kWp inverter', type: 'inverter' },
    { id: 'apt-07', label: 'Apt 7 · EV charger', type: 'ev' },
    { id: 'apt-03', label: 'Apt 3 · heat pump', type: 'heater' },
    { id: 'apt-09', label: 'Apt 9 · battery 5 kWh', type: 'battery' },
  ];

  function priceWave(t) {
    return Math.max(0.04, 0.125 + 0.085 * Math.sin(t / 60));
  }

  function startDemo(opts = {}) {
    const showAssets = opts.assets !== false;
    let lastPrice = priceWave(Date.now() / 1000);

    function tick() {
      const t = Date.now() / 1000;
      const p = priceWave(t);
      const signal = Math.max(0, Math.min(1, (p * 1000 - 40) / (200 - 40)));
      const limit = Math.round((1 - signal) * 100);

      set('stat-price', eur(p));
      const dEl = document.getElementById('stat-price-delta');
      if (dEl) {
        const delta = p - lastPrice;
        dEl.textContent = (delta >= 0 ? '▲ ' : '▼ ') + Math.abs(delta * 1000).toFixed(1) + ' €/MWh';
        dEl.className = 'delta ' + (delta >= 0 ? 'bad' : 'good');
      }
      set('stat-limit', limit + '%');
      lastPrice = p;

      const feed = document.getElementById('incentive-feed');
      if (feed) {
        const line = `[${fmtTime(new Date())}] price=${eur(p)} signal=${signal.toFixed(2)} → SET_LOAD_LIMIT ${limit}%\n`;
        feed.textContent = (line + feed.textContent).slice(0, 1800);
      }
    }

    function seedShares() {
      const tbody = document.getElementById('shares-body');
      if (!tbody) return;
      let totalKwh = 0;
      for (let i = 0; i < 12; i++) {
        const t = new Date(Date.now() - i * 9 * 60 * 1000);
        const a = ASSETS[i % ASSETS.length];
        const kwh = +(0.6 + Math.random() * 2.2).toFixed(2);
        const price = +(0.16 + Math.random() * 0.06).toFixed(3);
        totalKwh += kwh;
        const settled = i > 1 ? '<span class="badge green">on-chain</span>' : '<span class="badge amber">queued</span>';
        const row = document.createElement('tr');
        row.innerHTML = `<td>${fmtTime(t)}</td><td>${a.label}</td><td class="kwh">${kwh.toFixed(2)}</td><td class="eur">${(kwh * price).toFixed(2)}</td><td>${settled}</td>`;
        tbody.appendChild(row);
      }
      set('stat-shared', totalKwh.toFixed(1) + ' kWh');
      set('stat-co2', (totalKwh * 0.32).toFixed(1) + ' kg');
    }

    function seedAssets() {
      if (!showAssets) return;
      const list = document.getElementById('assets-body');
      if (!list) return;
      ASSETS.forEach(a => {
        const tr = document.createElement('tr');
        tr.innerHTML = `<td><code>did:ethr:volta:${(a.id + '0000000000').slice(0, 10)}</code></td><td>${a.label}</td><td><span class="badge">${a.type}</span></td><td class="num">${(Math.random() * 5 + 0.5).toFixed(1)}</td><td><span class="badge green">online</span></td>`;
        list.appendChild(tr);
      });
    }

    seedShares();
    seedAssets();
    tick();
    setInterval(tick, 2000);
  }

  function set(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }

  function mountContactForm() {
    const f = document.getElementById('contact-form');
    if (!f) return;
    f.addEventListener('submit', (e) => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(f).entries());
      const out = document.getElementById('contact-result');
      out.innerHTML = `<div class="callout" style="margin-top:1rem"><h3>Thanks, ${escape(data.name || 'there')}!</h3><p>This is a demo form — wire it to your CRM/Mailchimp/SendGrid by replacing <code>onSubmit</code> in <code>assets/app.js</code>. The submitted payload was logged to your console.</p></div>`;
      console.info('[ecovpp contact-form]', data);
      f.reset();
    });
  }

  function escape(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

  document.addEventListener('DOMContentLoaded', () => {
    mountHeader();
    mountFooter();
    mountContactForm();
    if (document.getElementById('demo-root')) startDemo();
  });
})();
