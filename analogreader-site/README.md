# analogreader.online — demo website

Consumer-facing static site for **analogreader.online** — a service that turns photos of analog electricity, gas, and water meters into digital readings.

Built in the same style as the [EcoVpp demo site](../site/) (the platform's OCR pipeline is the engine behind both products). 10 pages, no build step, deployable to any static host in under a minute.

## Pages

| File | Purpose |
|------|---------|
| `index.html` | Landing — three meter types, four-step process, CTAs |
| `how-it-works.html` | Pipeline breakdown, confidence scoring, supported meters |
| `features.html` | Full feature catalogue grouped by Capture / Read / Track / Share / Pro |
| `pricing.html` | Four-tier pricing (Free / Pro / Team / Enterprise) + FAQ |
| `demo.html` | Interactive: drop a meter photo, get a mocked reading + 30-day chart |
| `faq.html` | Common questions grouped by Product / Privacy / Integrations / Billing |
| `api.html` | Developer REST API reference (mock examples) |
| `contact.html` | Inquiry form (logs to console — see "Wiring the form") |
| `privacy.html` | GDPR-aligned policy template |
| `terms.html` | ToS template — replace before going live |
| `404.html` | Branded not-found page |

Shared assets live in `assets/`: `style.css`, `app.js` (header/footer/demo/upload), `favicon.svg`.

## Run locally

```bash
cd analogreader-site
python3 -m http.server 8080
# open http://localhost:8080/
```

Any static server works.

## Deploy

### Netlify (drag-drop, fastest)

Open https://app.netlify.com/drop and drag the `analogreader-site` folder in. Site is live within seconds.

Or via CLI:

```bash
cd analogreader-site
netlify deploy --prod --dir .
```

### Vercel

```bash
cd analogreader-site && npx vercel --prod
```

### Cloudflare Pages

Connect your repo, set **Build output directory** = `analogreader-site` (or `.` if you split it into its own repo), no build command.

### Plain hosting (any web server)

Upload the contents of `analogreader-site/` to your web root. That's it — no build, no Node, no Python.

## Move to its own repo

To split this folder into a standalone repository (recommended for production):

```bash
# 1. Create the new repo on GitHub UI: https://github.com/new
#    Name: analogreader-online (or any name you like)

# 2. From the EcoVpp repo root:
git subtree split --prefix=analogreader-site -b analogreader-only
mkdir /tmp/analogreader && cd /tmp/analogreader
git init && git pull /path/to/EcoVpp analogreader-only
git remote add origin git@github.com:DanBarbu/analogreader-online.git
mv .github-workflow-pages.yml .github/workflows/pages.yml  # restructure files
git add . && git commit -m "Initial commit (split from EcoVpp)"
git push -u origin main
```

After the first push:

1. Settings → Pages → Source = **GitHub Actions**.
2. Settings → Pages → Custom domain → `analogreader.online`.
3. At your DNS host (Spaceship), set:
   - `A` records for `@` pointing to GitHub's four Pages IPs:
     `185.199.108.153`, `185.199.109.153`, `185.199.110.153`, `185.199.111.153`
   - `CNAME` for `www` pointing to `<your-user>.github.io`
4. Drop a file called `CNAME` (one line: `analogreader.online`) in the repo root before deploying.

## Wiring the contact form

`assets/app.js` → `mountContactForm()` currently logs to the console. Replace with one of:

**Netlify Forms** (add `netlify` attribute):

```html
<form id="contact-form" netlify>
```

**Cloudflare Worker / SendGrid / Mailchimp**:

```js
fetch('https://your-endpoint', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(data),
});
```

## Wiring the OCR demo

`assets/app.js` → `mockOCR()` currently returns a deterministic-ish fake reading. Swap for the real call:

```js
async function ocr(file, kind) {
  const fd = new FormData();
  fd.append('photo', file);
  fd.append('kind', kind);
  const r = await fetch('/api/v1/readings/ocr', {
    method: 'POST',
    headers: { 'Authorization': 'Bearer ' + token },
    body: fd,
  });
  return r.json(); // { value, confidence }
}
```

Production OCR can be served by:

- The EcoVpp `webhook-receiver` service (route the upload to `/api/v1/telemetry/ingest` + OCR worker).
- A standalone Cloudflare Worker / AWS Lambda calling Google Cloud Vision, AWS Textract, or your own ONNX model.
- An on-device inference build (TensorFlow.js, ONNX Runtime Web) — runs entirely in the browser.

## Branding

| Variable | Default | Where |
|----------|---------|-------|
| Brand colour (cyan/teal gradient) | `#5eead4 → #22d3ee → #3b82f6` | `assets/style.css` → `--brand`, `--accent` |
| Power colour | `#fbbf24` | `assets/style.css` → `--power` |
| Gas colour | `#fb923c` | `assets/style.css` → `--gas` |
| Water colour | `#60a5fa` | `assets/style.css` → `--water` |
| Logo mark | "AR" in a teal square | `assets/app.js` → `mountHeader()` |
| Favicon | SVG | `assets/favicon.svg` |

Adjust those four files and the rest of the site follows.

## License

Apache-2.0 (same as the EcoVpp platform it builds on).
