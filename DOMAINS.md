# Pointing your domains at the demo sites

You own two domains:

- **ecovpp.eu** — for the EcoVpp platform marketing/demo (`site/`)
- **analogreader.online** — for the analog-meter OCR product (`analogreader-site/`)

There are three "easy" ways to forward each domain at the site code. Pick the row that matches the smallest amount of setup you want to do.

| Option | Time | Where it runs | Custom domain set-up |
|--------|------|---------------|----------------------|
| **A. Netlify drag-drop + URL forwarding at Spaceship** | 2 min | Netlify CDN | A 301 forward at the registrar, no DNS edits needed |
| **B. Netlify with real DNS** | 5 min | Netlify CDN | A/CNAME records at Spaceship |
| **C. GitHub Pages with custom domain** | 5 min | GitHub Pages | A/CNAME records at Spaceship + repo setting |

`CNAME` files are already committed for option C: `site/CNAME` = `ecovpp.eu`, `analogreader-site/CNAME` = `analogreader.online`.

---

## Option A — Netlify drag-drop + Spaceship URL forwarding (fastest)

Best when you just want the domain to point somewhere working *today*.

1. Open https://app.netlify.com/drop.
2. Drag the **`site`** folder in. Netlify gives you a URL like `https://radiant-fox-1234.netlify.app`. Copy it.
3. In Spaceship → **Domains** → `ecovpp.eu` → **Forwarding** → **Add URL forward**:
   - Target URL: paste the Netlify URL.
   - Forwarding type: **301 (permanent)**.
   - Save.
4. Repeat for `analogreader.online` with the **`analogreader-site`** folder.

Caveats: a URL forward shows the Netlify URL in the address bar after the redirect. If you want the address bar to keep showing `ecovpp.eu`, pick option B instead.

---

## Option B — Netlify with real DNS

Best when you want `ecovpp.eu` to stay in the address bar and you want automatic HTTPS without GitHub Pages.

1. Drag-drop the folder to Netlify (same as option A, steps 1–2).
2. Netlify dashboard → **Domain management** → **Add custom domain** → enter `ecovpp.eu`.
3. Netlify shows you the DNS records. At Spaceship → **Domains** → `ecovpp.eu` → **Advanced DNS**, add:
   - `A`     `@`   → the four Netlify load-balancer IPs they show you
   - `CNAME` `www` → `<your-netlify-subdomain>.netlify.app`
4. Wait 5–60 min for DNS propagation. Netlify issues a Let's Encrypt cert automatically.
5. Repeat the whole sequence for `analogreader.online`.

---

## Option C — GitHub Pages custom domain

Best when you want everything served straight from GitHub. The `CNAME` files in `site/` and `analogreader-site/` already declare the domains, so once Pages is enabled the workflow will publish them.

### One-time setup per domain

`analogreader.online` should be in its own repo — see [`analogreader-site/README.md → "Move to its own repo"`](analogreader-site/README.md). Once that's done, each repo is a separate Pages site with its own custom domain.

For **ecovpp.eu** (this repo):

1. https://github.com/DanBarbu/EcoVpp/settings/pages → **Source** = **GitHub Actions** (one click).
2. https://github.com/DanBarbu/EcoVpp/settings/pages → **Custom domain** → enter `ecovpp.eu` → **Save**.
3. At Spaceship → **Domains** → `ecovpp.eu` → **Advanced DNS**, add the records GitHub shows you (the standard four A records below):

   ```
   A     @     185.199.108.153
   A     @     185.199.109.153
   A     @     185.199.110.153
   A     @     185.199.111.153
   CNAME www   DanBarbu.github.io
   ```

4. Wait 5–60 min. GitHub will issue an HTTPS cert automatically once the records resolve.
5. Tick **Enforce HTTPS** in the Pages settings.

For **analogreader.online** after spinning out its own repo:

1. Spin out the repo (see `analogreader-site/README.md`).
2. Move the workflow file: `mv .github-workflow-pages.yml .github/workflows/pages.yml`.
3. Same Pages + DNS steps as above, but pointing at the new repo and `analogreader.online`.

---

## Quick decision tree

```
Just want it to resolve to something today?           → Option A
Want the address bar to keep showing your domain?     → Option B
Want everything in GitHub, nothing else to manage?    → Option C
```

## DNS test commands

After any DNS change, verify with:

```bash
dig +short ecovpp.eu
dig +short analogreader.online
curl -I https://ecovpp.eu
```

Records take anywhere from a minute to an hour to propagate. If something looks off after an hour, https://dnschecker.org will tell you which resolvers have picked up the change and which haven't.
