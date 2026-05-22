/* analogreader.online — shared header/footer + demo interactivity */
(function () {
  const NAV = [
    { href: '/', label: 'Home' },
    { href: '/how-it-works.html', label: 'How it works' },
    { href: '/features.html', label: 'Features' },
    { href: '/app.html', label: 'The app' },
    { href: '/pricing.html', label: 'Pricing' },
    { href: '/demo.html', label: 'Try the demo' },
    { href: '/faq.html', label: 'FAQ' },
    { href: '/contact.html', label: 'Contact' },
  ];

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
        <a class="logo" href="${resolve('/')}"><span class="mark">AR</span> analogreader</a>
        <button class="nav-toggle" aria-label="Toggle menu">☰</button>
        <nav class="nav" id="site-nav">
          ${NAV.map(n => `<a href="${resolve(n.href)}" class="${active(n.href) ? 'active' : ''}">${n.label}</a>`).join('')}
          <a class="cta" href="${resolve('/demo.html')}">Try it free</a>
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
          <a class="logo" href="${resolve('/')}"><span class="mark">AR</span> analogreader</a>
          <p style="margin-top:.7rem">Turn the photo of your old analog meter into a digital reading. Track power, gas, and water in one place — no installation, no utility-company contract.</p>
        </div>
        <div>
          <h4>Product</h4>
          <a href="${resolve('/how-it-works.html')}">How it works</a>
          <a href="${resolve('/features.html')}">Features</a>
          <a href="${resolve('/demo.html')}">Live demo</a>
          <a href="${resolve('/pricing.html')}">Pricing</a>
        </div>
        <div>
          <h4>Support</h4>
          <a href="${resolve('/faq.html')}">FAQ</a>
          <a href="${resolve('/contact.html')}">Contact</a>
          <a href="${resolve('/privacy.html')}">Privacy</a>
          <a href="${resolve('/terms.html')}">Terms</a>
        </div>
        <div>
          <h4>Connect</h4>
          <a href="https://github.com/DanBarbu">GitHub</a>
          <a href="${resolve('/api.html')}">Developer API</a>
        </div>
        <div class="copy">
          © ${new Date().getFullYear()} analogreader.online. Built by Dan Barbulescu. The OCR engine and platform code are derived from the open-source <a href="https://github.com/DanBarbu/EcoVpp">EcoVpp project</a> (Apache-2.0).
        </div>
      </div>`;
  }

  /* ------------------------------------------------------- Demo: upload OCR */
  const METER_KINDS = {
    power: { label: 'Electricity', unit: 'kWh', rate: 0.235, icon: '⚡', cssClass: 'power' },
    gas:   { label: 'Gas',         unit: 'm³',  rate: 1.120, icon: '🔥', cssClass: 'gas' },
    water: { label: 'Water',       unit: 'm³',  rate: 4.250, icon: '💧', cssClass: 'water' },
  };

  function mockOCR(kind) {
    // Deterministic-ish reading per kind so the demo feels real.
    const base = { power: 48213, gas: 12876, water: 9342 }[kind];
    const value = base + Math.floor(Math.random() * 25);
    const conf = 0.78 + Math.random() * 0.21;
    return { value, confidence: Math.round(conf * 100) / 100 };
  }

  function renderReading(target, file, kind) {
    const url = file ? URL.createObjectURL(file) : 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 width=%22120%22 height=%2290%22%3E%3Crect width=%22120%22 height=%2290%22 fill=%22%23000%22/%3E%3Ctext x=%2250%25%22 y=%2255%25%22 fill=%22%23555%22 font-family=%22monospace%22 font-size=%2220%22 text-anchor=%22middle%22%3E--meter--%3C/text%3E%3C/svg%3E';
    const meta = METER_KINDS[kind];
    const out = mockOCR(kind);
    const cost = (out.value * meta.rate).toFixed(2);
    const flag = out.confidence < 0.80
      ? `<span class="badge amber">low confidence · sent for review</span>`
      : `<span class="badge green">verified</span>`;
    target.innerHTML = `
      <div class="meter-preview">
        <img src="${url}" alt="Meter photo" />
        <div class="info">
          <div class="reading">${out.value.toLocaleString()} <small style="font-size:1rem;color:var(--muted)">${meta.unit}</small></div>
          <div class="meta">${meta.icon} ${meta.label} · ${flag}</div>
          <div class="meta" style="margin-top:.35rem">Estimated cost so far: <strong>€${cost}</strong></div>
          <div class="confidence" style="margin-top:.4rem">Confidence
            <span class="bar"><span class="fill" style="width:${(out.confidence * 100).toFixed(0)}%"></span></span>
            ${(out.confidence * 100).toFixed(0)}%
          </div>
        </div>
      </div>`;
  }

  function mountDropzone() {
    const dz = document.getElementById('dropzone');
    if (!dz) return;
    const input = dz.querySelector('input[type=file]');
    const kindSel = document.getElementById('meter-kind');
    const result = document.getElementById('reading-result');

    function handle(file) {
      const kind = kindSel ? kindSel.value : 'power';
      renderReading(result, file, kind);
    }

    dz.addEventListener('click', () => input && input.click());
    if (input) input.addEventListener('change', (e) => { if (e.target.files[0]) handle(e.target.files[0]); });
    dz.addEventListener('dragover', (e) => { e.preventDefault(); dz.classList.add('drag'); });
    dz.addEventListener('dragleave', () => dz.classList.remove('drag'));
    dz.addEventListener('drop', (e) => {
      e.preventDefault(); dz.classList.remove('drag');
      const f = e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) handle(f);
    });

    // Trigger a sample reading immediately so the page feels alive.
    handle(null);
  }

  /* --------------------------------------------------------- Consumption chart */
  function mountChart() {
    const chart = document.getElementById('consumption-chart');
    if (!chart) return;
    const kind = chart.dataset.kind || 'power';
    const days = 30;
    for (let i = 0; i < days; i++) {
      const v = 40 + Math.random() * 60 + (i > 22 ? 20 : 0);
      const bar = document.createElement('div');
      bar.className = 'bar ' + (METER_KINDS[kind] ? METER_KINDS[kind].cssClass : '');
      bar.style.height = v + '%';
      bar.title = `Day ${i + 1}: ${v.toFixed(0)} ${METER_KINDS[kind].unit}`;
      chart.appendChild(bar);
    }
  }

  /* ------------------------------------------------------------------- Form */
  function mountContactForm() {
    const f = document.getElementById('contact-form');
    if (!f) return;
    f.addEventListener('submit', (e) => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(f).entries());
      const out = document.getElementById('contact-result');
      out.innerHTML = `<div class="callout" style="margin-top:1rem"><h3>Thanks, ${escape(data.name || 'there')}!</h3><p>This is a demo form — wire it to your CRM, Mailchimp, Netlify Forms, or a Cloudflare Worker. Payload logged to console.</p></div>`;
      console.info('[analogreader contact]', data);
      f.reset();
    });
  }

  function escape(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

  document.addEventListener('DOMContentLoaded', () => {
    mountHeader();
    mountFooter();
    mountDropzone();
    mountChart();
    mountContactForm();
  });
})();
