# maximum-pain.com — Improvement Plan

> Prioritized roadmap for UX, performance, and code quality improvements.
> Updated 2026-04-28 to reflect PR #76 completions (Angular 17, Lambda@Edge SEO, SeoService, new components).

---

## What Was Completed in PR #76

| Item | Status |
|---|---|
| Angular 13 → 17 upgrade (esbuild builder) | ✅ Done |
| SEO: Dynamic titles/meta via `SeoService` (description, OG, Twitter cards) | ✅ Done |
| SEO: JSON-LD structured data (Organization, Article, FAQPage) | ✅ Done |
| SEO: Lambda@Edge server-side `<title>` injection for all ticker pages | ✅ Done |
| SEO: `SitemapService` — programmatic XML sitemap generator | ✅ Done |
| SEO: `robots.txt` updated (blocks `/admin/`, references sitemap) | ✅ Done |
| New page: Glossary (`/glossary`) with FAQPage schema, 15+ option terms | ✅ Done |
| New component: `CandlestickComponent` (`/candlestick/:id`) — Google Charts | ✅ Done |
| New component: `ChartcandleComponent` — responsive candlestick widget | ✅ Done |
| In-memory option chain cache (`OptionChainCacheService`) — reduces Schwab API calls | ✅ Done |
| Educational content blocks on Options and Screener pages (300+ words each) | ✅ Done |
| `MaxPainChart` legacy project removed from repo | ✅ Done |
| `ChartHelper` moved to `MaxPainInfrastructure` | ✅ Done |
| CI/CD: Lambda@Edge auto-deployed via `CICD-S3-MaxPainUI-Edge.yml` | ✅ Done |
| New DB views: `vwDaily`, `vwDaily2`, `vwHistoricalStockQuote` | ✅ Done |

---

## Priority 1 — Home Page Redesign

### Current State
Basic Bootstrap card grid: one AdSense ad (above fold), one static "Where do I Start?" card, one email subscribe widget, one OI walls promo card, and blog post cards loaded via API. No hero, no value proposition, no CTA hierarchy.

### Target State
A high-converting, fast-loading landing page that immediately communicates what the site does and funnels visitors toward the core tool.

#### 1a. Hero Section
Add a full-width hero above the fold with a centered ticker search:
```html
<div class="mp-hero">
  <h1>Find Options Max Pain in Seconds</h1>
  <p>See where market makers want your stock to close — for any ticker, any expiration.</p>
  <div class="mp-hero-search">
    <input placeholder="Enter a ticker (e.g. SPY, AAPL, TSLA)" />
    <button>Analyze →</button>
  </div>
  <!-- Quick-access chips: SPY | QQQ | AAPL | NVDA | TSLA -->
</div>
```
- Search navigates to `/options/:ticker`
- Popular ticker chips for one-click access
- Dark background with subtle candlestick pattern SVG
- Update `SeoService` call to add `WebSite` schema with `SearchAction` (enables Google sitelinks search box)

#### 1b. "How It Works" Strip
Three-column explainer below hero:
1. 🔍 We collect live option chain data from all expirations
2. 📊 We calculate the max pain strike — where sellers profit most
3. 🎯 You use it to time trades and manage risk

#### 1c. Feature Cards Grid (Structured)
Replace the mixed-content card soup with purpose-built feature cards:

| Card | Link |
|---|---|
| Max Pain Chart | /options/SPY |
| Candlestick | /candlestick/SPY |
| OI Walls | /outside-oi-walls |
| Daily Scan | /daily-scan |
| Greeks | /greeks/SPY |
| IV Chart | /iv/SPY |
| Glossary | /glossary |
| Download CSV | /download-csv |

#### 1d. Live "Today's Top OI Walls" Widget
Pull from the existing `OutsideOIWalls` data:
- Top 5 stocks with significant OI walls
- Link each to `/options/:ticker`
- Auto-updates since data is already collected nightly

#### 1e. Recent Blog Posts (List, not cards)
Replace home page blog cards with a clean horizontal list:
- Title, date, 1-line excerpt, "Read →" link
- Max 3 posts, sorted by date

#### 1f. Move AdSense Below Fold
Top-of-page ads hurt UX and Core Web Vitals. Move to bottom or sidebar.

---

## Priority 2 — Blog Redesign

### Current State
- Blog home: small image cards, no dates, no tags, no pagination
- Blog post: raw HTML dump, no reading time, no TOC, no related posts, no social sharing
- `SeoService` now injects meta/OG tags per post ✅ (PR #76) — layout unchanged
- URL: `/blog/archive/title/` — "archive" subfolder is redundant

### Changes

#### 2a. Blog Home (`/blog`) — List Layout
```
┌─────────────────────────────────────────┐
│ [Thumbnail]  Title of Post              │
│              Apr 27, 2026 · 4 min read  │
│              2-line excerpt...          │
│              [Read More →]              │
└─────────────────────────────────────────┘
```
- Sort by date descending
- Show date, reading time estimate (word count ÷ 200), excerpt
- Pagination — currently loads all posts at once

#### 2b. Blog Post Layout
- Meta bar: date, reading time, social share (Twitter/X, copy link)
- Table of contents (auto-generated from H2/H3 in content)
- Max content width ~720px centered (not full-width `col-12`)
- Related posts (3 most recent) at bottom

#### 2c. Fix URL Structure
- `/blog/where-do-i-start/` instead of `/blog/archive/where-do-i-start/`
- Add 301 redirects for old URLs (preserve SEO)
- Update `SitemapService` to use new pattern
- Update `lambda-edge/index.js` `ROUTE_TITLES` to cover `/blog/:slug`

#### 2d. Add Sidebar Links for New Pages
`/glossary` and `/candlestick` were added in PR #76 but are **not in the sidebar** yet:
```html
<li>
  <a [routerLink]='["/glossary"]'>
    <i class="fas fa-book" title="Glossary"></i>
    <span>Glossary</span>
  </a>
</li>
<li>
  <a [routerLink]='["/candlestick"]'>
    <i class="fas fa-chart-candlestick" title="Candlestick"></i>
    <span>Candlestick</span>
  </a>
</li>
```

---

## Priority 3 — Performance Enhancements

### 3a. ✅ Angular 17 Upgrade — DONE (PR #76)
Remaining migration work:
- Migrate NgModules → standalone components (incremental; start with new components)
- Adopt `@if` / `@for` control flow (replaces `*ngIf` / `*ngFor`)

### 3b. Lazy Loading Route Modules
All components currently in one bundle. Split into per-route chunks:
```typescript
{ path: 'blog', loadComponent: () => import('./blog/blog.component') }
```
Priority routes: `/candlestick`, `/greeks`, `/spreads`, `/iv`, `/history`, `/blog`, `/glossary`.
Expected bundle reduction: 40–60%.

### 3c. Lambda@Edge → CloudFront Functions
Lambda@Edge adds ~200–400ms cold start on cache miss. For simple title rewriting, **CloudFront Functions** is a better fit:
- Sub-millisecond execution (runs at edge, no cold start)
- Free tier: 2M requests/month
- Limitation: no `http` module, no external calls — but title rewriting needs neither
- Migrate `lambda-edge/index.js` logic to a CloudFront Function for significant latency improvement

### 3d. Self-Host Font Awesome
Currently loaded from CDN (`cdnjs.cloudflare.com`). Self-hosting eliminates third-party DNS lookup:
```bash
npm install @fortawesome/fontawesome-free
```
Remove CDN `@import` from `styles.scss`. Expected LCP improvement: 100–300ms.

### 3e. CloudFront Caching for API Responses
Option chains update once per day. Add `Cache-Control` headers to Lambda responses:
- Option chain: `Cache-Control: public, max-age=3600`
- Blog posts: `Cache-Control: public, max-age=86400`
- Chart images: `Cache-Control: public, max-age=3600`

### 3f. Image Optimization
- Convert PNGs/JPGs in `/assets/images/` to WebP
- Add `loading="lazy"` to non-above-fold images
- Add explicit `width`/`height` to prevent CLS
- Priority images: `OIWalls2.png`, `question_mark_small.png`, blog thumbnails

### 3g. Google Charts → Self-Hosted (ChartcandleComponent)
`ChartcandleComponent` uses Google Charts (external `gstatic.com` script). Migration to Chart.js or `lightweight-charts` would:
- Eliminate external script dependency
- Faster load (no Google CDN lookup)
- More control over styling and theming (light/dark already in the component)

### 3h. Admin Route Protection
All `/admin/*` routes are public. Add a route guard — even a simple token check:
```typescript
{ path: 'admin/blogmanager', component: BlogmanagerComponent, canActivate: [AuthGuard] }
```

---

## Priority 4 — Remaining SEO Work

### 4a. ✅ SeoService — DONE (PR #76)

### 4b. ✅ Lambda@Edge Title Injection — DONE (PR #76)

### 4c. Extend Lambda@Edge to Inject Meta Description
Currently Lambda@Edge only rewrites `<title>`. Extend `index.js` to also inject:
```html
<meta name="description" content="AAPL (Apple Inc.) Max Pain and Open Interest analysis">
```
The `TICKER_COMPANIES` lookup already has company names — just needs a `ROUTE_DESCRIPTIONS` map alongside `ROUTE_TITLES`.

### 4d. Sitemap Automation
- Wire `SitemapService` to regenerate and upload `google-sitemap.xml` to S3 on each deploy
- Submit to Google Search Console and Bing Webmaster Tools

### 4e. Structured Data for Options Pages
Add `Dataset` schema to each options page:
```json
{
  "@type": "Dataset",
  "name": "AAPL Max Pain Data",
  "description": "Open interest and max pain calculation for Apple Inc. options"
}
```

---

## Priority 5 — UX / DX

### 5a. Mobile Navigation
Sidebar icon-only on collapse is confusing on mobile. Consider a bottom tab bar:
- 5 items: Options, Scan, OI Walls, Blog, More

### 5b. Ticker Persistence
Ticker lost when navigating away. Persist via `StateService` and/or query params:
- `/options?ticker=AAPL`

### 5c. Local Dev — Docker Compose
```yaml
services:
  db:
    image: mcr.microsoft.com/mssql/server:2022-latest
    environment:
      ACCEPT_EULA: Y
      SA_PASSWORD: DevPassword1!
```

### 5d. Archive Legacy Code
- `ScheduledTask/` PowerShell scripts replaced by EventBridge — document or archive
- `csharp/MaxPainAPI/` import-only mode — document its role clearly

---

## Implementation Order

| Phase | Items | Effort |
|---|---|---|
| **Quick wins** | 2d (sidebar links for Glossary/Candlestick), 3d (self-host FA) | 1 day |
| **Phase 1** | 1a–1f (Home page redesign) | 3–5 days |
| **Phase 2** | 2a–2c (Blog redesign) | 3–4 days |
| **Phase 3** | 3b (lazy loading), 3e (caching headers), 3f (images) | 1 week |
| **Phase 4** | 3c (CF Functions), 4c (edge meta description), 4d (sitemap auto) | 1 week |
| **Phase 5** | 3a (standalone components), 3g (Chart.js), 3h (admin auth) | ongoing |

---

*Created: 2026-04-28 | Updated: 2026-04-28 to reflect PR #76 completions*
*Based on analysis of: github.com/dshipe/maximum-pain.com and https://maximum-pain.com*
