# EcoVPP MVP website

A clean, public-facing MVP for [EcoVPP](https://ecovpp.eu). Written to be understandable by residents and building managers — no jargon, no internal-project references, no dev tooling exposed.

## Pages

| File | Purpose |
|------|---------|
| `index.html` | Landing — value proposition + how it works overview + CTA |
| `how-it-works.html` | Four-step explanation, what residents need, what the manager handles |
| `features.html` | Grouped: for residents, for manager, add-ons |
| `pilots.html` | Countries currently active |
| `demo.html` | Interactive resident-dashboard preview with simulated data |
| `faq.html` | Common questions grouped by basics / money / privacy / practical |
| `contact.html` | Inquiry form |
| `privacy.html` | Plain-language privacy policy |
| `404.html` | Not-found page |

Shared assets in `assets/`: `style.css`, `app.js` (nav injection + form handler), `favicon.svg`.

## Run locally

```bash
cd mvp-site
python3 -m http.server 8080
# open http://localhost:8080/
```

## Deploy

Any static host works. This is a plain HTML/CSS/JS site with zero build step:

- **Drag-and-drop to Netlify**: https://app.netlify.com/drop → drop the `mvp-site` folder.
- **GitHub Pages**: add to the existing pages workflow, or point a separate Pages site at this directory.
- **Custom domain (`ecovpp.eu`)**: change the target URL in Dynadot forwarding to the MVP's URL, or point DNS at whichever host you deploy to.

## Relation to the rest of the repo

- `site/` — the original technical/marketing site (kept for reference).
- `analogreader-site/` — the consumer meter-digitisation product site.
- **`mvp-site/` (this)** — clean public MVP without internal references.

## Content guidelines followed

- No grant call identifiers, sprint numbers, or research annex references.
- No specific device model numbers or hardware bill of materials.
- No blockchain / DID terminology on public-facing pages.
- Pilots listed by country only (no addresses, unit counts, or personal contact info).
- Language kept accessible for a general audience.
