import React, { useState, useRef } from 'react';

interface Props {
  onUnlocked: () => void;
  onError: (error: string) => void;
}

export default function UnlockForm({ onUnlocked, onError }: Props) {
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [localError, setLocalError] = useState('');
  const [refreshing, setRefreshing] = useState(false);
  const passwordRef = useRef<HTMLInputElement>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  async function handleUnlock(e: React.FormEvent) {
    e.preventDefault();
    if (!password) return;

    setLoading(true);
    setLocalError('');

    try {
      const response = await chrome.runtime.sendMessage({
        type: 'UNLOCK',
        password,
      });

      if (response.success) {
        setPassword('');
        onUnlocked();
      } else {
        setLocalError(response.error || 'Invalid password');
      }
    } catch (err) {
      setLocalError('Failed to unlock database');
    } finally {
      setLoading(false);
    }
  }

  async function handleRemoveDb() {
    await chrome.runtime.sendMessage({ type: 'REMOVE_DATABASE' });
    window.location.reload();
  }

  function handleRefreshClick() {
    fileRef.current?.click();
  }

  async function handleFileSelected(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;

    setRefreshing(true);
    setLocalError('');

    try {
      const buffer = await file.arrayBuffer();
      const data = Array.from(new Uint8Array(buffer));

      const response = await chrome.runtime.sendMessage({
        type: 'IMPORT_DATABASE',
        data,
      });

      if (response.success) {
        setLocalError('');
        // Show success feedback briefly
        setRefreshing(false);
        // Focus password field for quick re-unlock
        passwordRef.current?.focus();
      } else {
        setLocalError(response.error || 'Failed to refresh database');
        setRefreshing(false);
      }
    } catch {
      setLocalError('Failed to refresh database');
      setRefreshing(false);
    }

    // Reset file input so the same file can be selected again
    if (fileRef.current) fileRef.current.value = '';
  }

  return (
    <div className="p-4 flex flex-col gap-4">
      <div className="text-center py-4">
        <div className="w-14 h-14 bg-amber-100 rounded-full flex items-center justify-center mx-auto mb-3">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-7 h-7 text-amber-600">
            <path fillRule="evenodd" d="M12 1.5a5.25 5.25 0 00-5.25 5.25v3a3 3 0 00-3 3v6.75a3 3 0 003 3h10.5a3 3 0 003-3v-6.75a3 3 0 00-3-3v-3c0-2.9-2.35-5.25-5.25-5.25zm3.75 8.25v-3a3.75 3.75 0 10-7.5 0v3h7.5z" clipRule="evenodd" />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-gray-900">Unlock Database</h2>
        <p className="text-sm text-gray-500 mt-1">Enter your master password</p>
      </div>

      <form onSubmit={handleUnlock} className="flex flex-col gap-3">
        <div>
          <label htmlFor="master-password" className="block text-xs font-medium text-gray-700 mb-1">
            Master Password
          </label>
          <input
            ref={passwordRef}
            id="master-password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Enter master password"
            autoFocus
            className="w-full px-3 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-primary-500 focus:border-primary-500"
          />
        </div>

        {localError && (
          <p className="text-xs text-red-600">{localError}</p>
        )}

        <button
          type="submit"
          disabled={loading || !password}
          className="w-full py-2.5 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {loading ? 'Unlocking...' : 'Unlock'}
        </button>
      </form>

      <div className="border-t border-gray-200 pt-3 mt-2 flex flex-col gap-2">
        <input
          ref={fileRef}
          type="file"
          accept=".kdbx"
          onChange={handleFileSelected}
          className="hidden"
        />
        <button
          onClick={handleRefreshClick}
          disabled={refreshing}
          className="w-full text-xs text-primary-600 hover:text-primary-700 transition-colors flex items-center justify-center gap-1"
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
            <path fillRule="evenodd" d="M15.312 11.424a5.5 5.5 0 01-9.201 2.466l-.312-.311h2.433a.75.75 0 000-1.5H4.598a.75.75 0 00-.75.75v3.634a.75.75 0 001.5 0v-2.033l.312.311a7 7 0 0011.712-3.138.75.75 0 00-1.449-.39zm-10.624-2.85a5.5 5.5 0 019.201-2.465l.312.31H11.77a.75.75 0 000 1.5h3.634a.75.75 0 00.75-.75V3.535a.75.75 0 00-1.5 0v2.034l-.312-.312A7 7 0 002.63 8.389a.75.75 0 001.45.388z" clipRule="evenodd" />
          </svg>
          {refreshing ? 'Refreshing...' : 'Refresh database file'}
        </button>
        <button
          onClick={handleRemoveDb}
          className="w-full text-xs text-gray-500 hover:text-red-600 transition-colors"
        >
          Remove imported database
        </button>
      </div>
    </div>
  );
}
