# CLAUDE.md — maximum-pain.com Codebase Guide

> This file helps AI assistants (Claude, Copilot, etc.) understand the architecture, conventions, and quirks of this codebase before making changes.

---

## What This Project Is

**maximum-pain.com** is a stock options analytics website built around the concept of "max pain" — the strike price at which the greatest number of options expire worthless, causing maximum financial loss to option buyers. The site provides:

- Max pain calculation per ticker & expiration date
- Open Interest and Volume charting (server-side images + Google Charts candlesticks)
- Greeks, IV (Implied Volatility), straddle, spread analysis
- A daily stock screener (Cup-with-Handle, breakout patterns)
- Market direction analysis
- Glossary of options terms
- A blog and email subscription system
- CSV download of option chain data

Live site: [https://maximum-pain.com](https://maximum-pain.com)

---

## Tech Stack

| Layer | Technology |
|---|---|
| **Frontend** | Angular 17, Bootstrap 5, TypeScript, SCSS |
| **Backend API** | AWS Lambda (C# / .NET 8) via Lambda Function URL |
| **Legacy API** | ASP.NET Core MVC (MaxPainAPI — import-only mode, not in prod UI) |
| **Database** | SQL Server (two instances: AWS + Home) |
| **Data Source** | Charles Schwab API (OAuth2, option chains) |
| **Charting** | Server-side image charts (API) + Google Charts (candlestick) |
| **SEO — Title injection** | AWS Lambda@Edge (Node.js 20, origin-response event) |
| **SEO — Client** | Angular `SeoService` (Title, Meta, JSON-LD structured data) |
| **Email** | MailerLite (subscriber list management) |
| **SMS** | Twilio (alerts) |
| **Auth** | None (public-facing); admin routes unprotected by route guard |
| **Hosting** | AWS S3 + CloudFront (frontend), AWS Lambda (backend API) |
| **CI/CD** | GitHub Actions — two active pipelines (UI+Edge to S3/CloudFront, Lambda to AWS) |
| **Caching** | In-memory `OptionChainCacheService` (singleton, `ConcurrentDictionary`) |
| **Other** | Python (DailyScan, DailyFetch, MarketDirection, CupWithHandle pattern scanner) |

---

## Repository Structure

```
maximum-pain.com/
├── csharp/
│   ├── MaxPainUI/              # ASP.NET Core host for Angular SPA
│   │   └── ClientApp/          # Angular 17 frontend (the main app)
│   ├── MaxPainAPI/             # Legacy ASP.NET Core MVC API (import-only mode)
│   ├── MaxPainInfrastructure/  # Shared C# library: models, services, DB contexts
│   ├── MaxPainLambda/          # AWS Lambda function (current production API)
│   └── UnitTestProject1/       # xUnit tests for infrastructure services
├── lambda-edge/                # Lambda@Edge for server-side SEO title injection
│   ├── index.js                # Node.js 20 handler — rewrites <title> per route/ticker
│   ├── package.json
│   ├── function.zip            # Pre-built deploy artifact
│   └── README.md
├── python/
│   ├── DailyScan/              # Daily stock screener (Qullamaggie-style)
│   │   ├── DailyScanner.py
│   │   ├── DailyFetch.py
│   │   ├── Daily_ScanQuall.py
│   │   ├── MarketDirection.py
│   │   └── test_drawmap*.py
│   └── EC2StartStop.py         # EC2 instance scheduler
├── DBScripts/
│   ├── AWS/                    # SQL Server schemas for AWS DB
│   ├── Home/                   # SQL Server schemas for Home DB
│   └── Performance/            # DBA maintenance scripts
├── ScheduledTask/              # PowerShell import/email scripts
├── docs/                       # Planning and implementation docs (this folder)
├── .github/workflows/          # GitHub Actions CI/CD pipelines
└── maxpain-import.py           # Python data import script
```

---

## Frontend (Angular 17 — `csharp/MaxPainUI/ClientApp/src/app/`)

### Angular Version
**Angular 17** — upgraded from 13 in PR #76. Uses the new `@angular/build` esbuild-based builder. Still uses NgModules (standalone component migration pending).

### Key Components

| Component | Route | Purpose |
|---|---|---|
| `HomeComponent` | `/` | Landing page with blog card grid + AdSense |
| `OptionsComponent` | `/options/:id` | Main options view: OI chart, Volume chart, Max Pain table, Straddle |
| `MaxpainComponent` | (child) | Raw max pain table (calls/puts/strike/total/diff) |
| `StackedComponent` | `/stacked/:id` | Stacked OI chart (calls + puts combined) |
| `GreeksComponent` | `/greeks/:id` | Delta, Gamma, Theta, Vega per strike |
| `IvComponent` | `/iv/:id` | Implied volatility chart |
| `HistoryComponent` | `/history/:id` | Historical max pain by date |
| `MaxpainHistoryComponent` | `/maxpain-history/:id` | Historical max pain trend chart |
| `SpreadComponent` | `/spreads/:id` | Bull/bear spread analysis |
| `ScreenerComponent` | `/screener/:id` | Option screener (OI walls, most active) |
| `OutsideoiwallsComponent` | `/outside-oi-walls` | Stocks breaching OI resistance/support |
| `DailyScanComponent` | `/daily-scan` | Daily stock scan results (from Python) |
| `CupWithHandleComponent` | `/cup-with-handle` | Cup-with-handle pattern results |
| `MarketDirectionComponent` | `/market-direction` | Market breadth/direction indicator |
| `CandlestickComponent` | `/candlestick/:id` | **NEW (PR #76)** — Candlestick chart per ticker (Google Charts) |
| `ChartcandleComponent` | (child widget) | **NEW (PR #76)** — Responsive Google Charts candlestick widget |
| `GlossaryComponent` | `/glossary` | **NEW (PR #76)** — Options terms glossary with FAQPage schema |
| `BloghomeComponent` | `/blog` | Blog listing (card grid) |
| `BlogComponent` | `/blog/archive/:id` | Individual blog post (raw HTML rendered via `[innerHTML]`) |
| `SubscribeComponent` | (widget) | Email signup form (MailerLite) |
| `AdsenseComponent` | (widget) | Google AdSense wrapper |
| `SidebarComponent` | (layout) | Collapsible left-side navigation |

### Admin Components (no auth guard — obscurity only)
- `/admin/blogmanager` — Create/edit blog posts
- `/admin/email-stat` — Email delivery stats
- `/admin/import` — Manual data import trigger
- `/admin/import-log` — Import job history
- `/admin/message` — Internal messaging
- `/admin/hop` — URL hop tracking
- `/admin/usertweets` — Twitter management (legacy)

### Key Services

| Service | File | Purpose |
|---|---|---|
| `DataService` | `services/data.service.ts` | All HTTP calls to backend; gzip decompression via pako |
| `SeoService` | `services/seo.service.ts` | **NEW (PR #76)** — Dynamic title, meta, OG tags, Twitter cards, JSON-LD |
| `SitemapService` | `services/sitemap.service.ts` | **NEW (PR #76)** — Programmatic XML sitemap generator |
| `StateService` | `services/state.service.ts` | Shared state across components |
| `ThemeService` | `services/theme.service.ts` | Light/dark mode toggle |
| `SidebarService` | `services/sidebar.service.ts` | Sidebar open/close state |
| `UtilsService` | `services/utils.service.ts` | Debug mode, URL helpers |

### Frontend Conventions
- All API calls go through `DataService`. Base URL is `https://maximum-pain.com` (hardcoded — toggle for local dev).
- Response compression: API returns gzip'd JSON; client decompresses with `pako`.
- Charts: server-side PNG images (via API) + Google Charts (candlestick/daily).
- Blog content is raw HTML stored in DB, rendered with `[innerHTML]`.
- Routing: hash-free URLs; S3/CloudFront redirects all non-asset paths to `index.html`.
- Theme: `bootstrap` (light) or `@forevolve/bootstrap-dark` (dark).
- Font Awesome 6.6 loaded from CDN.
- `ng2-adsense` for AdSense.
- Google Charts loaded via `<script>` tag in `index.html`.

---

## SEO Architecture (PR #76)

### Two-Layer Approach

#### Layer 1: Lambda@Edge — Server-Side `<title>` Injection
`lambda-edge/index.js` — Node.js 20 Lambda function attached to CloudFront as an origin-response handler.

**Problem it solves:** S3-hosted SPAs serve a generic `index.html` for every URL. Search engines see `<title>Stock Option Max Pain</title>` for `/options/TSLA`, `/greeks/AAPL`, etc.

**Solution:**
```
Browser → CloudFront → S3 (returns generic index.html)
                ↑ origin-response event
          Lambda@Edge rewrites <title> based on path
Browser receives HTML with correct <title> already embedded
```

**Route title mapping (`ROUTE_TITLES`):**
| Path pattern | Title generated |
|---|---|
| `/options/AAPL` | `AAPL Max Pain` |
| `/stacked/TSLA` | `TSLA Stacked` |
| `/greeks/SPY` | `SPY Greeks` |
| `/iv/QQQ` | `QQQ Implied Volatility` |
| `/history/NVDA` | `NVDA Max Pain History` |
| `/spreads/MSFT` | `MSFT Spreads` |
| `/download-csv/AMZN` | `AMZN Download` |
| `/screener/openinterest` | `openinterest Option Screener` |

The function also embeds `TICKER_COMPANIES` (all S&P 500 + major tickers) for company name lookups.

**Infrastructure:** Lambda function `maximum-pain-edge-title`, us-east-1, CloudFront distribution `E7EPZSYP8I0`, origin-response event. Fully automated via CI/CD.

> ⚠️ **Important:** Lambda@Edge functions must be in `us-east-1` regardless of where S3 is. CloudFront requires a published version ARN (not `$LATEST`). The CI/CD pipeline handles both automatically.

#### Layer 2: Angular `SeoService` — Client-Side Meta Tags
`seo.service.ts` handles everything Lambda@Edge cannot: `<meta description>`, OG tags, Twitter cards, canonical URLs, JSON-LD structured data. Called in each component's `ngOnInit`.

**Methods:**
- `updateTitle(title)` — sets `<title>`
- `updateMetaTags({ title, description, keywords, url, image })` — sets all meta/OG/Twitter tags
- `addStructuredData(data)` — injects JSON-LD `<script>` into `<head>`

**Components using `SeoService`:** OptionsComponent, BlogComponent, GlossaryComponent, ScreenerComponent, CandlestickComponent.

#### SitemapService
`sitemap.service.ts` generates XML sitemaps programmatically. Priorities: homepage 1.0, ticker pages 0.9 (daily), static pages 0.8 (weekly), blog 0.7 (monthly).

---

## Backend (C# — `MaxPainInfrastructure` + `MaxPainLambda`)

### MaxPainInfrastructure — Services

| Service | Purpose |
|---|---|
| `SchwabService` | OAuth2 token management + option chain fetching from Charles Schwab API |
| `FinImportService` | Parses and imports raw option chain data. Uses `OptionChainCacheService`. |
| `OptionChainCacheService` | **NEW (PR #76)** — `ConcurrentDictionary<char, List<ImportStaging>>`. Singleton; persists across Lambda invocations within same container. |
| `CalculationService` | Max pain calculation, straddle building, spread computation |
| `ChartHelper` | **Moved (PR #76)** from `MaxPainChart` → `MaxPainInfrastructure/Code/` |
| `ChartService` | Builds `ChartInfo` objects for rendering |
| `HistoryService` | Historical option data queries |
| `FinDataService` | Serves transformed option data to API |
| `EmailService` | Transactional email |
| `MailerLiteService` | Subscriber list via MailerLite API |
| `SMSService` | Twilio SMS |
| `SecretService` | Reads API credentials from `Secret` SQL table |
| `UrlShortService` | URL shortening |
| `LoggerService` | Structured logging to SQL Server |
| `DateService` | Market calendar, trading day calculations |

### OptionChainCacheService — Import Flow
```
IO_PreProcess()      → Clear cache
IO_ProcessChar('A')  → MISS → fetch Schwab API → cache result
IO_ProcessChar('A')  → HIT  → skip API call, use cached data
IO_PostProcess()     → log stats → clear cache
```
**Log markers:** `cache HIT character=A count=123` / `cache MISS character=A millisecond=5432`

### Database

| DB | Connection | Contents |
|---|---|---|
| AWS DB | `AWSConnection` | Option chains, import logs, blog, email, settings, secrets |
| Home DB | `HomeConnection` | Historical OHLCV, staging, pattern scan results |

**New DB objects (PR #76):**
- `VIEW_vwDaily` / `VIEW_vwDaily2` — Daily OHLCV for candlestick charts
- `VIEW_vwHistoricalStockQuote` — Historical stock quotes
- `SP_spHistoricalOptionQuotePostFromStaging` — Updated import staging SP
- `SP_spImportStagingPost` — New staging post SP

**Secret management:** All API credentials in the `Secret` SQL table. `SecretService` reads at runtime. Not in env vars or config files.

---

## CI/CD Pipelines

### `CICD-S3-MaxPainUI-Edge.yml` — Frontend + Lambda@Edge (Active)
Trigger: push to `lamdba` branch (**note: intentional typo — do not rename the branch**)

Steps:
1. `npm ci` → Angular 17 production build (esbuild)
2. S3 sync → `maxpain-ui-static-site`
3. Create/update IAM role `LambdaEdgeTitleRole`
4. Deploy `lambda-edge/index.js` as `maximum-pain-edge-title` (us-east-1)
5. Publish new Lambda version
6. Associate version with CloudFront `E7EPZSYP8I0` at origin-response
7. CloudFront invalidation `/*`

### `CICD-Lambda.yml` — Backend API (Active)
Trigger: push to `lambda` branch
Steps: .NET 8 publish → zip → S3 → Lambda update (`MaxPainLambda`)

### `CICD-S3-MaxPainUI_CreateCloudFront.yml` — One-time infra creation
Creates the CloudFront distribution from scratch. Run once.

---

## Known Issues / Tech Debt

1. **Admin routes unprotected** — `/admin/*` is public, obscurity-only.
2. **Blog HTML is raw** — No sanitization; XSS risk if blog manager is compromised.
3. **Hardcoded `domainUrl`** in `data.service.ts` — Requires comment-toggle for local dev.
4. **Two databases** — Home + AWS split adds operational complexity.
5. **Secrets in DB** — Non-standard; AWS Secrets Manager would be safer.
6. **Font Awesome from CDN** — Third-party DNS lookup; self-hosting is faster.
7. **No full SSR** — Lambda@Edge handles `<title>` only. Full Angular Universal would serve complete HTML (all meta tags) without client JS.
8. **`relativeLinkResolution: 'legacy'`** — Deprecated router option in `app.module.ts`; clean up.
9. **Lambda@Edge cold start** — Adds ~200–400ms on cache miss. CloudFront Functions (lighter, sub-ms) could replace it for simple title rewriting.
10. **`CandlestickComponent` and `GlossaryComponent`** not in sidebar navigation yet.
11. **`lamdba` branch name typo** — Intentional; do not rename.

---

## Local Development

### Frontend
```bash
cd csharp/MaxPainUI/ClientApp
npm ci
ng serve   # http://localhost:4200
# Comment-swap domainUrl in data.service.ts to point at local API
```

### Backend
```bash
cd csharp/MaxPainLambda
dotnet run
```

### Lambda@Edge (test)
```bash
cd lambda-edge
node -e "const h=require('./index'); h.handler({Records:[{cf:{request:{uri:'/options/AAPL'},response:{headers:{'content-type':[{value:'text/html'}]},body:'<html><head><title>X</title></head></html>',status:'200'}}}]}, {}, (e,r)=>console.log(r.body))"
```

---

*Generated: 2026-04-28 | Updated: 2026-04-28 to reflect PR #76 (Angular 17, Lambda@Edge, SeoService, CandlestickComponent, GlossaryComponent, OptionChainCacheService)*
