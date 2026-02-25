/* ============================================================
   投資Talk君 — Bookmarks Manager (localStorage)
   ============================================================ */

const BookmarkManager = (function () {
  'use strict';

  const STORAGE_KEY = 'talkjun_bookmarks';

  /**
   * Read the raw bookmarks array from localStorage.
   * @returns {Array<{id: string, title: string, publishedAt: string}>}
   */
  function getBookmarks() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) return [];
      const parsed = JSON.parse(raw);
      return Array.isArray(parsed) ? parsed : [];
    } catch (e) {
      console.warn('[BookmarkManager] Failed to parse bookmarks:', e);
      return [];
    }
  }

  /**
   * Persist the bookmarks array to localStorage.
   * @param {Array} bookmarks
   */
  function _save(bookmarks) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(bookmarks));
    } catch (e) {
      console.warn('[BookmarkManager] Failed to save bookmarks:', e);
    }
  }

  /**
   * Add a bookmark. Duplicate IDs are silently ignored.
   * @param {string} id
   * @param {string} title
   * @param {string} publishedAt
   */
  function addBookmark(id, title, publishedAt) {
    const bookmarks = getBookmarks();
    if (bookmarks.some(function (b) { return b.id === id; })) return;
    bookmarks.unshift({ id: id, title: title, publishedAt: publishedAt });
    _save(bookmarks);
    _dispatch('bookmark-changed', { id: id, action: 'add' });
  }

  /**
   * Remove a bookmark by ID.
   * @param {string} id
   */
  function removeBookmark(id) {
    var bookmarks = getBookmarks().filter(function (b) { return b.id !== id; });
    _save(bookmarks);
    _dispatch('bookmark-changed', { id: id, action: 'remove' });
  }

  /**
   * Check if a summary is bookmarked.
   * @param {string} id
   * @returns {boolean}
   */
  function isBookmarked(id) {
    return getBookmarks().some(function (b) { return b.id === id; });
  }

  /**
   * Toggle bookmark state and return the new state.
   * @param {string} id
   * @param {string} title
   * @param {string} publishedAt
   * @returns {boolean} — true if now bookmarked, false if removed
   */
  function toggleBookmark(id, title, publishedAt) {
    if (isBookmarked(id)) {
      removeBookmark(id);
      return false;
    } else {
      addBookmark(id, title, publishedAt);
      return true;
    }
  }

  /**
   * Get total bookmark count.
   * @returns {number}
   */
  function count() {
    return getBookmarks().length;
  }

  /**
   * Dispatch a custom event so other parts of the UI can react.
   */
  function _dispatch(name, detail) {
    try {
      window.dispatchEvent(new CustomEvent(name, { detail: detail }));
    } catch (e) {
      // Fail silently in old WebViews
    }
  }

  // Public API
  return {
    getBookmarks: getBookmarks,
    addBookmark: addBookmark,
    removeBookmark: removeBookmark,
    isBookmarked: isBookmarked,
    toggleBookmark: toggleBookmark,
    count: count
  };
})();
