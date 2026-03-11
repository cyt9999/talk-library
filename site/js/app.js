/* ============================================================
   投資Talk君 — Core Application Logic
   ============================================================ */

var TalkApp = (function () {
  'use strict';

  /* ----------------------------------------------------------
     Configuration
  ---------------------------------------------------------- */

  // API base URL for fetching video data from Railway API
  var API_BASE = (function () {
    var host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
      return 'http://localhost:8080';
    }
    var meta = document.querySelector('meta[name="api-base-url"]');
    if (meta && meta.content) {
      return meta.content;
    }
    return 'https://talk-ai-api-production.up.railway.app';
  })();

  // Data base path — kept for any remaining static data references
  var DATA_BASE = 'data/';

  var LANG_KEY = 'talkjun_lang';
  var DEFAULT_LANG = 'zh-Hant';

  /* ----------------------------------------------------------
     Language Management
  ---------------------------------------------------------- */

  function getLang() {
    try {
      var stored = localStorage.getItem(LANG_KEY);
      if (stored === 'zh-Hans' || stored === 'zh-Hant') return stored;
    } catch (e) { /* noop */ }
    return DEFAULT_LANG;
  }

  function setLang(lang) {
    try {
      localStorage.setItem(LANG_KEY, lang);
    } catch (e) { /* noop */ }
    window.dispatchEvent(new CustomEvent('lang-changed', { detail: { lang: lang } }));
  }

  function toggleLang() {
    var current = getLang();
    var next = current === 'zh-Hant' ? 'zh-Hans' : 'zh-Hant';
    setLang(next);
    return next;
  }

  /* ----------------------------------------------------------
     UI Labels (bilingual)
  ---------------------------------------------------------- */
  var UI_LABELS = {
    'zh-Hant': {
      searchPlaceholder: '搜尋影片標題、標籤、代號...',
      tagsLabel: '標籤',
      tickersLabel: '代號',
      keyPoints: '重點摘要',
      summary: '內容總結',
      tickers: '提及標的',
      mentionedAt: '提及時段',
      bookmarkAdd: '加入收藏',
      bookmarkRemove: '已收藏',
      bookmarksTitle: '我的收藏',
      bookmarksSubtitle: '已儲存的影片摘要',
      emptyBookmarks: '尚無收藏',
      emptyBookmarksDesc: '瀏覽摘要時點選收藏按鈕即可加入',
      noResults: '未找到結果',
      noResultsDesc: '請嘗試其他關鍵字或篩選條件',
      loadError: '載入失敗',
      loadErrorDesc: '請檢查網路連線後重試',
      retry: '重試',
      bullish: '看多',
      bearish: '看空',
      neutral: '中性',
      home: '首頁',
      bookmarks: '收藏',
      tickersNav: '標的',
      tickerSearchPlaceholder: '搜尋股票代號...',
      popularTickers: '熱門標的',
      videos: '部影片',
      noTickerResults: '未找到標的',
      noTickerResultsDesc: '請嘗試其他代號',
      viewSummary: '查看摘要',
      back: '返回',
      langHant: '繁體',
      langHans: '簡體',
      chatNav: 'AI問答',
      chatTitle: 'AI 問答',
      chatSubtitle: '根據Talk君影片內容回答',
      chatPlaceholder: '輸入你的投資問題...',
      chatSend: '發送',
      chatSuggestion1: 'Talk君最近分析了哪些股票？',
      chatSuggestion2: '半導體產業的最新觀點是什麼？',
      chatSuggestion3: '最近有什麼值得關注的投資趨勢？',
      chatSources: '參考來源',
      chatError: '無法連線至 AI 服務，請確認伺服器已啟動',
      chatThinking: '思考中...',
      chatWelcome: '你好！我是投資Talk君 AI 助手，可以根據Talk君的影片內容回答你的投資問題。',
      chatOffline: 'AI 服務目前離線，請稍後再試',
      chatRateLimit: '請求過於頻繁，請稍後再試',
      chatEmpty: '請輸入問題',
      sortLabel: '排序',
      sortDateDesc: '日期（新→舊）',
      sortDateAsc: '日期（舊→新）',
      sortDurationDesc: '時長（長→短）',
      sortDurationAsc: '時長（短→長）'
    },
    'zh-Hans': {
      searchPlaceholder: '搜索视频标题、标签、代号...',
      tagsLabel: '标签',
      tickersLabel: '代号',
      keyPoints: '重点摘要',
      summary: '内容总结',
      tickers: '提及标的',
      mentionedAt: '提及时段',
      bookmarkAdd: '加入收藏',
      bookmarkRemove: '已收藏',
      bookmarksTitle: '我的收藏',
      bookmarksSubtitle: '已保存的视频摘要',
      emptyBookmarks: '暂无收藏',
      emptyBookmarksDesc: '浏览摘要时点击收藏按钮即可加入',
      noResults: '未找到结果',
      noResultsDesc: '请尝试其他关键字或筛选条件',
      loadError: '加载失败',
      loadErrorDesc: '请检查网络连接后重试',
      retry: '重试',
      bullish: '看多',
      bearish: '看空',
      neutral: '中性',
      home: '首页',
      bookmarks: '收藏',
      tickersNav: '标的',
      tickerSearchPlaceholder: '搜索股票代号...',
      popularTickers: '热门标的',
      videos: '部视频',
      noTickerResults: '未找到标的',
      noTickerResultsDesc: '请尝试其他代号',
      viewSummary: '查看摘要',
      back: '返回',
      langHant: '繁体',
      langHans: '简体',
      chatNav: 'AI问答',
      chatTitle: 'AI 问答',
      chatSubtitle: '根据Talk君视频内容回答',
      chatPlaceholder: '输入你的投资问题...',
      chatSend: '发送',
      chatSuggestion1: 'Talk君最近分析了哪些股票？',
      chatSuggestion2: '半导体产业的最新观点是什么？',
      chatSuggestion3: '最近有什么值得关注的投资趋势？',
      chatSources: '参考来源',
      chatError: '无法连线至 AI 服务，请确认服务器已启动',
      chatThinking: '思考中...',
      chatWelcome: '你好！我是投资Talk君 AI 助手，可以根据Talk君的视频内容回答你的投资问题。',
      chatOffline: 'AI 服务目前离线，请稍后再试',
      chatRateLimit: '请求过于频繁，请稍后再试',
      chatEmpty: '请输入问题',
      sortLabel: '排序',
      sortDateDesc: '日期（新→旧）',
      sortDateAsc: '日期（旧→新）',
      sortDurationDesc: '时长（长→短）',
      sortDurationAsc: '时长（短→长）'
    }
  };

  function label(key) {
    var lang = getLang();
    return (UI_LABELS[lang] && UI_LABELS[lang][key]) || key;
  }

  /* ----------------------------------------------------------
     Data Fetching
  ---------------------------------------------------------- */

  function fetchIndex() {
    return fetch(API_BASE + '/api/videos')
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      });
  }

  /**
   * Fetch a video summary from the API.
   * @param {string} id - The video ID
   * @param {string} publishedAt - The published date (YYYY-MM-DD)
   */
  function fetchSummary(id, publishedAt) {
    var params = 'id=' + encodeURIComponent(id);
    if (publishedAt) params += '&date=' + encodeURIComponent(publishedAt);
    return fetch(API_BASE + '/api/summary?' + params)
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        // Normalize: API returns {id, date, summary} as text
        return {
          id: data.id,
          videoId: data.id,
          publishedAt: data.date,
          title: '',
          summary: {
            'zh-Hant': { paragraph: data.summary, keyPoints: [], tags: [] },
            'zh-Hans': { paragraph: data.summary, keyPoints: [], tags: [] }
          },
          tickers: []
        };
      });
  }

  /* ----------------------------------------------------------
     Formatting Helpers
  ---------------------------------------------------------- */

  /**
   * Format seconds into MM:SS or H:MM:SS.
   */
  function formatDuration(totalSeconds) {
    var sec = Math.floor(totalSeconds);
    var h = Math.floor(sec / 3600);
    var m = Math.floor((sec % 3600) / 60);
    var s = sec % 60;
    var mm = m < 10 ? '0' + m : '' + m;
    var ss = s < 10 ? '0' + s : '' + s;
    if (h > 0) {
      return h + ':' + mm + ':' + ss;
    }
    return mm + ':' + ss;
  }

  /**
   * Format a timestamp in seconds to MM:SS for display.
   */
  function formatTimestamp(sec) {
    return formatDuration(sec);
  }

  /**
   * Format a date string (YYYY-MM-DD) for display.
   */
  function formatDate(dateStr) {
    if (!dateStr) return '';
    var parts = dateStr.split('-');
    if (parts.length === 3) {
      return parts[0] + '/' + parts[1] + '/' + parts[2];
    }
    return dateStr;
  }

  /**
   * Extract the YouTube video ID from a URL.
   */
  function extractYouTubeId(url) {
    if (!url) return null;
    var match = url.match(/(?:v=|\/embed\/|\/v\/|youtu\.be\/)([a-zA-Z0-9_-]{11})/);
    return match ? match[1] : null;
  }

  /**
   * Build a YouTube embed URL with optional start time.
   */
  function youtubeEmbedUrl(videoUrl, startSeconds) {
    var vid = extractYouTubeId(videoUrl);
    if (!vid) return '';
    var url = 'https://www.youtube.com/embed/' + vid + '?rel=0&modestbranding=1&enablejsapi=1';
    if (startSeconds && startSeconds > 0) {
      url += '&start=' + Math.floor(startSeconds);
    }
    return url;
  }

  /* ----------------------------------------------------------
     Language Toggle UI Binding
  ---------------------------------------------------------- */

  function initLangToggle() {
    var toggle = document.querySelector('.lang-toggle');
    if (!toggle) return;

    var lang = getLang();
    _updateToggleUI(toggle, lang);

    var options = toggle.querySelectorAll('.lang-toggle-option');
    options.forEach(function (opt) {
      opt.addEventListener('click', function () {
        var targetLang = opt.getAttribute('data-lang');
        if (targetLang && targetLang !== getLang()) {
          setLang(targetLang);
          _updateToggleUI(toggle, targetLang);
        }
      });
    });
  }

  function _updateToggleUI(toggle, lang) {
    toggle.setAttribute('data-lang', lang);
    var options = toggle.querySelectorAll('.lang-toggle-option');
    options.forEach(function (opt) {
      if (opt.getAttribute('data-lang') === lang) {
        opt.classList.add('active');
      } else {
        opt.classList.remove('active');
      }
    });
  }

  /* ----------------------------------------------------------
     Bookmark Badge Update
  ---------------------------------------------------------- */

  function updateBookmarkBadges() {
    var count = BookmarkManager.count();
    var badges = document.querySelectorAll('.bookmark-count, .nav-badge');
    badges.forEach(function (badge) {
      badge.textContent = count > 0 ? count : '';
      badge.setAttribute('data-count', count);
    });
  }

  /* ----------------------------------------------------------
     Staggered Reveal Animation
  ---------------------------------------------------------- */

  function revealElements(selector, baseDelay) {
    baseDelay = baseDelay || 0;
    var elements = document.querySelectorAll(selector);
    elements.forEach(function (el, i) {
      setTimeout(function () {
        el.classList.add('revealed');
      }, baseDelay + i * 60);
    });
  }

  /* ----------------------------------------------------------
     YouTube Player Control
  ---------------------------------------------------------- */

  var _ytPlayer = null;

  function getYouTubeIframe() {
    return document.querySelector('.video-container iframe');
  }

  /**
   * Seek the YouTube embed to a specific time.
   * Uses postMessage for cross-origin iframe control.
   */
  function seekYouTube(seconds) {
    var iframe = getYouTubeIframe();
    if (!iframe) return;

    // Method 1: Update src with start param (reliable fallback)
    var src = iframe.getAttribute('src');
    if (src) {
      // Remove existing start param
      src = src.replace(/[&?]start=\d+/, '');
      // Add new start param
      var separator = src.indexOf('?') === -1 ? '?' : '&';
      iframe.setAttribute('src', src + separator + 'start=' + Math.floor(seconds));
    }
  }

  /* ----------------------------------------------------------
     Query Parameters
  ---------------------------------------------------------- */

  function getQueryParam(name) {
    var params = new URLSearchParams(window.location.search);
    return params.get(name);
  }

  /* ----------------------------------------------------------
     HTML Escaping
  ---------------------------------------------------------- */

  function escapeHtml(str) {
    if (!str) return '';
    var div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  }

  /* ----------------------------------------------------------
     Public API
  ---------------------------------------------------------- */

  return {
    DATA_BASE: DATA_BASE,
    getLang: getLang,
    setLang: setLang,
    toggleLang: toggleLang,
    label: label,
    fetchIndex: fetchIndex,
    fetchSummary: fetchSummary,
    formatDuration: formatDuration,
    formatTimestamp: formatTimestamp,
    formatDate: formatDate,
    extractYouTubeId: extractYouTubeId,
    youtubeEmbedUrl: youtubeEmbedUrl,
    initLangToggle: initLangToggle,
    updateBookmarkBadges: updateBookmarkBadges,
    revealElements: revealElements,
    seekYouTube: seekYouTube,
    getQueryParam: getQueryParam,
    escapeHtml: escapeHtml
  };
})();
