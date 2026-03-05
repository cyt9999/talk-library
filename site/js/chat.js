/* ============================================================
   投資Talk君 — Chat Page Module
   ============================================================ */

var ChatModule = (function () {
  'use strict';

  /* ----------------------------------------------------------
     Configuration
  ---------------------------------------------------------- */

  // Auto-detect API URL: use localhost for dev, override for production
  var API_URL = (function () {
    var host = window.location.hostname;
    if (host === 'localhost' || host === '127.0.0.1') {
      return 'http://localhost:8080/api/ask';
    }
    // For production, check for a configured endpoint
    var meta = document.querySelector('meta[name="chat-api-url"]');
    if (meta && meta.content) return meta.content;
    return 'http://localhost:8080/api/ask';
  })();

  var _messagesEl = null;
  var _inputEl = null;
  var _sendBtn = null;
  var _isSending = false;

  /* ----------------------------------------------------------
     Initialization
  ---------------------------------------------------------- */

  function init() {
    _messagesEl = document.getElementById('chat-messages');
    _inputEl = document.getElementById('chat-input');
    _sendBtn = document.getElementById('chat-send');

    if (!_messagesEl || !_inputEl || !_sendBtn) return;

    // Show welcome message
    _addAiBubble(TalkApp.label('chatWelcome'), []);

    // Show suggestion chips
    _showSuggestions();

    // Bind events
    _sendBtn.addEventListener('click', _onSend);
    _inputEl.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        _onSend();
      }
    });

    // Auto-resize textarea
    _inputEl.addEventListener('input', _autoResize);
  }

  /* ----------------------------------------------------------
     Suggestions
  ---------------------------------------------------------- */

  function _showSuggestions() {
    var container = document.createElement('div');
    container.className = 'chat-suggestions';

    var keys = ['chatSuggestion1', 'chatSuggestion2', 'chatSuggestion3'];
    keys.forEach(function (key) {
      var chip = document.createElement('button');
      chip.type = 'button';
      chip.className = 'chat-suggestion-chip';
      chip.textContent = TalkApp.label(key);
      chip.addEventListener('click', function () {
        _inputEl.value = chip.textContent;
        _onSend();
      });
      container.appendChild(chip);
    });

    _messagesEl.appendChild(container);
    _scrollToBottom();
  }

  /* ----------------------------------------------------------
     Send Message
  ---------------------------------------------------------- */

  function _onSend() {
    if (_isSending) return;

    var text = (_inputEl.value || '').trim();
    if (!text) return;

    // Remove suggestions if still visible
    var suggestions = _messagesEl.querySelector('.chat-suggestions');
    if (suggestions) suggestions.remove();

    // Add user bubble
    _addUserBubble(text);

    // Clear input
    _inputEl.value = '';
    _autoResize();

    // Show thinking indicator
    var thinkingEl = _addThinking();

    // Send to API
    _isSending = true;
    _sendBtn.disabled = true;

    fetch(API_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: text })
    })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(function (data) {
        thinkingEl.remove();
        _addAiBubble(data.answer || '', data.sources || []);
      })
      .catch(function () {
        thinkingEl.remove();
        _addErrorBubble(TalkApp.label('chatError'));
      })
      .finally(function () {
        _isSending = false;
        _sendBtn.disabled = false;
        _inputEl.focus();
      });
  }

  /* ----------------------------------------------------------
     Bubble Helpers
  ---------------------------------------------------------- */

  function _addUserBubble(text) {
    var bubble = document.createElement('div');
    bubble.className = 'chat-bubble chat-bubble-user';
    bubble.textContent = text;
    _messagesEl.appendChild(bubble);
    _scrollToBottom();
  }

  function _addAiBubble(text, sources) {
    var bubble = document.createElement('div');
    bubble.className = 'chat-bubble chat-bubble-ai';

    // Render text with basic line breaks
    var textEl = document.createElement('div');
    textEl.innerHTML = _formatText(text);
    bubble.appendChild(textEl);

    // Render sources
    if (sources && sources.length > 0) {
      var srcDiv = document.createElement('div');
      srcDiv.className = 'chat-sources';

      var srcLabel = document.createElement('div');
      srcLabel.className = 'chat-sources-label';
      srcLabel.textContent = TalkApp.label('chatSources');
      srcDiv.appendChild(srcLabel);

      sources.forEach(function (src) {
        var item = document.createElement('div');
        item.className = 'chat-source-item';
        item.textContent = _cleanSourceName(src);
        srcDiv.appendChild(item);
      });

      bubble.appendChild(srcDiv);
    }

    _messagesEl.appendChild(bubble);
    _scrollToBottom();
  }

  function _addErrorBubble(text) {
    var bubble = document.createElement('div');
    bubble.className = 'chat-bubble chat-bubble-error';
    bubble.textContent = text;
    _messagesEl.appendChild(bubble);
    _scrollToBottom();
  }

  function _addThinking() {
    var el = document.createElement('div');
    el.className = 'chat-thinking';
    el.innerHTML =
      '<div class="loader-dots">' +
        '<div class="loader-dot"></div>' +
        '<div class="loader-dot"></div>' +
        '<div class="loader-dot"></div>' +
      '</div>' +
      '<span>' + TalkApp.label('chatThinking') + '</span>';
    _messagesEl.appendChild(el);
    _scrollToBottom();
    return el;
  }

  /* ----------------------------------------------------------
     Utilities
  ---------------------------------------------------------- */

  function _scrollToBottom() {
    requestAnimationFrame(function () {
      _messagesEl.scrollTop = _messagesEl.scrollHeight;
    });
  }

  function _autoResize() {
    _inputEl.style.height = 'auto';
    _inputEl.style.height = Math.min(_inputEl.scrollHeight, 120) + 'px';
  }

  function _formatText(text) {
    if (!text) return '';
    // Escape HTML, then convert newlines to <br>
    var div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML.replace(/\n/g, '<br>');
  }

  function _cleanSourceName(filename) {
    // Strip path, extension, and temp suffixes (e.g. _pw55djdi)
    var name = filename.replace(/^.*\//, '').replace(/\.md$/, '').replace(/\.json$/, '').replace(/_[a-z0-9]{6,}$/, '');

    // video-2026-03-03-XKgWzUWnoa8 → 📺 YouTube影片 [2026/03/03]
    var videoMatch = name.match(/^video-(\d{4})-(\d{2})-(\d{2})-(.+)$/);
    if (videoMatch) {
      return '📺 YouTube影片 [' + videoMatch[1] + '/' + videoMatch[2] + '/' + videoMatch[3] + ']';
    }

    // tweets-2026-W09 → 📝 X平台短評 [2026年第09週]
    var tweetMatch = name.match(/^tweets-(\d{4})-W(\d{2})$/);
    if (tweetMatch) {
      return '📝 X平台短評 [' + tweetMatch[1] + '年第' + tweetMatch[2] + '週]';
    }

    // sheet-xxx-latest → 📊 Sheet name
    var sheetMatch = name.match(/^sheet-(.+?)-latest$/);
    if (sheetMatch) {
      var sheetNames = {
        'macro-announcements': '📊 總經公告',
        'positions-ytd': '📊 持倉績效',
        'data-sources': '📊 資料來源',
        'portfolio-beta': '📊 持倉Beta',
        'community-posts': '📊 社團貼文'
      };
      return sheetNames[sheetMatch[1]] || '📊 ' + sheetMatch[1];
    }

    // app-guide → 📖 使用指南
    if (name === 'app-guide') {
      return '📖 使用指南';
    }

    return name;
  }

  /* ----------------------------------------------------------
     Language Update
  ---------------------------------------------------------- */

  function onLangChanged() {
    // Update placeholder
    if (_inputEl) {
      _inputEl.placeholder = TalkApp.label('chatPlaceholder');
    }
    // Update page title
    var titleEl = document.getElementById('page-title');
    var subtitleEl = document.getElementById('page-subtitle');
    if (titleEl) titleEl.textContent = TalkApp.label('chatTitle');
    if (subtitleEl) subtitleEl.textContent = TalkApp.label('chatSubtitle');
    document.title = TalkApp.label('chatTitle') + ' - 投資Talk君';
  }

  /* ----------------------------------------------------------
     Public API
  ---------------------------------------------------------- */

  return {
    init: init,
    onLangChanged: onLangChanged
  };
})();
