import React, { useState, useEffect, useCallback } from 'react';
import type { KdbxEntryData, Credentials } from '../../shared/types';
import EntryItem from './EntryItem';

export default function EntryList() {
  const [entries, setEntries] = useState<KdbxEntryData[]>([]);
  const [query, setQuery] = useState('');
  const [currentUrl, setCurrentUrl] = useState('');
  const [loading, setLoading] = useState(true);
  const [selectedIndex, setSelectedIndex] = useState(-1);
  const [autofillError, setAutofillError] = useState('');

  const fetchEntries = useCallback(async (searchQuery: string, url?: string) => {
    try {
      const response = await chrome.runtime.sendMessage({
        type: searchQuery ? 'SEARCH_ENTRIES' : 'GET_ENTRIES_FOR_URL',
        query: searchQuery,
        url: url || currentUrl,
      });
      if (response.success) {
        setEntries(response.data as KdbxEntryData[]);
      }
    } catch {
      // Extension context may be invalidated
    }
  }, [currentUrl]);

  useEffect(() => {
    // Get current tab URL
    chrome.tabs.query({ active: true, currentWindow: true }).then(([tab]) => {
      const url = tab?.url || '';
      setCurrentUrl(url);
      fetchEntries('', url).then(() => setLoading(false));
    });
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      fetchEntries(query, currentUrl);
    }, 200);
    return () => clearTimeout(timer);
  }, [query, fetchEntries, currentUrl]);

  async function handleAutofill(credentials: Credentials) {
    setAutofillError('');
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) return;

    try {
      const response = await chrome.runtime.sendMessage({
        type: 'AUTOFILL',
        entry: credentials,
        tabId: tab.id,
      });

      if (response.success) {
        // Close popup after successful autofill
        window.close();
      } else {
        setAutofillError(response.error || 'Autofill failed');
      }
    } catch {
      setAutofillError('Failed to autofill. Try refreshing the page.');
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIndex((i) => Math.min(i + 1, entries.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIndex((i) => Math.max(i - 1, -1));
    } else if (e.key === 'Enter' && selectedIndex >= 0 && entries[selectedIndex]) {
      handleAutofill({
        username: entries[selectedIndex].username,
        password: entries[selectedIndex].password,
      });
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-gray-400 text-sm">Loading entries...</div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full" onKeyDown={handleKeyDown}>
      {/* Autofill error banner */}
      {autofillError && (
        <div className="px-3 py-2 bg-red-50 text-red-700 text-xs border-b border-red-200 flex items-center justify-between">
          <span>{autofillError}</span>
          <button onClick={() => setAutofillError('')} className="ml-2 underline">Dismiss</button>
        </div>
      )}

      {/* Search bar */}
      <div className="px-3 py-2 border-b border-gray-200 bg-white">
        <div className="relative">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4 absolute left-2.5 top-1/2 -translate-y-1/2 text-gray-400">
            <path fillRule="evenodd" d="M9 3.5a5.5 5.5 0 100 11 5.5 5.5 0 000-11zM2 9a7 7 0 1112.452 4.391l3.328 3.329a.75.75 0 11-1.06 1.06l-3.329-3.328A7 7 0 012 9z" clipRule="evenodd" />
          </svg>
          <input
            type="text"
            value={query}
            onChange={(e) => { setQuery(e.target.value); setSelectedIndex(-1); }}
            placeholder="Search entries..."
            autoFocus
            className="w-full pl-8 pr-3 py-2 text-sm bg-gray-100 border-0 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 focus:bg-white"
          />
          {query && (
            <button
              onClick={() => { setQuery(''); setSelectedIndex(-1); }}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Entries list */}
      <div className="flex-1 overflow-y-auto">
        {entries.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 text-gray-400">
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-10 h-10 mb-2">
              <path fillRule="evenodd" d="M10.5 3.75a6.75 6.75 0 100 13.5 6.75 6.75 0 000-13.5zM2.25 10.5a8.25 8.25 0 1114.59 5.28l4.69 4.69a.75.75 0 11-1.06 1.06l-4.69-4.69A8.25 8.25 0 012.25 10.5z" clipRule="evenodd" />
            </svg>
            <span className="text-sm">
              {query ? 'No matching entries' : 'No entries for this site'}
            </span>
            {!query && (
              <button
                onClick={() => fetchEntries('', '')}
                className="mt-2 text-xs text-primary-600 hover:underline"
              >
                Show all entries
              </button>
            )}
          </div>
        ) : (
          <div>
            {!query && entries.length > 0 && (
              <div className="px-4 py-1.5 text-xs text-gray-400 bg-gray-50 flex items-center justify-between">
                <span>{entries.length} {entries.length === 1 ? 'entry' : 'entries'} found</span>
                {currentUrl && (
                  <button
                    onClick={() => { setCurrentUrl(''); setEntries([]); }}
                    className="text-gray-400 hover:text-red-600 transition-colors"
                    title="Clear URL matches"
                  >
                    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
                      <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
                    </svg>
                  </button>
                )}
              </div>
            )}
            {entries.map((entry, index) => (
              <div key={entry.uuid} className={selectedIndex === index ? 'bg-primary-50' : ''}>
                <EntryItem
                  entry={entry}
                  onAutofill={handleAutofill}
                />
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
