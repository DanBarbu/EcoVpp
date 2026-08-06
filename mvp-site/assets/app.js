/* EcoVPP MVP — shared header/footer/nav injection + form handler */
(function () {
  const NAV = [
    { href: '/', label: 'Home' },
    { href: '/how-it-works.html', label: 'How it works' },
    { href: '/features.html', label: 'Features' },
    { href: '/pilots.html', label: 'Where we work' },
    { href: '/demo.html', label: 'Demo' },
    { href: '/faq.html', label: 'FAQ' },
  ];

  function basePath() {
    const m = location.pathname.match(/^(.*\/)([^/]*)$/);
    return m ? m[1] : '/';
  }
  function resolve(href) {
    if (href === '/') return basePath() || './';
    if (href.startsWith('/')) return basePath() + href.slice(1);
    return href;
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
        <a class="logo" href="${resolve('/')}"><span class="mark">EV</span> EcoVPP</a>
        <button class="nav-toggle" aria-label="Toggle menu">☰</button>
        <nav class="nav" id="site-nav">
          ${NAV.map(n => `<a href="${resolve(n.href)}" class="${active(n.href) ? 'active' : ''}">${n.label}</a>`).join('')}
          <a class="cta" href="${resolve('/contact.html')}">Contact</a>
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
          <a class="logo" href="${resolve('/')}"><span class="mark">EV</span> EcoVPP</a>
          <p style="margin-top:.7rem">A platform that lets neighbours share the solar energy they produce and lowers everyone's bill.</p>
        </div>
        <div>
          <h4>Product</h4>
          <a href="${resolve('/how-it-works.html')}">How it works</a>
          <a href="${resolve('/features.html')}">Features</a>
          <a href="${resolve('/demo.html')}">Demo</a>
          <a href="${resolve('/pilots.html')}">Where we work</a>
        </div>
        <div>
          <h4>Company</h4>
          <a href="${resolve('/contact.html')}">Contact</a>
          <a href="${resolve('/faq.html')}">FAQ</a>
          <a href="${resolve('/privacy.html')}">Privacy</a>
        </div>
        <div class="copy">
          © ${new Date().getFullYear()} EcoVPP. Built with the energy transition in mind.
        </div>
      </div>`;
  }

  function mountContactForm() {
    const f = document.getElementById('contact-form');
    if (!f) return;
    f.addEventListener('submit', (e) => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(f).entries());
      const out = document.getElementById('contact-result');
      out.innerHTML = `<div class="callout" style="margin-top:1rem;text-align:left"><h3>Thanks, ${escape(data.name || 'there')}.</h3><p>We'll get back to you within two working days.</p></div>`;
      console.info('[ecovpp-mvp] contact form submission', data);
      f.reset();
    });
  }

  function escape(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

  document.addEventListener('DOMContentLoaded', () => {
    mountHeader();
    mountFooter();
    mountContactForm();
  });
})();
