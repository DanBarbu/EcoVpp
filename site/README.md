# ECO-VPP demo website

A self-contained static website for the ECO-VPP platform. Six pages, no build step, no external dependencies, deployable to any static host in under a minute.

## Pages

| File | Purpose |
|------|---------|
| `index.html` | Landing page — hero, features, architecture, "try locally" CTA |
| `features.html` | Sprint-by-sprint feature breakdown |
| `pilots.html` | Pilot site map (RO / IT / ES / CH / MD) |
| `about.html` | Project context, FAQ, Horizon Europe framing |
| `demo.html` | Interactive operator dashboard demo (mocked, updates every 2 s) |
| `contact.html` | Inquiry form (logs to console — see "Wiring the form") |
| `404.html` | Branded not-found page |

Shared assets live in `assets/`: `style.css`, `app.js` (header/footer/demo logic), `favicon.svg`.

## Run locally

```bash
cd site
python3 -m http.server 8080
# then open http://localhost:8080/
```

Any static server works (`npx serve`, `caddy file-server`, `nginx`, `darkhttpd`).

## Deploy

### GitHub Pages

Already wired by `.github/workflows/pages.yml` at the repo root. Once Pages is enabled (Settings → Pages → Source = GitHub Actions), every push to `main` or `claude/**` publishes the `site/` directory. URL: `https://<user>.github.io/EcoVpp/`.

### Netlify

Drag-and-drop `site/` to https://app.netlify.com/drop, or wire the repo:

```bash
netlify deploy --dir=site --prod
```

`netlify.toml` is already in the directory.

### Vercel

```bash
cd site && vercel --prod
```

`vercel.json` configures clean URLs and asset caching.

### Cloudflare Pages

Connect the repo, set **Build output directory** = `site`, no build command needed.

### Plain S3 / nginx / Caddy

Upload the contents of `site/` to your bucket / docroot.

## Wiring the contact form

`assets/app.js` → `mountContactForm()` currently logs the submission to the console. Replace its body with one of:

**Netlify Forms** (just add `netlify` attribute):

```html
<form id="contact-form" netlify>
```

**Cloudflare Worker**:

```js
fetch('https://forms.your-domain.workers.dev/submit', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
});
```

**Mailchimp / SendGrid / HubSpot**: same pattern, swap the URL.

## Wiring the live demo

`assets/app.js` → `startDemo()` is fully self-contained mock data. To point it at the real platform:

1. Run the backend (`docker compose up -d` from the repo root).
2. In `startDemo`, replace `priceWave()` with a `fetch('/api/...')` call (snippet in `demo.html`).
3. For real-time updates, open a WebSocket to `/ws` — the protocol matches `services/webhook-receiver`.

## Browser support

ES2017+, no transpilation. Tested on current Chrome, Firefox, Safari, Edge. The site is fully responsive and renders without JavaScript (header/footer/demo are JS-injected, but every page's main content is plain HTML).

## License

Apache-2.0, same as the repo.
