import React, { useState, useEffect } from 'react';
import type { ExtensionSettings, ExtensionMode } from '../../shared/types';
import { DEFAULT_SETTINGS } from '../../shared/types';

interface Props {
  onBack: () => void;
}

export default function Settings({ onBack }: Props) {
  const [settings, setSettings] = useState<ExtensionSettings>(DEFAULT_SETTINGS);
  const [saved, setSaved] = useState(false);
  const [kpxcStatus, setKpxcStatus] = useState<'disconnected' | 'connecting' | 'connected'>('disconnected');

  useEffect(() => {
    chrome.runtime.sendMessage({ type: 'GET_SETTINGS' }).then((response) => {
      if (response.success) {
        setSettings(response.data as ExtensionSettings);
      }
    });
  }, []);

  async function updateSetting(key: keyof ExtensionSettings, value: unknown) {
    const updated = { ...settings, [key]: value };
    setSettings(updated);

    const response = await chrome.runtime.sendMessage({
      type: 'UPDATE_SETTINGS',
      settings: { [key]: value },
    });

    if (response.success) {
      setSaved(true);
      setTimeout(() => setSaved(false), 1500);
    }
  }

  async function handleConnectKpxc() {
    setKpxcStatus('connecting');
    try {
      const response = await chrome.runtime.sendMessage({ type: 'CONNECT_KEEPASSXC' });
      setKpxcStatus(response.success ? 'connected' : 'disconnected');
    } catch {
      setKpxcStatus('disconnected');
    }
  }

  async function handleDisconnectKpxc() {
    await chrome.runtime.sendMessage({ type: 'DISCONNECT_KEEPASSXC' });
    setKpxcStatus('disconnected');
  }

  return (
    <div className="p-4 flex flex-col gap-4">
      <div className="flex items-center gap-2 mb-2">
        <button onClick={onBack} className="p-1 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-4 h-4">
            <path fillRule="evenodd" d="M17 10a.75.75 0 01-.75.75H5.612l4.158 3.96a.75.75 0 11-1.04 1.08l-5.5-5.25a.75.75 0 010-1.08l5.5-5.25a.75.75 0 111.04 1.08L5.612 9.25H16.25A.75.75 0 0117 10z" clipRule="evenodd" />
          </svg>
        </button>
        <h2 className="text-sm font-semibold text-gray-900">Settings</h2>
        {saved && <span className="text-xs text-green-600 ml-auto">Saved</span>}
      </div>

      {/* Mode selection */}
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-2">Mode</label>
        <div className="flex gap-2">
          {(['standalone', 'keepassxc'] as ExtensionMode[]).map((mode) => (
            <button
              key={mode}
              onClick={() => updateSetting('mode', mode)}
              className={`flex-1 py-2 px-3 text-xs font-medium rounded-lg border transition-colors ${
                settings.mode === mode
                  ? 'border-primary-500 bg-primary-50 text-primary-700'
                  : 'border-gray-200 bg-white text-gray-600 hover:bg-gray-50'
              }`}
            >
              {mode === 'standalone' ? 'Standalone' : 'KeePassXC'}
            </button>
          ))}
        </div>
        <p className="text-xs text-gray-400 mt-1">
          {settings.mode === 'standalone'
            ? 'Read .kdbx files directly in the browser'
            : 'Connect to KeePassXC desktop app'}
        </p>
      </div>

      {/* KeePassXC connection */}
      {settings.mode === 'keepassxc' && (
        <div className="p-3 bg-gray-100 rounded-lg">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className={`w-2 h-2 rounded-full ${kpxcStatus === 'connected' ? 'bg-green-500' : 'bg-gray-400'}`} />
              <span className="text-xs text-gray-700">
                {kpxcStatus === 'connected' ? 'Connected' : kpxcStatus === 'connecting' ? 'Connecting...' : 'Disconnected'}
              </span>
            </div>
            {kpxcStatus === 'connected' ? (
              <button
                onClick={handleDisconnectKpxc}
                className="text-xs text-red-600 hover:underline"
              >
                Disconnect
              </button>
            ) : (
              <button
                onClick={handleConnectKpxc}
                disabled={kpxcStatus === 'connecting'}
                className="text-xs text-primary-600 hover:underline disabled:opacity-50"
              >
                Connect
              </button>
            )}
          </div>
        </div>
      )}

      {/* Lock timeout */}
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Auto-lock timeout
        </label>
        <select
          value={settings.lockTimeoutMinutes}
          onChange={(e) => updateSetting('lockTimeoutMinutes', Number(e.target.value))}
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value={5}>5 minutes</option>
          <option value={15}>15 minutes</option>
          <option value={30}>30 minutes</option>
          <option value={60}>1 hour</option>
          <option value={120}>2 hours</option>
          <option value={240}>4 hours</option>
          <option value={480}>8 hours</option>
          <option value={0}>Never</option>
        </select>
      </div>

      {/* Clipboard clear */}
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Clear clipboard after
        </label>
        <select
          value={settings.clipboardClearSeconds}
          onChange={(e) => updateSetting('clipboardClearSeconds', Number(e.target.value))}
          className="w-full px-3 py-2 text-sm border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500"
        >
          <option value={10}>10 seconds</option>
          <option value={15}>15 seconds</option>
          <option value={30}>30 seconds</option>
          <option value={60}>60 seconds</option>
          <option value={0}>Never</option>
        </select>
      </div>

      {/* Remove database */}
      <div className="border-t border-gray-200 pt-3 mt-2">
        <button
          onClick={async () => {
            await chrome.runtime.sendMessage({ type: 'REMOVE_DATABASE' });
            window.location.reload();
          }}
          className="w-full py-2 text-xs text-red-600 hover:text-red-700 hover:bg-red-50 rounded-lg transition-colors"
        >
          Remove imported database
        </button>
      </div>
    </div>
  );
}
