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

      <main className="flex-1 min-h-0 p-3 grid grid-cols-4 grid-rows-2 gap-3">
        <div className="col-span-2"><RealtimeHR /></div>
        <div><ActivitySummary locked={!hasAuth} connected={isConnected} /></div>
        <div><SpO2Chart locked={!hasAuth} connected={isConnected} /></div>

        <div><SleepChart locked={!hasAuth} connected={isConnected} /></div>
        <div><StressChart /></div>
        <div><HRVChart locked={!hasAuth} connected={isConnected} /></div>
        <div><HRHistory /></div>
      </main>
    </div>
  );
}

function HRHistory() {
  const { data: apiData } = useHealthData<{ timestamp: string; bpm: number }>('/api/hr?limit=20', 1000);
  const tz = localStorage.getItem('tz') || Intl.DateTimeFormat().resolvedOptions().timeZone;

  return (
    <div className="bg-gray-900 rounded-xl p-3 h-full flex flex-col">
      <h2 className="text-xs font-semibold mb-2 text-gray-400 uppercase tracking-wide">
        Heart Rate Log<InfoTooltip text="Recent heart rate readings with timestamps. Updates each second via BLE. Green=normal (<100), Yellow=elevated (100-140), Red=high (>140)." />
      </h2>
      {apiData.length === 0 ? (
        <div className="flex-1 flex items-center justify-center text-gray-600 text-xs">No data</div>
      ) : (
        <div className="flex-1 overflow-auto space-y-0.5 text-xs">
          {apiData.slice(0, 20).map((r, i) => (
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
