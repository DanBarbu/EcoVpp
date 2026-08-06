/* EcoVPP MVP — shared header/footer/nav injection + language + cookies */
(function () {

  /* ------------------------------------------------------------------ i18n */
  const LOCALES = {
    en: { label: 'English',  flag: '🇬🇧', dir: '' },
    ro: { label: 'Română',   flag: '🇷🇴', dir: 'ro/' },
    it: { label: 'Italiano', flag: '🇮🇹', dir: 'it/' },
    de: { label: 'Deutsch',  flag: '🇩🇪', dir: 'de/' },
    es: { label: 'Español',  flag: '🇪🇸', dir: 'es/' },
  };

  const STRINGS = {
    en: { home:'Home', how:'How it works', features:'Features', pilots:'Where we work', demo:'Demo', faq:'FAQ', contact:'Contact',
          product:'Product', company:'Company', legal:'Legal notice', terms:'Terms', privacy:'Privacy', accessibility:'Accessibility',
          rights:'© %Y EcoVPP. All rights reserved.', tagline:'A platform that lets neighbours share the solar energy they produce.',
          cookieText:'We use only strictly-necessary cookies to remember your language and cookie preference. No tracking, no analytics, no third-party marketing.',
          cookieAccept:'Got it', cookieMore:'Read the privacy policy',
          submit:'Send →', formOk:'Thanks, %s. We\'ll get back to you within two working days.' },
    ro: { home:'Acasă', how:'Cum funcționează', features:'Funcționalități', pilots:'Unde lucrăm', demo:'Demo', faq:'Întrebări', contact:'Contact',
          product:'Produs', company:'Companie', legal:'Notă legală', terms:'Termeni', privacy:'Confidențialitate', accessibility:'Accesibilitate',
          rights:'© %Y EcoVPP. Toate drepturile rezervate.', tagline:'O platformă care permite vecinilor să împartă energia solară produsă în comun.',
          cookieText:'Folosim doar cookie-uri strict necesare pentru a reține limba și preferința de cookie-uri. Fără urmărire, fără analitice, fără marketing terță parte.',
          cookieAccept:'Am înțeles', cookieMore:'Citește politica de confidențialitate',
          submit:'Trimite →', formOk:'Mulțumim, %s. Vă vom răspunde în două zile lucrătoare.' },
    it: { home:'Home', how:'Come funziona', features:'Funzionalità', pilots:'Dove operiamo', demo:'Demo', faq:'FAQ', contact:'Contatti',
          product:'Prodotto', company:'Azienda', legal:'Note legali', terms:'Termini', privacy:'Privacy', accessibility:'Accessibilità',
          rights:'© %Y EcoVPP. Tutti i diritti riservati.', tagline:'Una piattaforma che permette ai vicini di condividere l\'energia solare prodotta insieme.',
          cookieText:'Utilizziamo solo cookie strettamente necessari per ricordare la lingua e le preferenze sui cookie. Nessun tracciamento, nessuna analisi, nessun marketing di terze parti.',
          cookieAccept:'Ho capito', cookieMore:'Leggi l\'informativa privacy',
          submit:'Invia →', formOk:'Grazie, %s. Ti risponderemo entro due giorni lavorativi.' },
    de: { home:'Start', how:'So funktioniert es', features:'Funktionen', pilots:'Wo wir tätig sind', demo:'Demo', faq:'FAQ', contact:'Kontakt',
          product:'Produkt', company:'Unternehmen', legal:'Impressum', terms:'AGB', privacy:'Datenschutz', accessibility:'Barrierefreiheit',
          rights:'© %Y EcoVPP. Alle Rechte vorbehalten.', tagline:'Eine Plattform, mit der Nachbarn den gemeinsam erzeugten Solarstrom teilen.',
          cookieText:'Wir verwenden ausschließlich technisch notwendige Cookies zur Speicherung Ihrer Sprach- und Cookie-Einstellung. Kein Tracking, keine Analyse, kein Drittanbieter-Marketing.',
          cookieAccept:'Verstanden', cookieMore:'Datenschutzerklärung lesen',
          submit:'Senden →', formOk:'Danke, %s. Wir melden uns innerhalb von zwei Werktagen.' },
    es: { home:'Inicio', how:'Cómo funciona', features:'Funciones', pilots:'Dónde operamos', demo:'Demo', faq:'FAQ', contact:'Contacto',
          product:'Producto', company:'Empresa', legal:'Aviso legal', terms:'Términos', privacy:'Privacidad', accessibility:'Accesibilidad',
          rights:'© %Y EcoVPP. Todos los derechos reservados.', tagline:'Una plataforma que permite a los vecinos compartir la energía solar producida en común.',
          cookieText:'Solo utilizamos cookies estrictamente necesarias para recordar tu idioma y preferencia de cookies. Sin seguimiento, sin analítica, sin marketing de terceros.',
          cookieAccept:'Entendido', cookieMore:'Leer la política de privacidad',
          submit:'Enviar →', formOk:'Gracias, %s. Te responderemos en dos días laborables.' },
  };

  /* Nav pages (rel paths inside a locale directory / root) */
  const NAV = ['home', 'how', 'features', 'pilots', 'demo', 'faq'];
  const NAV_HREF = {
    home: 'index.html', how: 'how-it-works.html', features: 'features.html',
    pilots: 'pilots.html', demo: 'demo.html', faq: 'faq.html',
  };

  /* Detect current locale from URL: /ro/foo.html, /de/foo.html, else 'en' */
  function detectLocale() {
    const p = location.pathname;
    const m = p.match(/\/(ro|it|de|es)(\/|$)/);
    if (m) return m[1];
    return 'en';
  }
  const LOCALE = detectLocale();
  const T = STRINGS[LOCALE] || STRINGS.en;

  /* Path to project root (mvp-site/) from current page. */
  function rootPath() {
    if (LOCALE === 'en') return './';
    return '../';
  }

  /* Build a link to a page within a target locale. */
  function localePath(locale, filename) {
    const base = rootPath() + LOCALES[locale].dir;
    return base + filename;
  }

  /* Current page filename (index.html if trailing slash) */
  function currentFilename() {
    const p = location.pathname.split('/').pop();
    return p && p.includes('.') ? p : 'index.html';
  }

  /* Legal helpers */
  function legalPath(filename) { return rootPath() + LOCALES[LOCALE].dir + filename; }

  /* ---------------------------------------------------------------- header */
  function mountHeader() {
    const el = document.getElementById('site-header');
    if (!el) return;
    const navLinks = NAV.map(k => {
      const href = localePath(LOCALE, NAV_HREF[k]);
      const active = new RegExp(NAV_HREF[k].replace('.', '\\.') + '$').test(location.pathname) ||
                     (k === 'home' && (location.pathname.endsWith('/') || location.pathname.endsWith('/' + (LOCALES[LOCALE].dir || ''))));
      return `<a href="${href}" class="${active ? 'active' : ''}">${T[k]}</a>`;
    }).join('');
    const langLinks = Object.keys(LOCALES).map(code => {
      const target = localePath(code, currentFilename());
      return `<li><a href="${target}" class="${code === LOCALE ? 'active' : ''}"><span class="flag">${LOCALES[code].flag}</span>${LOCALES[code].label}</a></li>`;
    }).join('');
    el.innerHTML = `
      <div class="inner">
        <a class="logo" href="${localePath(LOCALE, 'index.html')}"><span class="mark">EV</span> EcoVPP</a>
        <button class="nav-toggle" aria-label="Toggle menu">☰</button>
        <nav class="nav" id="site-nav">
          ${navLinks}
          <div class="lang-switch" id="lang-switch">
            <button aria-haspopup="true" aria-expanded="false"><span class="flag">${LOCALES[LOCALE].flag}</span>${LOCALES[LOCALE].label} ▾</button>
            <ul>${langLinks}</ul>
          </div>
          <a class="cta" href="${localePath(LOCALE, 'contact.html')}">${T.contact}</a>
        </nav>
      </div>`;
    el.querySelector('.nav-toggle').addEventListener('click', () => {
      el.querySelector('#site-nav').classList.toggle('open');
    });
    const ls = el.querySelector('#lang-switch');
    ls.querySelector('button').addEventListener('click', (e) => {
      e.stopPropagation();
      ls.classList.toggle('open');
      ls.querySelector('button').setAttribute('aria-expanded', ls.classList.contains('open'));
    });
    document.addEventListener('click', () => ls.classList.remove('open'));
  }

  /* ---------------------------------------------------------------- footer */
  function mountFooter() {
    const el = document.getElementById('site-footer');
    if (!el) return;
    const y = new Date().getFullYear();
    el.innerHTML = `
      <div class="inner">
        <div>
          <a class="logo" href="${localePath(LOCALE, 'index.html')}"><span class="mark">EV</span> EcoVPP</a>
          <p style="margin-top:.7rem">${T.tagline}</p>
        </div>
        <div>
          <h4>${T.product}</h4>
          <a href="${localePath(LOCALE, 'how-it-works.html')}">${T.how}</a>
          <a href="${localePath(LOCALE, 'features.html')}">${T.features}</a>
          <a href="${localePath(LOCALE, 'demo.html')}">${T.demo}</a>
          <a href="${localePath(LOCALE, 'pilots.html')}">${T.pilots}</a>
        </div>
        <div>
          <h4>${T.company}</h4>
          <a href="${localePath(LOCALE, 'contact.html')}">${T.contact}</a>
          <a href="${localePath(LOCALE, 'faq.html')}">${T.faq}</a>
          <a href="${localePath(LOCALE, 'legal.html')}">${T.legal}</a>
          <a href="${localePath(LOCALE, 'terms.html')}">${T.terms}</a>
          <a href="${localePath(LOCALE, 'privacy.html')}">${T.privacy}</a>
          <a href="${localePath(LOCALE, 'accessibility.html')}">${T.accessibility}</a>
        </div>
        <div class="copy">${T.rights.replace('%Y', y)}</div>
      </div>`;
  }

  /* ------------------------------------------------------------- cookie UI */
  function mountCookieBanner() {
    if (localStorage.getItem('ecovpp.cookies') === 'accepted') return;
    const div = document.createElement('div');
    div.id = 'cookie-banner';
    div.className = 'show';
    div.innerHTML = `
      <p>${T.cookieText}</p>
      <div class="actions">
        <a href="${localePath(LOCALE, 'privacy.html')}"><button type="button">${T.cookieMore}</button></a>
        <button type="button" class="primary" id="cookie-accept">${T.cookieAccept}</button>
      </div>`;
    document.body.appendChild(div);
    div.querySelector('#cookie-accept').addEventListener('click', () => {
      localStorage.setItem('ecovpp.cookies', 'accepted');
      div.remove();
    });
  }

  /* ------------------------------------------------------------ contact fm */
  function mountContactForm() {
    const f = document.getElementById('contact-form');
    if (!f) return;
    f.addEventListener('submit', (e) => {
      e.preventDefault();
      const data = Object.fromEntries(new FormData(f).entries());
      const out = document.getElementById('contact-result');
      out.innerHTML = `<div class="callout" style="margin-top:1rem;text-align:left"><h3>${T.formOk.replace('%s', escape(data.name || ''))}</h3></div>`;
      console.info('[ecovpp-mvp] contact form submission', data);
      f.reset();
    });
  }

  function escape(s) { return String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c])); }

  document.documentElement.setAttribute('lang', LOCALE);
  document.addEventListener('DOMContentLoaded', () => {
    mountHeader();
    mountFooter();
    mountCookieBanner();
    mountContactForm();
  });
})();
