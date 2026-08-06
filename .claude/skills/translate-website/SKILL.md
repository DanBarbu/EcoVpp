---
name: translate-website
description: |
  Translate a static website into one or more additional EU languages while
  keeping full compliance with EU/national online legislation (GDPR, ePrivacy,
  E-Commerce, Accessibility). Use this when the user asks for language
  versions of an existing site, or asks to bring a site into legal compliance
  in EU countries.
---

# Translating a static website into EU languages, with compliance

Use this skill when the user asks to (a) translate a site into one or more EU languages, and/or (b) make a site EU-compliant.

## Non-negotiables — don't skip these

Every localized version must ship with:

1. **Privacy Policy** — GDPR arts. 13–14 + national implementation (LOPDGDD / BDSG / Codice Privacy / Legea 190/2018).
2. **Legal Notice / Impressum / Aviso legal / Note legali / Notă legală** — Directive 2000/31/EC + national (§ 5 DDG, Ley 34/2002 LSSI-CE, D.Lgs. 70/2003, Legea 365/2002).
3. **Terms of Use / AGB / Condiciones / Termini / Termeni** — governs website access; note that service contracts are separate.
4. **Accessibility Statement** — Directive (EU) 2016/2102 + national + EAA 2019/882; commit to WCAG 2.1 AA (EN 301 549).
5. **Cookie/consent handling** — ePrivacy art. 5(3): consent required for **any** non-strictly-necessary storage. If you only use strictly-necessary items, say so explicitly and skip the consent banner in favour of a plain informational note.
6. **Language switcher** in the header — persistent, links to the equivalent page in each locale.
7. **`<html lang="xx">`** — set correctly per page (screen readers use it).

## Repo structure

Recommended for a static site:

```
mvp-site/
  index.html              # canonical (English) content + legal pages
  how-it-works.html
  features.html
  ...                     # marketing pages
  privacy.html            # legal
  legal.html
  terms.html
  accessibility.html
  404.html
  assets/
    style.css             # SHARED across locales
    app.js                # SHARED — contains i18n strings + nav injection + cookie banner
    favicon.svg
  ro/                     # one directory per locale
    index.html            # same file names as root, translated
    ...                   # links use `../assets/...`
  it/
  de/
  es/
```

Rules:
- Same filenames across locales so the language switcher can just swap the directory segment.
- Assets stay in `assets/` and are referenced with `../assets/…` from locale subdirs and `assets/…` from the root.
- The `app.js` header/footer injection detects the locale from `location.pathname` and picks strings from a `STRINGS` object keyed by locale code.

## Which languages, which pages

Marketing pages should be translated in full — no half-translated headers with English body. Legal pages **must** be in a language the user understands (national consumer-protection law requires it).

Minimum coverage per locale:

- All landing/marketing pages (home, how-it-works, features, pilots/where-we-work, demo, faq, contact).
- All legal pages (privacy, legal/impressum, terms, accessibility).
- 404.

Do not machine-translate legal pages without a review pass — legal terminology matters. Match the terminology used by the national regulator's own website when in doubt.

## National regulatory anchors to cite

| Country | Website legal notice | Privacy authority | Accessibility authority | Consumer protection |
|---|---|---|---|---|
| Romania | Legea 365/2002 | ANSPDCP | ADR (Autoritatea pentru Digitalizarea României) | ANPC |
| Italy | D.Lgs. 70/2003, Codice del Consumo (D.Lgs. 206/2005) | Garante Privacy | AgID | AGCM |
| Germany | § 5 DDG, § 55 MStV | BfDI + Landesdatenschutzbehörden | BFIT-Bund | Verbraucherzentrale |
| Spain | Ley 34/2002 LSSI-CE, RDL 1/2007 (LGDCU) | AEPD | OAW / OADIS | AECOSAN |

For every legal page, cite the **applicable national law** in the first paragraph, not just GDPR. This is what distinguishes a compliant page from a template.

## Data placeholders — do NOT hallucinate

Legal pages must include real company data:
- Company legal name
- Registered address
- Company/commercial register number
- Tax ID (VAT / CUI / P. IVA / NIF / USt-IdNr.)
- Legal representative
- DPO contact if designated

**If you do not have these**, use visually-obvious placeholders (e.g. `<span class="placeholder">[COMPANY LEGAL NAME]</span>`) styled in a warning colour, and note in the PR description that the user must fill them before going live. Never invent them.

## Cookie banner logic

If the site uses only strictly-necessary storage:
- No legal consent is required — but a short informational banner is best practice.
- Store the "seen it" flag under a distinct key (`ecovpp.cookies` etc.), not a marketing-style ID.
- Provide an "accept" button that only dismisses the banner (does not enable anything hidden).
- Link the banner to the Privacy Policy in the same locale.

If the site adds analytics/marketing later, upgrade to a full consent-management pattern: reject-all button of equal prominence to accept-all (CJEU ruling C-673/17 Planet49; French CNIL guidance), granular categories, one-click withdraw.

## Practical steps to follow

1. **Copy the English page structure** for each locale into `mvp-site/<lang>/`.
2. **Translate marketing pages** page by page, keeping component structure identical so shared CSS works.
3. **Write legal pages against the national law of each locale**, not just via translation — the citations differ per country.
4. **Add locale to `STRINGS` in `assets/app.js`** for nav labels, cookie banner text, and footer link labels.
5. **Set `<html lang="xx">`** on every page.
6. **Add hreflang tags** to `<head>` for SEO if the site will be indexed:
   ```html
   <link rel="alternate" hreflang="en" href="https://example.eu/index.html" />
   <link rel="alternate" hreflang="ro" href="https://example.eu/ro/index.html" />
   <link rel="alternate" hreflang="x-default" href="https://example.eu/" />
   ```
7. **Test the language switcher** on every page: `en/features` → `de/features` etc. Files must have identical names across locales.
8. **Sanity-check** each locale root loads its own CSS and JS via the `../assets/` path.
9. **Verify placeholders** — `grep 'class="placeholder"'` to list every field the user must fill before publishing.
10. **Add a compliance checklist to the PR** so the user knows what to fill in.

## Terminology quick reference (translation choices)

| English | RO | IT | DE | ES |
|---|---|---|---|---|
| Solar sharing | împărțire solară | condivisione solare | Solaraufteilung | reparto solar |
| Bill credit | credit pe factură | sconto in bolletta | Rechnungs­gutschrift | descuento en la factura |
| Building manager | administrator | amministratore | Hausverwaltung | administración de fincas |
| Community battery | baterie comună | batteria di comunità | Gemeinschaftsspeicher | batería comunitaria |
| Renewable Energy Directive | Directiva UE privind energiile regenerabile | Direttiva sulle Energie Rinnovabili | Erneuerbare-Energien-Richtlinie | Directiva de Energías Renovables |

Keep terminology consistent within a locale — decide once per string and reuse via the `STRINGS` object where possible.

## When the user says "make it compliant to X site"

- Ask (or infer) which country/language the reference site targets.
- Read the reference's Privacy, Legal, Terms, Accessibility, and Cookie pages if reachable.
- Mirror the **structure and authority citations**, not the wording — copying wording infringes copyright.
- Compare our footer link set (privacy, legal, terms, accessibility) to theirs; add anything missing.
