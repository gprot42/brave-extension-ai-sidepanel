import { useState, useEffect, useCallback } from 'react';
import type { StatusResponse } from '../../shared/messages';

export function useAuth() {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const refreshStatus = useCallback(async () => {
    try {
      const response = await chrome.runtime.sendMessage({ type: 'GET_STATUS' });
      if (response.success) {
        setStatus(response.data as StatusResponse);
      }
    } catch {
      // Extension context may be invalidated
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  const unlock = useCallback(async (password: string, keyFileData?: number[]) => {
    const message: Record<string, unknown> = { type: 'UNLOCK', password };
    if (keyFileData) message.keyFileData = keyFileData;

    const response = await chrome.runtime.sendMessage(message);
    if (response.success) {
      await refreshStatus();
      return true;
    }
    throw new Error(response.error || 'Unlock failed');
  }, [refreshStatus]);

  const lock = useCallback(async () => {
    await chrome.runtime.sendMessage({ type: 'LOCK' });
    await refreshStatus();
  }, [refreshStatus]);

  return { status, loading, refreshStatus, unlock, lock };
}
