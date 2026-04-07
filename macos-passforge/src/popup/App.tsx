import React, { useEffect, useState } from 'react';
import type { StatusResponse } from '../shared/messages';
import type { ExtensionSettings } from '../shared/types';
import ImportDb from './components/ImportDb';
import UnlockForm from './components/UnlockForm';
import EntryList from './components/EntryList';
import Settings from './components/Settings';

type View = 'loading' | 'import' | 'unlock' | 'entries' | 'settings';

export default function App() {
  const [view, setView] = useState<View>('loading');
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string>('');

  // Check storage directly — works even if service worker is down
  async function checkStorageForDatabase(): Promise<boolean> {
    try {
      const result = await chrome.storage.local.get('kdbxData');
      return !!result.kdbxData;
    } catch {
      return false;
    }
  }

  async function refreshStatus() {
    try {
      const response = await chrome.runtime.sendMessage({ type: 'GET_STATUS' });
      if (response && response.success) {
        const s = response.data as StatusResponse;
        setStatus(s);
        if (!s.hasDatabase) {
          setView('import');
        } else if (!s.isUnlocked) {
          setView('unlock');
        } else {
          setView('entries');
        }
        return;
      }
    } catch {
      // Service worker may be waking up — fall through to storage check
    }

    // Fallback: check storage directly to decide import vs unlock
    const hasDb = await checkStorageForDatabase();
    setView(hasDb ? 'unlock' : 'import');
  }

  useEffect(() => {
    // Timeout fallback: check storage if service worker is too slow
    const timeout = setTimeout(async () => {
      if (view === 'loading') {
        const hasDb = await checkStorageForDatabase();
        setView(hasDb ? 'unlock' : 'import');
      }
    }, 3000);

    refreshStatus();

    return () => clearTimeout(timeout);
  }, []);

  function handleImported() {
    setView('unlock');
    refreshStatus();
  }

  function handleUnlocked() {
    setView('entries');
    refreshStatus();
  }

  function handleLock() {
    chrome.runtime.sendMessage({ type: 'LOCK' }).then(() => {
      setView('unlock');
      refreshStatus();
    });
  }

  if (view === 'loading') {
    return (
      <div className="w-popup h-popup flex items-center justify-center bg-gray-50">
        <div className="text-gray-400 text-sm">Loading...</div>
      </div>
    );
  }

  return (
    <div className="w-popup h-popup flex flex-col bg-gray-50">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 bg-white border-b border-gray-200">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 bg-primary-600 rounded flex items-center justify-center">
            <span className="text-white text-xs font-bold">P</span>
          </div>
          <h1 className="text-sm font-semibold text-gray-900">PassForge</h1>
        </div>
        <div className="flex items-center gap-1">
          {view === 'entries' && (
            <button
              onClick={handleLock}
              className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded"
              title="Lock database"
            >
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
                <path fillRule="evenodd" d="M10 1a4.5 4.5 0 00-4.5 4.5V9H5a2 2 0 00-2 2v6a2 2 0 002 2h10a2 2 0 002-2v-6a2 2 0 00-2-2h-.5V5.5A4.5 4.5 0 0010 1zm3 8V5.5a3 3 0 10-6 0V9h6z" clipRule="evenodd" />
              </svg>
            </button>
          )}
          <button
            onClick={() => setView(view === 'settings' ? (status?.isUnlocked ? 'entries' : status?.hasDatabase ? 'unlock' : 'import') : 'settings')}
            className="p-1.5 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded"
            title="Settings"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
              <path fillRule="evenodd" d="M7.84 1.804A1 1 0 018.82 1h2.36a1 1 0 01.98.804l.331 1.652a6.993 6.993 0 011.929 1.115l1.598-.54a1 1 0 011.186.447l1.18 2.044a1 1 0 01-.205 1.251l-1.267 1.113a7.047 7.047 0 010 2.228l1.267 1.113a1 1 0 01.206 1.25l-1.18 2.045a1 1 0 01-1.187.447l-1.598-.54a6.993 6.993 0 01-1.929 1.115l-.33 1.652a1 1 0 01-.98.804H8.82a1 1 0 01-.98-.804l-.331-1.652a6.993 6.993 0 01-1.929-1.115l-1.598.54a1 1 0 01-1.186-.447l-1.18-2.044a1 1 0 01.205-1.251l1.267-1.114a7.05 7.05 0 010-2.227L1.821 7.773a1 1 0 01-.206-1.25l1.18-2.045a1 1 0 011.187-.447l1.598.54A6.993 6.993 0 017.51 3.456l.33-1.652zM10 13a3 3 0 100-6 3 3 0 000 6z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="px-4 py-2 bg-red-50 text-red-700 text-xs border-b border-red-200">
          {error}
          <button onClick={() => setError('')} className="ml-2 underline">Dismiss</button>
        </div>
      )}

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {view === 'import' && <ImportDb onImported={handleImported} />}
        {view === 'unlock' && <UnlockForm onUnlocked={handleUnlocked} onError={setError} />}
        {view === 'entries' && <EntryList />}
        {view === 'settings' && <Settings onBack={() => refreshStatus()} />}
      </div>
    </div>
  );
}
