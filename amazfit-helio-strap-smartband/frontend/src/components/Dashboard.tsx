import { useHealthData } from '../hooks/useHealthData';
import type { DeviceStatus } from '../types';
import { useState, useCallback, useEffect } from 'react';
import RealtimeHR from './RealtimeHR';
import SleepChart from './SleepChart';
import SpO2Chart from './SpO2Chart';
import StressChart from './StressChart';
import HRVChart from './HRVChart';
import ActivitySummary from './ActivitySummary';
import DeviceStatusPanel from './DeviceStatus';
import InfoTooltip from './InfoTooltip';
import AIAnalysis from './AIAnalysis';
import { useWebSocket } from '../hooks/useWebSocket';

const TIMEZONES = [
  'UTC',
  'America/Anchorage', 'America/New_York', 'America/Chicago', 'America/Denver',
  'America/Los_Angeles', 'America/Phoenix', 'America/Toronto', 'America/Vancouver',
  'America/Mexico_City', 'America/Sao_Paulo', 'America/Argentina/Buenos_Aires',
  'America/Bogota', 'America/Lima', 'America/Santiago',
  'Europe/London', 'Europe/Dublin', 'Europe/Paris', 'Europe/Berlin', 'Europe/Amsterdam',
  'Europe/Brussels', 'Europe/Zurich', 'Europe/Vienna', 'Europe/Rome', 'Europe/Madrid',
  'Europe/Lisbon', 'Europe/Stockholm', 'Europe/Oslo', 'Europe/Copenhagen',
  'Europe/Helsinki', 'Europe/Warsaw', 'Europe/Prague', 'Europe/Budapest',
  'Europe/Bucharest', 'Europe/Athens', 'Europe/Istanbul', 'Europe/Moscow',
  'Africa/Cairo', 'Africa/Johannesburg', 'Africa/Lagos', 'Africa/Nairobi',
  'Asia/Dubai', 'Asia/Riyadh', 'Asia/Tehran', 'Asia/Karachi', 'Asia/Kolkata',
  'Asia/Dhaka', 'Asia/Bangkok', 'Asia/Jakarta', 'Asia/Singapore', 'Asia/Hong_Kong',
  'Asia/Shanghai', 'Asia/Taipei', 'Asia/Seoul', 'Asia/Tokyo',
  'Australia/Perth', 'Australia/Adelaide', 'Australia/Sydney', 'Australia/Brisbane',
  'Pacific/Auckland', 'Pacific/Fiji', 'Pacific/Honolulu',
];

function getBpmColor(bpm: number) {
  if (bpm < 100) return 'text-emerald-400';
  if (bpm < 140) return 'text-yellow-400';
  return 'text-red-400';
}

export default function Dashboard() {
  const { data: deviceData } = useHealthData<DeviceStatus>('/api/device', 10000);
  const device = deviceData.length > 0 ? deviceData[0] : null;
  const hasAuth = device?.has_auth ?? false;
  const isConnected = device?.state === 'CONNECTED';
  const [showSettings, setShowSettings] = useState(false);
  const [timezone, setTimezone] = useState(() => localStorage.getItem('tz') || Intl.DateTimeFormat().resolvedOptions().timeZone);
  const [authKeyInput, setAuthKeyInput] = useState('');
  const [authKeyStatus, setAuthKeyStatus] = useState<string | null>(null);
  const [showCurrentKey, setShowCurrentKey] = useState(false);
  const [currentKey, setCurrentKey] = useState<string | null>(null);
  const [exportDays, setExportDays] = useState(30);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [resetConfirm, setResetConfirm] = useState(false);
  const [resetStatus, setResetStatus] = useState<string | null>(null);
  const [spo2Auto, setSpo2Auto] = useState<boolean | null>(null);
  const [spo2Loading, setSpo2Loading] = useState(false);
  const [spo2Status, setSpo2Status] = useState<string | null>(null);
  const [showHelp, setShowHelp] = useState(false);
  const [ollamaUrl, setOllamaUrl] = useState(() => localStorage.getItem('ollama_url') || 'http://localhost:11434');
  const [ollamaModel, setOllamaModel] = useState(() => localStorage.getItem('ollama_model') || '');
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [aiDays, setAiDays] = useState(() => Number(localStorage.getItem('ai_days')) || 7);
  const [aiEnabled, setAiEnabled] = useState(() => localStorage.getItem('ai_enabled') !== 'false');
  const [aiProvider, setAiProvider] = useState<'ollama' | 'lmstudio'>(() => 
    (localStorage.getItem('ai_provider') as 'ollama' | 'lmstudio') || 'ollama'
  );

  // Auto-detect available models on mount / when URL or provider changes
  useEffect(() => {
    fetch(`/api/ai-models?ollama_url=${encodeURIComponent(ollamaUrl)}&provider=${aiProvider}`)
      .then(r => r.json())
      .then(data => {
        if (data.models?.length) {
          setAvailableModels(data.models);
          // If no model is set or current model isn't available, use the first available
          const saved = localStorage.getItem('ollama_model');
          if (!saved || !data.models.includes(saved)) {
            setOllamaModel(data.models[0]);
            localStorage.setItem('ollama_model', data.models[0]);
          }
        }
      })
      .catch(() => {});
  }, [ollamaUrl, aiProvider]);

  const toggleFullscreen = useCallback(() => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else {
      document.exitFullscreen().catch(() => {});
    }
  }, []);

  useEffect(() => {
    const handler = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener('fullscreenchange', handler);
    return () => document.removeEventListener('fullscreenchange', handler);
  }, []);

  const saveTimezone = (tz: string) => {
    setTimezone(tz);
    localStorage.setItem('tz', tz);
  };

  const submitAuthKey = async () => {
    if (authKeyInput.length !== 32) {
      setAuthKeyStatus('Key must be exactly 32 hex characters');
      return;
    }
    try {
      const res = await fetch(`/api/auth-key?key=${authKeyInput}`, { method: 'POST' });
      if (res.ok) {
        setAuthKeyStatus('Auth key saved');
        setAuthKeyInput('');
      } else {
        const err = await res.json();
        setAuthKeyStatus(err.detail || 'Failed');
      }
    } catch {
      setAuthKeyStatus('Network error');
    }
  };

  const handleResetData = async () => {
    if (!resetConfirm) {
      setResetConfirm(true);
      setTimeout(() => setResetConfirm(false), 5000);
      return;
    }
    try {
      const res = await fetch('/api/reset-data', { method: 'POST' });
      if (res.ok) {
        setResetStatus('All data cleared');
        setResetConfirm(false);
        setTimeout(() => window.location.reload(), 1000);
      } else {
        const err = await res.json().catch(() => null);
        setResetStatus(err?.detail || 'Reset failed — try again when sync is not running');
        setResetConfirm(false);
      }
    } catch {
      setResetStatus('Network error');
      setResetConfirm(false);
    }
  };

  const fetchSpo2Auto = useCallback(async () => {
    if (!isConnected) return;
    try {
      const res = await fetch('/api/device-config/spo2-auto');
      if (res.ok) {
        const data = await res.json();
        setSpo2Auto(data.enabled);
      }
    } catch { /* ignore */ }
  }, [isConnected]);

  const toggleSpo2Auto = async () => {
    const newVal = !(spo2Auto ?? false);
    setSpo2Loading(true);
    setSpo2Status(null);
    try {
      const res = await fetch(`/api/device-config/spo2-auto?enabled=${newVal}`, { method: 'POST' });
      if (res.ok) {
        setSpo2Auto(newVal);
        setSpo2Status(newVal ? 'SpO2 monitoring enabled' : 'SpO2 monitoring disabled');
      } else {
        const err = await res.json().catch(() => null);
        setSpo2Status(err?.detail || 'Failed to change setting');
      }
    } catch {
      setSpo2Status('Network error');
    } finally {
      setSpo2Loading(false);
      setTimeout(() => setSpo2Status(null), 3000);
    }
  };

  // Fetch SpO2 auto setting when connected + settings open
  useEffect(() => {
    if (showSettings && isConnected) {
      fetchSpo2Auto();
    }
  }, [showSettings, isConnected, fetchSpo2Auto]);

  const toggleShowKey = async () => {
    if (showCurrentKey) {
      setShowCurrentKey(false);
      setCurrentKey(null);
      return;
    }
    try {
      const res = await fetch('/api/auth-key');
      const data = await res.json();
      if (data.key) {
        setCurrentKey(data.key);
        setShowCurrentKey(true);
      }
    } catch {
      // ignore
    }
  };

  return (
    <div className="h-screen flex flex-col bg-gray-950 text-gray-100 overflow-hidden">
      <header className="flex-none border-b border-gray-800 px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-lg font-bold leading-tight">Amazfit Helio Strap</h1>
            <p className="text-xs text-gray-500">Real-time health monitoring</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <DeviceStatusPanel />
          <button
            onClick={toggleFullscreen}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
            title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {isFullscreen ? (
              <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="4 14 10 14 10 20"/><polyline points="20 10 14 10 14 4"/><line x1="14" y1="10" x2="21" y2="3"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
            ) : (
              <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 3 21 3 21 9"/><polyline points="9 21 3 21 3 15"/><line x1="21" y1="3" x2="14" y2="10"/><line x1="3" y1="21" x2="10" y2="14"/></svg>
            )}
          </button>
          <button
            onClick={() => setShowHelp(true)}
            className="w-8 h-8 flex items-center justify-center rounded-lg text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
            title="Help"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          </button>
          <button
            onClick={() => setShowSettings(!showSettings)}
            className={`w-8 h-8 flex items-center justify-center rounded-lg transition-colors ${showSettings ? 'bg-gray-700 text-gray-200' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800'}`}
            title="Settings"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
          </button>
        </div>
      </header>

      {showSettings && (
        <div className="flex-none border-b border-gray-800 px-4 py-3 bg-gray-900 space-y-3">
          <div className="flex items-center gap-4">
            <label className="text-xs text-gray-400">Timezone:</label>
            <select
              value={timezone}
              onChange={(e) => saveTimezone(e.target.value)}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-blue-500"
            >
              {TIMEZONES.map((tz: string) => (
                <option key={tz} value={tz}>{tz}</option>
              ))}
            </select>
            <span className="text-[10px] text-gray-500">Current: {timezone}</span>
          </div>
          <div className="flex items-center gap-4">
            <label className="text-xs text-gray-400">Device:</label>
            {device?.device_id ? (
              <span className="text-[10px] text-gray-300 font-mono bg-gray-800 px-2 py-0.5 rounded select-all">{device.device_id}</span>
            ) : (
              <span className="text-[10px] text-gray-500">No device cached — use BT Scan to find one</span>
            )}
          </div>
          <div className="flex items-center gap-4">
            <label className="text-xs text-gray-400">Auth Key:</label>
            <input
              type="password"
              value={authKeyInput}
              onChange={(e) => setAuthKeyInput(e.target.value)}
              placeholder="32-char hex key"
              maxLength={32}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 w-64 font-mono focus:outline-none focus:border-blue-500"
            />
            <button
              onClick={submitAuthKey}
              className="bg-blue-600 hover:bg-blue-500 text-white text-xs px-3 py-1 rounded"
            >
              Save
            </button>
            {hasAuth && (
              <button
                onClick={toggleShowKey}
                className="text-[10px] text-gray-500 hover:text-gray-300 underline"
              >
                {showCurrentKey ? 'Hide' : 'Show'} key
              </button>
            )}
            {authKeyStatus && <span className="text-[10px] text-gray-400">{authKeyStatus}</span>}
            {hasAuth && !showCurrentKey && <span className="text-[10px] text-emerald-400">Key set</span>}
            {showCurrentKey && currentKey && (
              <span className="text-[10px] text-gray-300 font-mono bg-gray-800 px-2 py-0.5 rounded select-all">{currentKey}</span>
            )}
          </div>
          <div className="flex items-center gap-4">
            <label className="text-xs text-gray-400">Export:</label>
            <select
              value={exportDays}
              onChange={(e) => setExportDays(Number(e.target.value))}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-blue-500"
            >
              <option value={7}>Last 7 days</option>
              <option value={14}>Last 14 days</option>
              <option value={30}>Last 30 days</option>
              <option value={90}>Last 90 days</option>
              <option value={365}>Last year</option>
            </select>
            <a
              href={`/api/export?days=${exportDays}`}
              download={`health_export_${exportDays}d.json`}
              className="bg-blue-600 hover:bg-blue-500 text-white text-xs px-3 py-1 rounded"
            >
              Download JSON
            </a>
            <span className="text-[10px] text-gray-500">All health data for LLM / medical analysis</span>
          </div>
          <div className="flex items-center gap-4">
            <label className="text-xs text-gray-400">Device:</label>
            <div className="flex items-center gap-3">
              <span className="text-xs text-gray-500">Auto SpO2</span>
              <button
                onClick={toggleSpo2Auto}
                disabled={spo2Loading || !isConnected}
                className={`relative w-10 h-5 rounded-full transition-colors disabled:opacity-50 ${
                  spo2Auto ? 'bg-green-600' : 'bg-gray-700'
                }`}
              >
                <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                  spo2Auto ? 'translate-x-5' : ''
                }`} />
              </button>
              {!isConnected && <span className="text-[10px] text-gray-600">Connect to device first</span>}
              {spo2Status && <span className="text-[10px] text-green-400">{spo2Status}</span>}
            </div>
          </div>
          <div className="flex items-center gap-4">
            <label className="text-xs text-gray-400">AI Analysis:</label>
            <button
              onClick={() => { const v = !aiEnabled; setAiEnabled(v); localStorage.setItem('ai_enabled', String(v)); }}
              className={`relative w-10 h-5 rounded-full transition-colors ${aiEnabled ? 'bg-blue-600' : 'bg-gray-600'}`}
            >
              <span className={`absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition-transform ${
                aiEnabled ? 'translate-x-5' : ''
              }`} />
            </button>
            <span className="text-[10px] text-gray-500">{aiEnabled ? 'AI panel visible' : 'AI panel hidden'}</span>
          </div>
          {aiEnabled && <div className="flex items-center gap-4 flex-wrap">
            <label className="text-xs text-gray-400">Provider:</label>
            <select
              value={aiProvider}
              onChange={(e) => { 
                const v = e.target.value as 'ollama' | 'lmstudio';
                setAiProvider(v); 
                localStorage.setItem('ai_provider', v);
                // Update default URL based on provider
                const defaultUrl = v === 'lmstudio' ? 'http://localhost:1234' : 'http://localhost:11434';
                setOllamaUrl(defaultUrl);
                localStorage.setItem('ollama_url', defaultUrl);
              }}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-blue-500"
            >
              <option value="ollama">Ollama</option>
              <option value="lmstudio">LM Studio</option>
            </select>
            <input
              value={ollamaUrl}
              onChange={(e) => { setOllamaUrl(e.target.value); localStorage.setItem('ollama_url', e.target.value); }}
              placeholder={aiProvider === 'lmstudio' ? "http://localhost:1234" : "http://localhost:11434"}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 w-48 font-mono focus:outline-none focus:border-blue-500"
            />
            {availableModels.length > 0 ? (
              <select
                value={ollamaModel}
                onChange={(e) => { setOllamaModel(e.target.value); localStorage.setItem('ollama_model', e.target.value); }}
                className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 font-mono focus:outline-none focus:border-blue-500"
              >
                {availableModels.map((m) => (
                  <option key={m} value={m}>{m}</option>
                ))}
              </select>
            ) : (
              <input
                value={ollamaModel}
                onChange={(e) => { setOllamaModel(e.target.value); localStorage.setItem('ollama_model', e.target.value); }}
                placeholder="model name"
                className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 w-28 font-mono focus:outline-none focus:border-blue-500"
              />
            )}
            <select
              value={aiDays}
              onChange={(e) => { const v = Number(e.target.value); setAiDays(v); localStorage.setItem('ai_days', String(v)); }}
              className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200 focus:outline-none focus:border-blue-500"
            >
              <option value={7}>7 days</option>
              <option value={14}>14 days</option>
              <option value={30}>30 days</option>
              <option value={90}>90 days</option>
            </select>
            <span className="text-[10px] text-gray-500">{aiProvider === 'lmstudio' ? 'LM Studio' : 'Ollama'} URL, model, data range</span>
          </div>}
          <div className="flex items-center gap-4">
            <label className="text-xs text-gray-400">Data:</label>
            <button
              onClick={handleResetData}
              className={`text-xs px-3 py-1 rounded ${resetConfirm ? 'bg-red-600 hover:bg-red-500 text-white' : 'bg-gray-700 hover:bg-gray-600 text-red-400'}`}
            >
              {resetConfirm ? 'Confirm Reset' : 'Reset All Data'}
            </button>
            {resetConfirm && <span className="text-[10px] text-red-400">Click again to confirm. This will delete all health data.</span>}
            {resetStatus && <span className="text-[10px] text-gray-400">{resetStatus}</span>}
          </div>
        </div>
      )}

      <main className="flex-1 min-h-0 p-3 overflow-auto">
        <div className="grid grid-cols-4 grid-rows-[minmax(0,1fr)_minmax(0,1fr)] gap-3 h-[calc(100vh-8rem)]">
          <div className="col-span-2 min-h-0"><RealtimeHR /></div>
          <div className="min-h-0"><ActivitySummary locked={!hasAuth} connected={isConnected} /></div>
          <div className="min-h-0"><SpO2Chart locked={!hasAuth} connected={isConnected} /></div>

          <div className="min-h-0"><SleepChart locked={!hasAuth} connected={isConnected} /></div>
          <div className="min-h-0"><StressChart /></div>
          <div className="min-h-0"><HRVChart locked={!hasAuth} connected={isConnected} /></div>
          <div className="min-h-0"><HRHistory /></div>
        </div>
      </main>

      <div className="flex-none border-t border-gray-800">
        {aiEnabled && <AIAnalysis ollamaUrl={ollamaUrl} model={ollamaModel} days={aiDays} provider={aiProvider} />}
      </div>

      {/* Help Modal */}
      {showHelp && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setShowHelp(false)}>
          <div className="bg-gray-900 border border-gray-700 rounded-xl p-6 max-w-lg w-full mx-4 max-h-[80vh] overflow-auto" onClick={e => e.stopPropagation()}>
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-lg font-bold text-gray-100">Help</h2>
              <button onClick={() => setShowHelp(false)} className="text-gray-500 hover:text-gray-300 text-xl leading-none">&times;</button>
            </div>
            <div className="space-y-4 text-sm text-gray-300">
              <section>
                <h3 className="font-semibold text-gray-100 mb-1">Getting Started</h3>
                <ol className="list-decimal list-inside space-y-1 text-gray-400">
                  <li>Click <strong>BT Scan</strong> to find your Amazfit Helio Strap nearby</li>
                  <li>Select the device from the scan results to connect</li>
                  <li>An <strong>auth key</strong> is required for health data — set it in Settings</li>
                  <li>Activity, sleep, stress, and HRV data sync automatically on connect</li>
                </ol>
              </section>
              <section>
                <h3 className="font-semibold text-gray-100 mb-1">Data Panels</h3>
                <ul className="space-y-1 text-gray-400">
                  <li><strong>Heart Rate</strong> — Real-time BPM chart via BLE, updates each second</li>
                  <li><strong>Activity</strong> — Daily steps and calories from the device sensor</li>
                  <li><strong>SpO2</strong> — Blood oxygen saturation, collected during sleep or manually on device</li>
                  <li><strong>Sleep</strong> — Sleep stages (deep, light, REM, awake) with duration breakdown</li>
                  <li><strong>Stress</strong> — Stress level (0-100) measured every few minutes</li>
                  <li><strong>HRV</strong> — Heart rate variability (RMSSD) over time</li>
                  <li><strong>Heart Rate Log</strong> — Per-second BPM readings with timestamps</li>
                </ul>
              </section>
              <section>
                <h3 className="font-semibold text-gray-100 mb-1">Sync</h3>
                <p className="text-gray-400">
                  Real-time data (HR, steps, calories) flows automatically once connected.
                  Sync fetches historical data (SpO2, sleep, stress, HRV) from the device's internal storage.
                  This also runs automatically on connect and every 5 minutes.
                </p>
              </section>
              <section>
                <h3 className="font-semibold text-gray-100 mb-1">Auth Key</h3>
                <p className="text-gray-400">
                  The auth key is needed to unlock health data from the device. Extract it using
                  the <code className="text-gray-300 bg-gray-800 px-1 rounded">./extract_auth_key.sh</code> script
                  with an Android device running the Zepp app, then paste it into Settings.
                </p>
              </section>
              <section>
                <h3 className="font-semibold text-gray-100 mb-1">Export</h3>
                <p className="text-gray-400">
                  Use the Export button in Settings to download all health data as JSON for analysis.
                </p>
              </section>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function HRHistory() {
  const { data: wsData } = useWebSocket<{ timestamp: string; bpm: number }>('/ws/hr');
  const { data: apiData } = useHealthData<{ timestamp: string; bpm: number }>('/api/hr?limit=20', 5000);
  const tz = localStorage.getItem('tz') || Intl.DateTimeFormat().resolvedOptions().timeZone;

  // When live WS data is flowing, show only live readings (no stale API mix).
  // Fall back to API historical data only when WS has nothing yet.
  const wsRecent = wsData.slice(-40).reverse();
  let merged: { timestamp: string; bpm: number }[];
  if (wsRecent.length > 0) {
    // Live mode: dedup by second to prevent duplicate entries
    const seen = new Set<string>();
    merged = [];
    for (const r of wsRecent) {
      const sec = r.timestamp.slice(0, 19);
      if (!seen.has(sec)) {
        seen.add(sec);
        merged.push(r);
      }
      if (merged.length >= 20) break;
    }
  } else {
    merged = apiData.slice(0, 20);
  }

  return (
    <div className="bg-gray-900 rounded-xl p-3 h-full flex flex-col">
      <h2 className="text-xs font-semibold mb-2 text-gray-400 uppercase tracking-wide">
        Heart Rate Log<InfoTooltip text="Recent heart rate readings with timestamps. Updates each second via BLE. Green=normal (<100), Yellow=elevated (100-140), Red=high (>140)." />
      </h2>
      {merged.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-xs">No data</div>
      ) : (
        <div className="flex-1 overflow-auto space-y-0.5 text-xs">
          {merged.map((r, i) => (
            <div key={i} className="flex justify-between text-gray-400">
              <span>{new Date(r.timestamp).toLocaleTimeString([], { timeZone: tz, hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}</span>
              <span className={`font-medium ${getBpmColor(r.bpm)}`}>{r.bpm} bpm</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
