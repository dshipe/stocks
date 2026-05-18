// ==UserScript==
// @name         Maximum-Pain Ticker Enhancer
// @namespace    https://maximum-pain.com
// @version      1.2
// @description  Adds autocomplete, company names, recent history, and quick-picks to the ticker selector
// @match        https://maximum-pain.com/options/*
// @match        https://maximum-pain.com/stacked*
// @match        https://maximum-pain.com/greeks*
// @match        https://maximum-pain.com/iv*
// @grant        none
// ==/UserScript==

(function () {
  'use strict';

  // ── Ticker database (symbol -> company name) ───────────────────────────────
  const TICKERS = {
    AAPL:'Apple', MSFT:'Microsoft', NVDA:'NVIDIA', AMZN:'Amazon', GOOGL:'Alphabet A',
    GOOG:'Alphabet C', META:'Meta', TSLA:'Tesla', AVGO:'Broadcom', BRK:'Berkshire',
    LLY:'Eli Lilly', JPM:'JPMorgan', V:'Visa', UNH:'UnitedHealth', XOM:'ExxonMobil',
    MA:'Mastercard', COST:'Costco', HD:'Home Depot', PG:'Procter & Gamble', JNJ:'Johnson & Johnson',
    ABBV:'AbbVie', BAC:'Bank of America', NFLX:'Netflix', CRM:'Salesforce', WMT:'Walmart',
    MRK:'Merck', CVX:'Chevron', KO:'Coca-Cola', AMD:'AMD', ACN:'Accenture',
    PEP:'PepsiCo', LIN:'Linde', MCD:'McDonald\'s', TMO:'Thermo Fisher', ADBE:'Adobe',
    ABT:'Abbott', CSCO:'Cisco', ORCL:'Oracle', QCOM:'Qualcomm', INTU:'Intuit',
    GE:'GE Aerospace', DIS:'Disney', CAT:'Caterpillar', NOW:'ServiceNow', TXN:'Texas Instruments',
    IBM:'IBM', AMAT:'Applied Materials', SPGI:'S&P Global', GS:'Goldman Sachs', ISRG:'Intuitive Surgical',
    BKNG:'Booking', LRCX:'Lam Research', PANW:'Palo Alto Networks', KLAC:'KLA Corp',
    SNPS:'Synopsys', CDNS:'Cadence', AXP:'American Express', ADI:'Analog Devices',
    REGN:'Regeneron', PLD:'Prologis', CRWD:'CrowdStrike', DDOG:'Datadog', NET:'Cloudflare',
    ZS:'Zscaler', SNOW:'Snowflake', MDB:'MongoDB', TEAM:'Atlassian', VEEV:'Veeva',
    CELH:'Celsius', ENPH:'Enphase', AXON:'Axon', SMCI:'Super Micro', PLTR:'Palantir',
    UBER:'Uber', DASH:'DoorDash', ABNB:'Airbnb', SQ:'Block', COIN:'Coinbase',
    MELI:'MercadoLibre', SPOT:'Spotify', RBLX:'Roblox', TTD:'Trade Desk', ROKU:'Roku',
    APP:'Applovin', HIMS:'Hims & Hers', DUOL:'Duolingo', IBKR:'Interactive Brokers',
    TOST:'Toast', FRPT:'Freshpet', ELF:'e.l.f. Beauty', ONON:'On Running',
    PODD:'Insulet', IRTC:'iRhythm', TMDX:'TransMedics', POWL:'Powell Industries',
    KTOS:'Kratos Defense', CACI:'CACI International', SAIC:'SAIC', DRS:'Leonardo DRS',
    LDOS:'Leidos', BAH:'Booz Allen', BWXT:'BWX Technologies', OXY:'Occidental',
    DVN:'Devon Energy', FANG:'Diamondback Energy', MPC:'Marathon Petroleum',
    VLO:'Valero', PSX:'Phillips 66', SLB:'Schlumberger', HAL:'Halliburton',
    BKR:'Baker Hughes', SOFI:'SoFi', AFRM:'Affirm', UPST:'Upstart', HOOD:'Robinhood',
    NU:'Nu Holdings', PYPL:'PayPal', FIS:'Fidelity National', FI:'Fiserv',
    GPN:'Global Payments', AMP:'Ameriprise', MU:'Micron', STX:'Seagate',
    WDC:'Western Digital', SNDK:'SanDisk', CIEN:'Ciena', GEV:'GE Vernova',
    VRT:'Vertiv', FIX:'Comfort Systems', TER:'Teradyne', AMAT:'Applied Materials',
    LRCX:'Lam Research', KLAC:'KLA Corp', KEYS:'Keysight', COHR:'Coherent',
    SPY:'S&P 500 ETF', QQQ:'Nasdaq-100 ETF', IWM:'Russell 2000 ETF',
    GLD:'Gold ETF', TLT:'20yr Treasury ETF', VIX:'VIX',
  };

  const QUICK_PICKS = [
    'NVDA','TSLA','AAPL','MSFT','AMZN','META','SPY','QQQ',
    'AMD','PLTR','COIN','CRWD','MU','STX',
  ];

  const RECENT_KEY = 'mp_recent_tickers';
  const MAX_RECENT = 8;

  function getRecent() {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); }
    catch { return []; }
  }

  function saveRecent(ticker) {
    let recent = getRecent().filter(t => t !== ticker);
    recent.unshift(ticker);
    recent = recent.slice(0, MAX_RECENT);
    localStorage.setItem(RECENT_KEY, JSON.stringify(recent));
  }

  function navigate(ticker) {
    if (!ticker) return;
    ticker = ticker.toUpperCase().trim();
    saveRecent(ticker);
    window.location.href = '/options/' + ticker;
  }

  // ── Wait for Angular to render the input ─────────────────────────────────
  function waitForInput(cb, tries = 0) {
    const input = document.querySelector('input[formcontrolname="formTicker"]');
    if (input) { cb(input); return; }
    if (tries < 30) setTimeout(() => waitForInput(cb, tries + 1), 300);
  }

  waitForInput(function (input) {
    const container = input.closest('.input-group') || input.parentElement;

    // ── Inject styles ──────────────────────────────────────────────────────
    const style = document.createElement('style');
    style.textContent = `
      .mp-enhancer-wrap { position: relative; width: 100%; }

      .mp-autocomplete {
        position: absolute; top: calc(100% + 4px); left: 0; right: 0;
        background: #fff; border: 1px solid #ccc; border-radius: 6px;
        box-shadow: 0 4px 16px rgba(0,0,0,.15); z-index: 9999;
        max-height: 280px; overflow-y: auto; display: none;
      }
      .mp-autocomplete.open { display: block; }

      .mp-ac-item {
        padding: 8px 14px; cursor: pointer; display: flex;
        justify-content: space-between; align-items: center;
        font-size: 14px; border-bottom: 1px solid #f0f0f0;
      }
      .mp-ac-item:last-child { border-bottom: none; }
      .mp-ac-item:hover, .mp-ac-item.active { background: #eef4ff; }
      .mp-ac-sym { font-weight: 700; color: #1a56db; }
      .mp-ac-name { color: #666; font-size: 12px; max-width: 55%; text-align: right;
                    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      .mp-ac-section { padding: 4px 14px; font-size: 11px; color: #999;
                        background: #f8f8f8; border-bottom: 1px solid #eee;
                        text-transform: uppercase; letter-spacing: .5px; }

      .mp-company-badge {
        font-size: 12px; color: #555; margin-top: 4px; min-height: 16px;
        padding-left: 2px;
      }

      .mp-quick-picks { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }
      .mp-qp-btn {
        padding: 3px 10px; font-size: 12px; border-radius: 4px; cursor: pointer;
        border: 1px solid #1a56db; color: #1a56db; background: #fff;
        transition: background .15s, color .15s; font-weight: 600;
      }
      .mp-qp-btn:hover { background: #1a56db; color: #fff; }

      .mp-recent-wrap { margin-top: 8px; }
      .mp-recent-label { font-size: 11px; color: #999; margin-bottom: 4px;
                          text-transform: uppercase; letter-spacing: .5px; }
      .mp-recent-pills { display: flex; flex-wrap: wrap; gap: 5px; }
      .mp-recent-pill {
        padding: 2px 9px; font-size: 12px; border-radius: 12px; cursor: pointer;
        background: #f0f4ff; color: #1a56db; border: 1px solid #c7d9ff;
        font-weight: 600;
      }
      .mp-recent-pill:hover { background: #dce8ff; }
    `;
    document.head.appendChild(style);

    // ── Wrap the input group ───────────────────────────────────────────────
    const wrap = document.createElement('div');
    wrap.className = 'mp-enhancer-wrap';
    container.parentNode.insertBefore(wrap, container);
    wrap.appendChild(container);

    // ── Company name badge ────────────────────────────────────────────────
    const badge = document.createElement('div');
    badge.className = 'mp-company-badge';
    const currentTicker = window.location.pathname.split('/').pop().toUpperCase();
    badge.textContent = TICKERS[currentTicker] ? TICKERS[currentTicker] : '';
    wrap.appendChild(badge);

    // ── Autocomplete dropdown ─────────────────────────────────────────────
    const dropdown = document.createElement('div');
    dropdown.className = 'mp-autocomplete';
    wrap.appendChild(dropdown);

    let activeIdx = -1;

    function getItems() { return dropdown.querySelectorAll('.mp-ac-item'); }

    function renderDropdown(query) {
      dropdown.innerHTML = '';
      activeIdx = -1;

      if (!query) {
        const recent = getRecent();
        if (recent.length) {
          const sec = document.createElement('div');
          sec.className = 'mp-ac-section'; sec.textContent = 'Recent';
          dropdown.appendChild(sec);
          recent.forEach(t => addItem(t, TICKERS[t] || '', dropdown));
        }
      } else {
        const q = query.toUpperCase();
        const matches = Object.entries(TICKERS)
          .filter(([sym, name]) =>
            sym.startsWith(q) || name.toUpperCase().includes(q)
          )
          .sort((a, b) => {
            const aExact = a[0].startsWith(q) ? 0 : 1;
            const bExact = b[0].startsWith(q) ? 0 : 1;
            return aExact - bExact || a[0].localeCompare(b[0]);
          })
          .slice(0, 12);

        if (!matches.length) {
          dropdown.innerHTML = '<div class="mp-ac-item" style="color:#999">No matches — press Enter to search</div>';
        } else {
          matches.forEach(([sym, name]) => addItem(sym, name, dropdown));
        }
      }

      dropdown.classList.toggle('open', dropdown.children.length > 0);
    }

    function addItem(sym, name, parent) {
      const item = document.createElement('div');
      item.className = 'mp-ac-item';
      item.innerHTML = `<span class="mp-ac-sym">${sym}</span><span class="mp-ac-name">${name}</span>`;
      item.addEventListener('mousedown', e => {
        e.preventDefault();
        navigate(sym);
      });
      parent.appendChild(item);
    }

    function closeDropdown() {
      dropdown.classList.remove('open');
      activeIdx = -1;
    }

    // ── Input event handlers ───────────────────────────────────────────────
    input.addEventListener('input', () => {
      const v = input.value.trim();
      badge.textContent = TICKERS[v.toUpperCase()] || '';
      renderDropdown(v);
    });

    input.addEventListener('focus', () => {
      renderDropdown(input.value.trim());
    });

    input.addEventListener('blur', () => {
      setTimeout(closeDropdown, 150);
    });

    input.addEventListener('keydown', e => {
      const items = getItems();
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        activeIdx = Math.min(activeIdx + 1, items.length - 1);
        items.forEach((el, i) => el.classList.toggle('active', i === activeIdx));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        activeIdx = Math.max(activeIdx - 1, 0);
        items.forEach((el, i) => el.classList.toggle('active', i === activeIdx));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        e.stopPropagation();
        if (activeIdx >= 0 && items[activeIdx]) {
          const sym = items[activeIdx].querySelector('.mp-ac-sym')?.textContent;
          if (sym) { navigate(sym); return; }
        }
        navigate(input.value.trim());
      } else if (e.key === 'Escape') {
        closeDropdown();
      }
    });

    // ── Search button: collapse the two icon buttons into one labeled button ─
    const buttons = container.querySelectorAll('.input-group-append button');
    if (buttons.length >= 2) {
      buttons[0].closest('.input-group-append').style.display = 'none'; // hide green check
      const searchBtn = buttons[1];
      searchBtn.innerHTML = 'Search';
      Object.assign(searchBtn.style, {
        display: 'flex', alignItems: 'center',
        padding: '0 20px', height: '100%',
        borderRadius: '0 8px 8px 0',
        fontSize: '15px', fontWeight: '500',
        background: '#1a56db', color: '#fff',
        border: 'none', cursor: 'pointer',
        whiteSpace: 'nowrap', transition: 'background 0.15s',
      });
      searchBtn.addEventListener('mouseenter', () => searchBtn.style.background = '#1341b8');
      searchBtn.addEventListener('mouseleave', () => searchBtn.style.background = '#1a56db');
      input.style.borderRadius = '8px 0 0 8px';
      input.style.borderRight = 'none';
    }

    // ── Quick picks ────────────────────────────────────────────────────────
    const qpWrap = document.createElement('div');
    qpWrap.className = 'mp-quick-picks';
    QUICK_PICKS.forEach(sym => {
      const btn = document.createElement('button');
      btn.className = 'mp-qp-btn';
      btn.textContent = sym;
      if (sym === currentTicker) {
        btn.style.background = '#1a56db';
        btn.style.color = '#fff';
      }
      btn.addEventListener('click', () => navigate(sym));
      qpWrap.appendChild(btn);
    });
    wrap.appendChild(qpWrap);

    // ── Recent tickers ─────────────────────────────────────────────────────
    function renderRecent() {
      const existing = wrap.querySelector('.mp-recent-wrap');
      if (existing) existing.remove();
      const recent = getRecent().filter(t => !QUICK_PICKS.includes(t));
      if (!recent.length) return;
      const rWrap = document.createElement('div');
      rWrap.className = 'mp-recent-wrap';
      const label = document.createElement('div');
      label.className = 'mp-recent-label'; label.textContent = 'Recent';
      rWrap.appendChild(label);
      const pills = document.createElement('div');
      pills.className = 'mp-recent-pills';
      recent.forEach(t => {
        const pill = document.createElement('span');
        pill.className = 'mp-recent-pill';
        pill.textContent = t;
        pill.title = TICKERS[t] || t;
        pill.addEventListener('click', () => navigate(t));
        pills.appendChild(pill);
      });
      rWrap.appendChild(pills);
      wrap.appendChild(rWrap);
    }
    renderRecent();
  });

})();
