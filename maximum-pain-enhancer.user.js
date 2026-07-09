// ==UserScript==
// @name         Maximum-Pain Ticker Enhancer
// @namespace    https://maximum-pain.com
// @version      2.0
// @description  Live Yahoo Finance autocomplete, company names, recent history, and quick-picks
// @match        https://maximum-pain.com/options/*
// @match        https://maximum-pain.com/stacked*
// @match        https://maximum-pain.com/greeks*
// @match        https://maximum-pain.com/iv*
// @grant        GM_xmlhttpRequest
// @connect      query1.finance.yahoo.com
// ==/UserScript==

(function () {
  'use strict';

  // ── Static fallback — used for badge on page load + quick-pick labels ──────
  const STATIC = {
    AAPL:'Apple', MSFT:'Microsoft', NVDA:'NVIDIA', AMZN:'Amazon', GOOGL:'Alphabet',
    META:'Meta', TSLA:'Tesla', AVGO:'Broadcom', JPM:'JPMorgan', V:'Visa',
    MA:'Mastercard', COST:'Costco', NFLX:'Netflix', AMD:'AMD', CRM:'Salesforce',
    QCOM:'Qualcomm', GE:'GE Aerospace', DIS:'Disney', CRWD:'CrowdStrike',
    PLTR:'Palantir', UBER:'Uber', COIN:'Coinbase', MU:'Micron', STX:'Seagate',
    WDC:'Western Digital', CIEN:'Ciena', GEV:'GE Vernova', VRT:'Vertiv',
    TER:'Teradyne', KEYS:'Keysight', SPY:'S&P 500 ETF', QQQ:'Nasdaq-100 ETF',
  };

  const QUICK_PICKS = [
    'NVDA','TSLA','AAPL','MSFT','AMZN','META','SPY','QQQ',
    'AMD','PLTR','COIN','CRWD','MU','STX',
  ];

  const RECENT_KEY = 'mp_recent_tickers';
  const MAX_RECENT = 8;
  const YAHOO_URL  = 'https://query1.finance.yahoo.com/v1/finance/search' +
                     '?quotesCount=8&newsCount=0&enableFuzzyQuery=false&q=';

  function getRecent() {
    try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); }
    catch { return []; }
  }

  function saveRecent(ticker) {
    let r = getRecent().filter(t => t !== ticker);
    r.unshift(ticker);
    localStorage.setItem(RECENT_KEY, JSON.stringify(r.slice(0, MAX_RECENT)));
  }

  function navigate(ticker) {
    if (!ticker) return;
    ticker = ticker.toUpperCase().trim();
    saveRecent(ticker);
    window.location.href = '/options/' + ticker;
  }

  // ── Live Yahoo Finance search via GM_xmlhttpRequest (bypasses CORS) ────────
  function yahooSearch(query, callback) {
    GM_xmlhttpRequest({
      method: 'GET',
      url: YAHOO_URL + encodeURIComponent(query),
      headers: { 'Accept': 'application/json' },
      onload: res => {
        try {
          const data = JSON.parse(res.responseText);
          const quotes = (data.quotes || [])
            .filter(q => q.quoteType === 'EQUITY' || q.quoteType === 'ETF')
            .map(q => ({ sym: q.symbol, name: q.shortname || q.longname || '' }));
          callback(quotes);
        } catch { callback([]); }
      },
      onerror: () => callback([]),
    });
  }

  // ── Debounce helper ────────────────────────────────────────────────────────
  function debounce(fn, ms) {
    let timer;
    return (...args) => { clearTimeout(timer); timer = setTimeout(() => fn(...args), ms); };
  }

  // ── Wait for Angular to render the input ──────────────────────────────────
  function waitForInput(cb, tries = 0) {
    const input = document.querySelector('input[formcontrolname="formTicker"]');
    if (input) { cb(input); return; }
    if (tries < 30) setTimeout(() => waitForInput(cb, tries + 1), 300);
  }

  waitForInput(function (input) {
    const container = input.closest('.input-group') || input.parentElement;

    // ── Styles ────────────────────────────────────────────────────────────────
    const style = document.createElement('style');
    style.textContent = `
      .mp-wrap { position: relative; width: 100%; }

      .mp-dropdown {
        position: absolute; top: calc(100% + 4px); left: 0; right: 0; z-index: 9999;
        background: #fff; border: 1px solid #ddd; border-radius: 8px;
        box-shadow: 0 4px 16px rgba(0,0,0,.12);
        max-height: 300px; overflow-y: auto; display: none;
      }
      .mp-dropdown.open { display: block; }

      .mp-section { padding: 4px 12px; font-size: 11px; color: #999;
                    background: #f8f9fb; border-bottom: 1px solid #eee;
                    text-transform: uppercase; letter-spacing: .5px; }
      .mp-item { padding: 9px 14px; display: flex; justify-content: space-between;
                  align-items: center; font-size: 13px; cursor: pointer;
                  border-bottom: 1px solid #f5f5f5; }
      .mp-item:last-child { border-bottom: none; }
      .mp-item:hover, .mp-item.active { background: #eff6ff; }
      .mp-sym { font-weight: 700; color: #1d4ed8; }
      .mp-name { color: #888; font-size: 12px; max-width: 55%;
                  text-align: right; white-space: nowrap;
                  overflow: hidden; text-overflow: ellipsis; }
      .mp-loading { padding: 10px 14px; font-size: 12px; color: #aaa; font-style: italic; }

      .mp-badge { font-size: 12px; color: #2563eb; font-style: italic;
                  margin-top: 5px; min-height: 16px; padding-left: 2px; }

      .mp-quick { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 10px; }
      .mp-qbtn { padding: 3px 10px; font-size: 12px; font-weight: 600;
                  border: 1px solid #1d4ed8; color: #1d4ed8; background: #fff;
                  border-radius: 4px; cursor: pointer; transition: background .12s, color .12s; }
      .mp-qbtn:hover, .mp-qbtn.cur { background: #1d4ed8; color: #fff; }

      .mp-recent { margin-top: 8px; }
      .mp-rlabel { font-size: 11px; color: #aaa; text-transform: uppercase;
                    letter-spacing: .5px; margin-bottom: 4px; }
      .mp-rpills { display: flex; flex-wrap: wrap; gap: 4px; }
      .mp-rpill { padding: 2px 9px; font-size: 12px; font-weight: 600;
                  border-radius: 12px; cursor: pointer;
                  background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }
      .mp-rpill:hover { background: #dbeafe; }
    `;
    document.head.appendChild(style);

    // ── Wrap + badge ──────────────────────────────────────────────────────────
    const wrap = document.createElement('div');
    wrap.className = 'mp-wrap';
    container.parentNode.insertBefore(wrap, container);
    wrap.appendChild(container);

    const badge = document.createElement('div');
    badge.className = 'mp-badge';
    const curTicker = window.location.pathname.split('/').pop().toUpperCase();
    badge.textContent = STATIC[curTicker] || '';
    if (!badge.textContent) {
      // fetch company name for current ticker if not in static list
      yahooSearch(curTicker, results => {
        const match = results.find(r => r.sym === curTicker);
        if (match) badge.textContent = match.name;
      });
    }
    wrap.appendChild(badge);

    // ── Dropdown ──────────────────────────────────────────────────────────────
    const dropdown = document.createElement('div');
    dropdown.className = 'mp-dropdown';
    wrap.appendChild(dropdown);

    let activeIdx = -1;
    function getItems() { return dropdown.querySelectorAll('.mp-item'); }
    function closeDropdown() { dropdown.classList.remove('open'); activeIdx = -1; }

    function addItem(sym, name) {
      const item = document.createElement('div');
      item.className = 'mp-item';
      item.innerHTML = `<span class="mp-sym">${sym}</span><span class="mp-name">${name}</span>`;
      item.addEventListener('mousedown', e => { e.preventDefault(); navigate(sym); });
      dropdown.appendChild(item);
    }

    function showRecent() {
      dropdown.innerHTML = '';
      const recent = getRecent();
      if (!recent.length) { dropdown.classList.remove('open'); return; }
      const sec = document.createElement('div');
      sec.className = 'mp-section'; sec.textContent = 'Recent';
      dropdown.appendChild(sec);
      recent.forEach(t => addItem(t, STATIC[t] || ''));
      dropdown.classList.add('open');
    }

    function showLoading() {
      dropdown.innerHTML = '<div class="mp-loading">Searching...</div>';
      dropdown.classList.add('open');
    }

    function showResults(results) {
      dropdown.innerHTML = '';
      if (!results.length) {
        dropdown.innerHTML = '<div class="mp-loading">No matches — press Enter to search</div>';
        dropdown.classList.add('open');
        return;
      }
      results.forEach(r => addItem(r.sym, r.name));
      dropdown.classList.add('open');
      activeIdx = -1;
    }

    // ── Live search with debounce ─────────────────────────────────────────────
    const doSearch = debounce(query => {
      if (!query) { showRecent(); return; }
      showLoading();
      yahooSearch(query, results => {
        // update badge with first exact match
        const exact = results.find(r => r.sym === query.toUpperCase());
        if (exact) badge.textContent = exact.name;
        showResults(results);
      });
    }, 300);

    // ── Input handlers ────────────────────────────────────────────────────────
    input.addEventListener('input', () => {
      const v = input.value.trim();
      badge.textContent = STATIC[v.toUpperCase()] || badge.textContent;
      doSearch(v);
    });

    input.addEventListener('focus', () => {
      if (!input.value.trim()) showRecent(); else doSearch(input.value.trim());
    });

    input.addEventListener('blur', () => setTimeout(closeDropdown, 150));

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
        e.preventDefault(); e.stopPropagation();
        if (activeIdx >= 0 && items[activeIdx]) {
          const sym = items[activeIdx].querySelector('.mp-sym')?.textContent;
          if (sym) { navigate(sym); return; }
        }
        navigate(input.value.trim());
      } else if (e.key === 'Escape') {
        closeDropdown();
      }
    });

    // ── Search button: one labeled button replacing two icon buttons ──────────
    const btns = container.querySelectorAll('.input-group-append button');
    if (btns.length >= 2) {
      btns[0].closest('.input-group-append').style.display = 'none';
      const searchBtn = btns[1];
      searchBtn.innerHTML = 'Search';
      Object.assign(searchBtn.style, {
        display: 'flex', alignItems: 'center',
        padding: '0 20px', height: '100%',
        borderRadius: '0 8px 8px 0',
        fontSize: '15px', fontWeight: '500',
        background: '#1d4ed8', color: '#fff',
        border: 'none', cursor: 'pointer',
        whiteSpace: 'nowrap', transition: 'background 0.15s',
      });
      searchBtn.addEventListener('mouseenter', () => searchBtn.style.background = '#1e40af');
      searchBtn.addEventListener('mouseleave', () => searchBtn.style.background = '#1d4ed8');
      input.style.borderRadius = '8px 0 0 8px';
      input.style.borderRight = 'none';
    }

    // ── Quick picks ───────────────────────────────────────────────────────────
    const qpWrap = document.createElement('div');
    qpWrap.className = 'mp-quick';
    QUICK_PICKS.forEach(sym => {
      const btn = document.createElement('button');
      btn.className = 'mp-qbtn' + (sym === curTicker ? ' cur' : '');
      btn.textContent = sym;
      btn.addEventListener('click', () => navigate(sym));
      qpWrap.appendChild(btn);
    });
    wrap.appendChild(qpWrap);

    // ── Recent pills ──────────────────────────────────────────────────────────
    const recent = getRecent().filter(t => !QUICK_PICKS.includes(t));
    if (recent.length) {
      const rWrap = document.createElement('div');
      rWrap.className = 'mp-recent';
      const lbl = document.createElement('div');
      lbl.className = 'mp-rlabel'; lbl.textContent = 'Recent';
      rWrap.appendChild(lbl);
      const pills = document.createElement('div');
      pills.className = 'mp-rpills';
      recent.forEach(t => {
        const p = document.createElement('span');
        p.className = 'mp-rpill'; p.textContent = t;
        p.title = STATIC[t] || t;
        p.addEventListener('click', () => navigate(t));
        pills.appendChild(p);
      });
      rWrap.appendChild(pills);
      wrap.appendChild(rWrap);
    }
  });

})();
