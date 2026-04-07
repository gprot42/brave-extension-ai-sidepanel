import { useState, useEffect, useCallback } from 'react';
import type { KdbxEntryData, Credentials } from '../../shared/types';

export function useEntries(url: string) {
  const [entries, setEntries] = useState<KdbxEntryData[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const search = useCallback(async (query: string) => {
    try {
      const response = await chrome.runtime.sendMessage({
        type: 'SEARCH_ENTRIES',
        query,
        url,
      });
      if (response.success) {
        setEntries(response.data as KdbxEntryData[]);
      } else {
        setError(response.error);
      }
    } catch (err) {
      setError('Failed to search entries');
    }
  }, [url]);

  const fetchForUrl = useCallback(async () => {
    setLoading(true);
    try {
      const response = await chrome.runtime.sendMessage({
        type: 'GET_ENTRIES_FOR_URL',
        url,
      });
      if (response.success) {
        setEntries(response.data as KdbxEntryData[]);
      }
    } catch {
      setError('Failed to load entries');
    } finally {
      setLoading(false);
    }
  }, [url]);

  useEffect(() => {
    if (url) fetchForUrl();
  }, [url, fetchForUrl]);

  return { entries, loading, error, search, refresh: fetchForUrl };
}
