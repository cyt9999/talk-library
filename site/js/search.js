/* ============================================================
   投資Talk君 — Client-Side Search & Filter
   ============================================================ */

var SearchFilter = (function () {
  'use strict';

  /* ----------------------------------------------------------
     State
  ---------------------------------------------------------- */

  var _allItems = [];        // Full index.json array
  var _allTags = [];         // Unique tags extracted
  var _allTickers = [];      // Unique tickers extracted
  var _activeTags = [];      // Currently selected tag filters
  var _activeTickers = [];   // Currently selected ticker filters
  var _searchQuery = '';     // Current search text
  var _sortMode = 'date-desc'; // Current sort mode
  var _debounceTimer = null;
  var _onFilterCallback = null;

  var DEBOUNCE_MS = 300;

  /* ----------------------------------------------------------
     Initialization
  ---------------------------------------------------------- */

  /**
   * Initialize the search/filter system.
   * @param {Array} items - The index.json data array
   * @param {Function} onFilter - Callback receiving the filtered array
   */
  function init(items, onFilter) {
    _allItems = items || [];
    _onFilterCallback = onFilter;

    // Extract unique tags across all items, respecting current language
    _extractFilters();

    // Render chip bars
    _renderTagChips();
    _renderTickerChips();

    // Bind search input and sort
    _bindSearchInput();
    _bindSortSelect();

    // Initial render with all items
    _applyFilters();
  }

  /**
   * Re-extract filter labels when language changes.
   */
  function refreshForLang() {
    _extractFilters();
    _renderTagChips();
    _renderTickerChips();
    _applyFilters();
  }

  /* ----------------------------------------------------------
     Filter Extraction
  ---------------------------------------------------------- */

  function _extractFilters() {
    var lang = TalkApp.getLang();
    var tagSet = {};
    var tickerSet = {};

    _allItems.forEach(function (item) {
      // Tags can come from the item's tags array (index.json uses flat tags array)
      var tags = item.tags || [];
      tags.forEach(function (t) {
        tagSet[t] = true;
      });

      // Tickers from the item's tickers array (index.json has flat string array)
      var tickers = item.tickers || [];
      tickers.forEach(function (tk) {
        if (typeof tk === 'string') {
          tickerSet[tk] = true;
        } else if (tk.symbol) {
          tickerSet[tk.symbol] = true;
        }
      });
    });

    _allTags = Object.keys(tagSet).sort();
    _allTickers = Object.keys(tickerSet).sort();
  }

  /* ----------------------------------------------------------
     Chip Rendering
  ---------------------------------------------------------- */

  function _renderTagChips() {
    var container = document.getElementById('tag-chips');
    if (!container) return;

    container.innerHTML = '';

    if (_allTags.length === 0) {
      container.parentElement.style.display = 'none';
      return;
    }
    container.parentElement.style.display = '';

    // Update label
    var labelEl = container.parentElement.querySelector('.filter-label');
    if (labelEl) labelEl.textContent = TalkApp.label('tagsLabel');

    _allTags.forEach(function (tag) {
      var chip = document.createElement('button');
      chip.className = 'chip';
      chip.setAttribute('type', 'button');
      chip.textContent = tag;
      chip.setAttribute('data-tag', tag);

      if (_activeTags.indexOf(tag) !== -1) {
        chip.classList.add('active');
      }

      chip.addEventListener('click', function () {
        _toggleTag(tag);
        chip.classList.toggle('active');
      });

      container.appendChild(chip);
    });
  }

  function _renderTickerChips() {
    var container = document.getElementById('ticker-chips');
    if (!container) return;

    container.innerHTML = '';

    if (_allTickers.length === 0) {
      container.parentElement.style.display = 'none';
      return;
    }
    container.parentElement.style.display = '';

    // Update label
    var labelEl = container.parentElement.querySelector('.filter-label');
    if (labelEl) labelEl.textContent = TalkApp.label('tickersLabel');

    _allTickers.forEach(function (ticker) {
      var chip = document.createElement('button');
      chip.className = 'chip chip-ticker';
      chip.setAttribute('type', 'button');
      chip.textContent = ticker;
      chip.setAttribute('data-ticker', ticker);

      if (_activeTickers.indexOf(ticker) !== -1) {
        chip.classList.add('active');
      }

      chip.addEventListener('click', function () {
        _toggleTicker(ticker);
        chip.classList.toggle('active');
      });

      container.appendChild(chip);
    });
  }

  /* ----------------------------------------------------------
     Search Input Binding
  ---------------------------------------------------------- */

  function _bindSearchInput() {
    var input = document.getElementById('search-input');
    var clearBtn = document.getElementById('search-clear');
    if (!input) return;

    // Update placeholder for current language
    input.setAttribute('placeholder', TalkApp.label('searchPlaceholder'));

    input.addEventListener('input', function () {
      _searchQuery = input.value.trim();

      // Show/hide clear button
      if (clearBtn) {
        if (_searchQuery.length > 0) {
          clearBtn.classList.add('visible');
        } else {
          clearBtn.classList.remove('visible');
        }
      }

      // Debounced filter
      if (_debounceTimer) clearTimeout(_debounceTimer);
      _debounceTimer = setTimeout(function () {
        _applyFilters();
      }, DEBOUNCE_MS);
    });

    if (clearBtn) {
      clearBtn.addEventListener('click', function () {
        input.value = '';
        _searchQuery = '';
        clearBtn.classList.remove('visible');
        _applyFilters();
        input.focus();
      });
    }
  }

  /* ----------------------------------------------------------
     Sort Select Binding
  ---------------------------------------------------------- */

  function _bindSortSelect() {
    var select = document.getElementById('sort-select');
    if (!select) return;

    select.addEventListener('change', function () {
      _sortMode = select.value;
      _applyFilters();
    });
  }

  /**
   * Update search placeholder text (called on lang change).
   */
  function updateSearchPlaceholder() {
    var input = document.getElementById('search-input');
    if (input) {
      input.setAttribute('placeholder', TalkApp.label('searchPlaceholder'));
    }
  }

  /* ----------------------------------------------------------
     Toggle Filters
  ---------------------------------------------------------- */

  function _toggleTag(tag) {
    var idx = _activeTags.indexOf(tag);
    if (idx === -1) {
      _activeTags.push(tag);
    } else {
      _activeTags.splice(idx, 1);
    }
    _applyFilters();
  }

  function _toggleTicker(ticker) {
    var idx = _activeTickers.indexOf(ticker);
    if (idx === -1) {
      _activeTickers.push(ticker);
    } else {
      _activeTickers.splice(idx, 1);
    }
    _applyFilters();
  }

  /* ----------------------------------------------------------
     Filter Logic
  ---------------------------------------------------------- */

  function _applyFilters() {
    var results = _allItems.filter(function (item) {
      // Search query filter
      if (_searchQuery) {
        var q = _searchQuery.toLowerCase();
        var title = (item.title || '').toLowerCase();
        var tags = (item.tags || []).join(' ').toLowerCase();
        var tickers = (item.tickers || []).map(function (t) {
          return typeof t === 'string' ? t : (t.symbol || '');
        }).join(' ').toLowerCase();

        var matchesSearch = title.indexOf(q) !== -1 ||
                            tags.indexOf(q) !== -1 ||
                            tickers.indexOf(q) !== -1;
        if (!matchesSearch) return false;
      }

      // Tag filter — item must have ALL active tags
      if (_activeTags.length > 0) {
        var itemTags = item.tags || [];
        var hasAllTags = _activeTags.every(function (t) {
          return itemTags.indexOf(t) !== -1;
        });
        if (!hasAllTags) return false;
      }

      // Ticker filter — item must have ANY active ticker
      if (_activeTickers.length > 0) {
        var itemTickers = (item.tickers || []).map(function (t) {
          return typeof t === 'string' ? t : (t.symbol || '');
        });
        var hasAnyTicker = _activeTickers.some(function (tk) {
          return itemTickers.indexOf(tk) !== -1;
        });
        if (!hasAnyTicker) return false;
      }

      return true;
    });

    // Sort results
    results.sort(function (a, b) {
      switch (_sortMode) {
        case 'date-asc':
          return (a.publishedAt || '').localeCompare(b.publishedAt || '');
        case 'duration-desc':
          return (b.duration || 0) - (a.duration || 0);
        case 'duration-asc':
          return (a.duration || 0) - (b.duration || 0);
        case 'date-desc':
        default:
          return (b.publishedAt || '').localeCompare(a.publishedAt || '');
      }
    });

    if (_onFilterCallback) {
      _onFilterCallback(results);
    }
  }

  /* ----------------------------------------------------------
     Clear All Filters
  ---------------------------------------------------------- */

  function clearAll() {
    _activeTags = [];
    _activeTickers = [];
    _searchQuery = '';

    var input = document.getElementById('search-input');
    if (input) input.value = '';

    var clearBtn = document.getElementById('search-clear');
    if (clearBtn) clearBtn.classList.remove('visible');

    // Re-render chips without active states
    _renderTagChips();
    _renderTickerChips();
    _applyFilters();
  }

  /* ----------------------------------------------------------
     Public API
  ---------------------------------------------------------- */

  return {
    init: init,
    refreshForLang: refreshForLang,
    updateSearchPlaceholder: updateSearchPlaceholder,
    clearAll: clearAll
  };
})();
