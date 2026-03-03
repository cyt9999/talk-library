/* ============================================================
   投資Talk君 — Ticker Search Page Module
   ============================================================ */

var TickerPage = (function () {
  'use strict';

  /* ----------------------------------------------------------
     State
  ---------------------------------------------------------- */

  var _indexData = [];           // Full index.json array
  var _tickerMap = {};           // { "NVDA": [{ indexEntry, tickerInfo }...] }
  var _summaryCache = {};        // { "date-id": summaryData }
  var _allSymbols = [];          // Sorted unique symbols
  var _highlightIdx = -1;       // Autocomplete highlight index
  var _currentSymbol = null;     // Currently displayed symbol
  var _initialized = false;

  /* ----------------------------------------------------------
     Initialization
  ---------------------------------------------------------- */

  function init() {
    TalkApp.fetchIndex()
      .then(function (data) {
        _indexData = data;
        _buildTickerMap();

        var loader = document.getElementById('page-loader');
        if (loader) loader.style.display = 'none';

        _renderPopularTickers();
        _bindSearch();

        _initialized = true;

        // Check for deep link
        var symbol = TalkApp.getQueryParam('symbol');
        if (symbol) {
          symbol = symbol.toUpperCase();
          var input = document.getElementById('ticker-search-input');
          if (input) input.value = symbol;
          _selectTicker(symbol);
        }
      })
      .catch(function (err) {
        console.error('[ticker] Failed to load index.json:', err);
        var loader = document.getElementById('page-loader');
        if (loader) loader.style.display = 'none';
        _renderError();
      });
  }

  /* ----------------------------------------------------------
     Build Ticker Map
  ---------------------------------------------------------- */

  function _buildTickerMap() {
    _tickerMap = {};

    _indexData.forEach(function (item) {
      var tickers = item.tickers || [];
      tickers.forEach(function (tk) {
        var sym = typeof tk === 'string' ? tk : (tk.symbol || '');
        if (!sym) return;
        sym = sym.toUpperCase();

        if (!_tickerMap[sym]) {
          _tickerMap[sym] = [];
        }
        _tickerMap[sym].push({
          indexEntry: item,
          tickerSymbol: sym
        });
      });
    });

    _allSymbols = Object.keys(_tickerMap).sort();
  }

  /* ----------------------------------------------------------
     Popular Tickers
  ---------------------------------------------------------- */

  function _renderPopularTickers() {
    var container = document.getElementById('popular-chips');
    var labelEl = document.getElementById('popular-label');
    if (!container) return;

    if (labelEl) labelEl.textContent = TalkApp.label('popularTickers');

    // Sort by mention count descending, take top 12
    var sorted = _allSymbols.slice().sort(function (a, b) {
      return _tickerMap[b].length - _tickerMap[a].length;
    });
    var top = sorted.slice(0, 12);

    container.innerHTML = '';
    top.forEach(function (sym) {
      var count = _tickerMap[sym].length;
      var chip = document.createElement('button');
      chip.className = 'popular-chip';
      chip.setAttribute('type', 'button');
      chip.innerHTML = TalkApp.escapeHtml(sym) +
        ' <span class="popular-chip-count">' + count + '</span>';
      chip.addEventListener('click', function () {
        var input = document.getElementById('ticker-search-input');
        if (input) input.value = sym;
        _selectTicker(sym);
        _hideAutocomplete();
        _updateClearBtn(sym);
      });
      container.appendChild(chip);
    });
  }

  /* ----------------------------------------------------------
     Search & Autocomplete
  ---------------------------------------------------------- */

  function _bindSearch() {
    var input = document.getElementById('ticker-search-input');
    var clearBtn = document.getElementById('ticker-search-clear');
    if (!input) return;

    input.setAttribute('placeholder', TalkApp.label('tickerSearchPlaceholder'));

    input.addEventListener('input', function () {
      var val = input.value.trim().toUpperCase();
      _updateClearBtn(val);
      if (val.length === 0) {
        _hideAutocomplete();
        _showPopular();
        _clearResults();
        return;
      }
      _showAutocomplete(val);
    });

    input.addEventListener('keydown', function (e) {
      var ac = document.getElementById('ticker-autocomplete');
      var items = ac ? ac.querySelectorAll('.ticker-ac-item') : [];
      if (items.length === 0) return;

      if (e.key === 'ArrowDown') {
        e.preventDefault();
        _highlightIdx = Math.min(_highlightIdx + 1, items.length - 1);
        _updateHighlight(items);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        _highlightIdx = Math.max(_highlightIdx - 1, 0);
        _updateHighlight(items);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (_highlightIdx >= 0 && _highlightIdx < items.length) {
          var sym = items[_highlightIdx].getAttribute('data-symbol');
          if (sym) {
            input.value = sym;
            _selectTicker(sym);
            _hideAutocomplete();
            _updateClearBtn(sym);
          }
        } else {
          // Direct enter with typed text
          var val = input.value.trim().toUpperCase();
          if (val && _tickerMap[val]) {
            _selectTicker(val);
            _hideAutocomplete();
          }
        }
      } else if (e.key === 'Escape') {
        _hideAutocomplete();
      }
    });

    // Hide autocomplete on outside click
    document.addEventListener('click', function (e) {
      var container = document.querySelector('.ticker-search-container');
      if (container && !container.contains(e.target)) {
        _hideAutocomplete();
      }
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        input.value = '';
        _updateClearBtn('');
        _hideAutocomplete();
        _showPopular();
        _clearResults();
        input.focus();
        // Update URL
        _updateUrl(null);
      });
    }
  }

  function _updateClearBtn(val) {
    var clearBtn = document.getElementById('ticker-search-clear');
    if (!clearBtn) return;
    if (val && val.length > 0) {
      clearBtn.classList.add('visible');
    } else {
      clearBtn.classList.remove('visible');
    }
  }

  function _showAutocomplete(query) {
    var ac = document.getElementById('ticker-autocomplete');
    if (!ac) return;

    // Prefix match
    var matches = _allSymbols.filter(function (sym) {
      return sym.indexOf(query) === 0;
    });

    // Also include contains matches (lower priority)
    var containsMatches = _allSymbols.filter(function (sym) {
      return sym.indexOf(query) > 0;
    });

    var combined = matches.concat(containsMatches).slice(0, 8);

    if (combined.length === 0) {
      _hideAutocomplete();
      return;
    }

    _highlightIdx = -1;
    ac.innerHTML = '';

    combined.forEach(function (sym) {
      var count = _tickerMap[sym].length;
      var item = document.createElement('div');
      item.className = 'ticker-ac-item';
      item.setAttribute('data-symbol', sym);

      // Try to get a name from the first summary's ticker data
      var nameText = '';
      var entries = _tickerMap[sym];
      if (entries.length > 0) {
        var firstEntry = entries[0].indexEntry;
        var tickers = firstEntry.tickers || [];
        for (var i = 0; i < tickers.length; i++) {
          var tk = tickers[i];
          if (typeof tk === 'object' && tk.symbol && tk.symbol.toUpperCase() === sym && tk.name) {
            nameText = tk.name;
            break;
          }
        }
      }

      item.innerHTML =
        '<div>' +
          '<span class="ticker-ac-symbol">' + TalkApp.escapeHtml(sym) + '</span>' +
          (nameText ? '<span class="ticker-ac-name">' + TalkApp.escapeHtml(nameText) + '</span>' : '') +
        '</div>' +
        '<span class="ticker-ac-count">' + count + ' ' + TalkApp.label('videos') + '</span>';

      item.addEventListener('click', function () {
        var input = document.getElementById('ticker-search-input');
        if (input) input.value = sym;
        _selectTicker(sym);
        _hideAutocomplete();
        _updateClearBtn(sym);
      });

      ac.appendChild(item);
    });

    ac.classList.add('visible');
  }

  function _hideAutocomplete() {
    var ac = document.getElementById('ticker-autocomplete');
    if (ac) {
      ac.classList.remove('visible');
      ac.innerHTML = '';
    }
    _highlightIdx = -1;
  }

  function _updateHighlight(items) {
    items.forEach(function (item, i) {
      if (i === _highlightIdx) {
        item.classList.add('highlighted');
      } else {
        item.classList.remove('highlighted');
      }
    });
  }

  /* ----------------------------------------------------------
     Select & Display Ticker
  ---------------------------------------------------------- */

  function _selectTicker(symbol) {
    _currentSymbol = symbol;
    _hidePopular();
    _updateUrl(symbol);

    var entries = _tickerMap[symbol];
    if (!entries || entries.length === 0) {
      _renderNoResults();
      return;
    }

    // Fetch all relevant summaries to get full ticker data
    var promises = entries.map(function (entry) {
      var item = entry.indexEntry;
      var cacheKey = (item.publishedAt || '') + '-' + item.id;

      if (_summaryCache[cacheKey]) {
        return Promise.resolve(_summaryCache[cacheKey]);
      }

      return TalkApp.fetchSummary(item.id, item.publishedAt)
        .then(function (data) {
          _summaryCache[cacheKey] = data;
          return data;
        })
        .catch(function () {
          return null; // Graceful degradation
        });
    });

    Promise.all(promises).then(function (summaries) {
      _renderResults(symbol, entries, summaries);
    });
  }

  /* ----------------------------------------------------------
     Render Results
  ---------------------------------------------------------- */

  function _renderResults(symbol, entries, summaries) {
    var container = document.getElementById('ticker-results');
    if (!container) return;
    container.innerHTML = '';

    // Collect ticker info from summaries
    var lang = TalkApp.getLang();
    var mentionData = [];
    var sentimentCounts = { bullish: 0, bearish: 0, neutral: 0 };
    var tickerName = '';

    summaries.forEach(function (summary, idx) {
      if (!summary) return;

      var entry = entries[idx];
      var tickers = summary.tickers || [];
      var matched = null;

      for (var i = 0; i < tickers.length; i++) {
        if (tickers[i].symbol && tickers[i].symbol.toUpperCase() === symbol) {
          matched = tickers[i];
          break;
        }
      }

      if (matched) {
        if (!tickerName && matched.name) tickerName = matched.name;
        var sentiment = matched.sentiment || 'neutral';
        sentimentCounts[sentiment] = (sentimentCounts[sentiment] || 0) + 1;

        // Get key points from the summary that overlap with the ticker's mention time ranges
        var langData = summary.summary && summary.summary[lang] ? summary.summary[lang] : (summary.summary ? summary.summary['zh-Hant'] || summary.summary['zh-Hans'] : null);
        var allKeyPoints = (langData && langData.keyPoints) || [];
        var mentions = matched.mentions || [];

        // Find key points whose timestamp falls within any mention range
        // Use a generous buffer (+/- 120s) since key points may be slightly outside
        var relevantKeyPoints = [];
        allKeyPoints.forEach(function (kp) {
          var isRelevant = mentions.some(function (m) {
            return kp.timestamp >= (m.start - 120) && kp.timestamp <= (m.end + 120);
          });
          if (isRelevant) {
            relevantKeyPoints.push(kp);
          }
        });

        // If no key points matched the time range, fall back to all key points
        // (the whole video is about this ticker)
        if (relevantKeyPoints.length === 0 && allKeyPoints.length > 0) {
          relevantKeyPoints = allKeyPoints;
        }

        mentionData.push({
          summary: summary,
          indexEntry: entry.indexEntry,
          ticker: matched,
          sentiment: sentiment,
          keyPoints: relevantKeyPoints,
          mentions: mentions
        });
      }
    });

    var total = sentimentCounts.bullish + sentimentCounts.bearish + sentimentCounts.neutral;

    // === Header card ===
    var headerHtml = '<div class="ticker-result-header">';
    headerHtml += '<div class="ticker-result-symbol">' + TalkApp.escapeHtml(symbol) + '</div>';
    if (tickerName) {
      headerHtml += '<div class="ticker-result-name">' + TalkApp.escapeHtml(tickerName) + '</div>';
    }

    // Stats
    headerHtml += '<div class="ticker-result-stats">';
    headerHtml += '<div class="ticker-stat"><span class="ticker-stat-value">' + total + '</span> <span class="ticker-stat-label">' + TalkApp.label('videos') + '</span></div>';
    if (sentimentCounts.bullish > 0) {
      headerHtml += '<div class="ticker-stat"><span class="ticker-stat-value" style="color:var(--color-bullish)">' + sentimentCounts.bullish + '</span> <span class="ticker-stat-label">' + TalkApp.label('bullish') + '</span></div>';
    }
    if (sentimentCounts.bearish > 0) {
      headerHtml += '<div class="ticker-stat"><span class="ticker-stat-value" style="color:var(--color-bearish)">' + sentimentCounts.bearish + '</span> <span class="ticker-stat-label">' + TalkApp.label('bearish') + '</span></div>';
    }
    headerHtml += '</div>';

    // Sentiment bar
    if (total > 0) {
      var bPct = Math.round((sentimentCounts.bullish / total) * 100);
      var rPct = Math.round((sentimentCounts.bearish / total) * 100);
      var nPct = 100 - bPct - rPct;

      headerHtml += '<div class="sentiment-bar">';
      if (bPct > 0) headerHtml += '<div class="sentiment-bar-segment bullish" style="width:' + bPct + '%"></div>';
      if (rPct > 0) headerHtml += '<div class="sentiment-bar-segment bearish" style="width:' + rPct + '%"></div>';
      if (nPct > 0) headerHtml += '<div class="sentiment-bar-segment neutral" style="width:' + nPct + '%"></div>';
      headerHtml += '</div>';

      headerHtml += '<div class="sentiment-bar-legend">';
      if (sentimentCounts.bullish > 0) {
        headerHtml += '<span class="sentiment-legend-item"><span class="sentiment-legend-dot bullish"></span> ' + TalkApp.label('bullish') + '</span>';
      }
      if (sentimentCounts.bearish > 0) {
        headerHtml += '<span class="sentiment-legend-item"><span class="sentiment-legend-dot bearish"></span> ' + TalkApp.label('bearish') + '</span>';
      }
      if (sentimentCounts.neutral > 0) {
        headerHtml += '<span class="sentiment-legend-item"><span class="sentiment-legend-dot neutral"></span> ' + TalkApp.label('neutral') + '</span>';
      }
      headerHtml += '</div>';
    }

    headerHtml += '</div>';
    container.insertAdjacentHTML('beforeend', headerHtml);

    // === Mention cards ===
    // Sort by date descending
    mentionData.sort(function (a, b) {
      var dateA = a.indexEntry.publishedAt || '';
      var dateB = b.indexEntry.publishedAt || '';
      return dateB.localeCompare(dateA);
    });

    mentionData.forEach(function (m) {
      var cardHtml = '<div class="ticker-mention-card">';

      // Top row: date + sentiment
      cardHtml += '<div class="ticker-mention-top">';
      cardHtml += '<span class="ticker-mention-date">' + TalkApp.formatDate(m.indexEntry.publishedAt) + '</span>';
      cardHtml += '<span class="sentiment-badge ' + m.sentiment + '">' + TalkApp.label(m.sentiment) + '</span>';
      cardHtml += '</div>';

      // Title
      cardHtml += '<div class="ticker-mention-title">' + TalkApp.escapeHtml(m.indexEntry.title || '') + '</div>';

      // Full key points — Talk君's actual opinion
      if (m.keyPoints && m.keyPoints.length > 0) {
        cardHtml += '<div class="ticker-mention-keypoints">';
        m.keyPoints.forEach(function (kp) {
          cardHtml += '<div class="ticker-mention-kp">';
          cardHtml += '<div class="ticker-mention-kp-bullet"></div>';
          cardHtml += '<div class="ticker-mention-kp-text">' + TalkApp.escapeHtml(kp.text) + '</div>';
          cardHtml += '</div>';
        });
        cardHtml += '</div>';
      }

      // Link to summary
      var summaryUrl = 'summary.html?id=' + encodeURIComponent(m.indexEntry.id) + '&date=' + encodeURIComponent(m.indexEntry.publishedAt || '');
      cardHtml += '<a href="' + summaryUrl + '" class="ticker-mention-link">';
      cardHtml += TalkApp.label('viewSummary');
      cardHtml += ' <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>';
      cardHtml += '</a>';

      cardHtml += '</div>';
      container.insertAdjacentHTML('beforeend', cardHtml);
    });

    // Add nav spacer
    container.insertAdjacentHTML('beforeend', '<div class="nav-spacer"></div>');

    // Staggered reveal
    setTimeout(function () {
      TalkApp.revealElements('.ticker-result-header', 0);
      TalkApp.revealElements('.ticker-mention-card', 80);
    }, 50);
  }

  function _renderNoResults() {
    var container = document.getElementById('ticker-results');
    if (!container) return;
    container.innerHTML =
      '<div class="empty-state">' +
        '<svg class="empty-state-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
          '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>' +
          '<polyline points="16 7 22 7 22 13"/>' +
        '</svg>' +
        '<div class="empty-state-title">' + TalkApp.label('noTickerResults') + '</div>' +
        '<div class="empty-state-desc">' + TalkApp.label('noTickerResultsDesc') + '</div>' +
      '</div>';
  }

  function _renderError() {
    var container = document.getElementById('ticker-results');
    if (!container) return;
    container.innerHTML =
      '<div class="error-state">' +
        '<div class="error-state-title">' + TalkApp.label('loadError') + '</div>' +
        '<div class="error-state-desc">' + TalkApp.label('loadErrorDesc') + '</div>' +
        '<button class="retry-btn" onclick="location.reload()">' + TalkApp.label('retry') + '</button>' +
      '</div>';
  }

  function _clearResults() {
    var container = document.getElementById('ticker-results');
    if (container) container.innerHTML = '';
    _currentSymbol = null;
  }

  /* ----------------------------------------------------------
     Show/Hide Popular Section
  ---------------------------------------------------------- */

  function _showPopular() {
    var section = document.getElementById('popular-section');
    if (section) section.style.display = '';
  }

  function _hidePopular() {
    var section = document.getElementById('popular-section');
    if (section) section.style.display = 'none';
  }

  /* ----------------------------------------------------------
     URL Management
  ---------------------------------------------------------- */

  function _updateUrl(symbol) {
    if (symbol) {
      var newUrl = 'ticker.html?symbol=' + encodeURIComponent(symbol);
      history.replaceState(null, '', newUrl);
    } else {
      history.replaceState(null, '', 'ticker.html');
    }
  }

  /* ----------------------------------------------------------
     Language Change Handler
  ---------------------------------------------------------- */

  function onLangChanged() {
    if (!_initialized) return;

    // Update search placeholder
    var input = document.getElementById('ticker-search-input');
    if (input) input.setAttribute('placeholder', TalkApp.label('tickerSearchPlaceholder'));

    // Update popular label
    var labelEl = document.getElementById('popular-label');
    if (labelEl) labelEl.textContent = TalkApp.label('popularTickers');

    // Re-render current results if any
    if (_currentSymbol && _tickerMap[_currentSymbol]) {
      _selectTicker(_currentSymbol);
    }
  }

  /* ----------------------------------------------------------
     Public API
  ---------------------------------------------------------- */

  return {
    init: init,
    onLangChanged: onLangChanged
  };
})();
