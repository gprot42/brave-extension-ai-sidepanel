import { useHealthData } from '../hooks/useHealthData';
import type { DeviceStatus } from '../types';
import { useState } from 'react';

interface ScannedDevice {
  name: string;
  address: string;
  rssi: number;
}

export default function DeviceStatusPanel() {
  const { data, refetch } = useHealthData<DeviceStatus>('/api/device', 3000);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [scanResults, setScanResults] = useState<ScannedDevice[] | null>(null);

  const status = data.length > 0 ? data[0] : null;
  const deviceState = status?.state ?? 'DISCONNECTED';
  const isConnected = deviceState === 'CONNECTED';
  const isConnecting = deviceState === 'CONNECTING';
  const isAuthenticating = deviceState === 'AUTHENTICATING';
  const isError = deviceState === 'ERROR';
  const isBusy = isConnecting || isAuthenticating || busy;
  const hasDevice = !!status?.device_id;

  // Use backend error_message or local error
  const displayError = error || (isError ? status?.error_message : null);

  const handleScan = async () => {
    setScanning(true);
    setError(null);
    setScanResults(null);
    try {
      const res = await fetch('/api/scan');
      if (!res.ok) throw new Error('Scan failed');
      const devices: ScannedDevice[] = await res.json();
      setScanResults(devices);
      if (devices.length === 0) {
        setError('No Helio Strap found. Make sure it is nearby and not connected to the Zepp app.');
      }
    } catch {
      setError('Scan failed — is Bluetooth enabled?');
    } finally {
      setScanning(false);
    }
  };

  const handleConnectTo = async (address: string) => {
    setBusy(true);
    setError(null);
    setScanResults(null);
    try {
      const res = await fetch(`/api/connect?device_id=${encodeURIComponent(address)}`, { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: 'Connection failed' }));
        setError(body.detail || 'Connection failed');
      }
    } catch {
      setError('Server unreachable');
    } finally {
      setBusy(false);
      refetch();
    }
  };

  const handleConnect = async () => {
    if (!hasDevice) {
      // No cached device — trigger scan instead
      handleScan();
      return;
    }
    setBusy(true);
    setError(null);
    setScanResults(null);
    try {
      const res = await fetch('/api/connect', { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({ detail: 'Connection failed' }));
        setError(body.detail || 'Connection failed');
      }
    } catch {
      setError('Server unreachable');
    } finally {
      setBusy(false);
      refetch();
    }
  };

  const handleDisconnect = async () => {
    setBusy(true);
    setError(null);
    try {
      await fetch('/api/disconnect', { method: 'POST' });
    } catch {
      setError('Server unreachable');
    } finally {
      setBusy(false);
      refetch();
    }
  };

  const handleSync = async () => {
    setBusy(true);
    try {
      await fetch('/api/sync', { method: 'POST' });
    } finally {
      setBusy(false);
      refetch();
    }
  };

  // State indicator color and text
  const stateColor = isConnected
    ? 'bg-green-400'
    : isError
      ? 'bg-red-400'
      : (isConnecting || isAuthenticating)
        ? 'bg-amber-400 animate-pulse'
        : 'bg-gray-600';

  const stateTextColor = isConnected
    ? 'text-green-400'
    : isError
      ? 'text-red-400'
      : (isConnecting || isAuthenticating)
        ? 'text-amber-400'
        : 'text-gray-500';

  const stateLabel = isConnecting
    ? 'CONNECTING...'
    : isAuthenticating
      ? 'AUTHENTICATING...'
      : isError
        ? 'ERROR'
        : deviceState;

  return (
    <div className="relative">
      <div className="flex items-center gap-3 text-xs">
        {/* Error banner */}
        {displayError && (
          <div className="flex items-center gap-1.5 bg-red-950/60 border border-red-800/50 rounded-lg px-3 py-1.5 max-w-[400px]">
            <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-red-400 flex-shrink-0">
              <circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>
            </svg>
            <span className="text-red-300 text-[11px] leading-tight">{displayError}</span>
            <button
              onClick={() => setError(null)}
              className="text-red-500 hover:text-red-300 ml-1 flex-shrink-0"
            >
              &times;
            </button>
          </div>
        )}

        {/* Battery */}
        {status?.battery_level != null && (
          <span className="text-gray-400">Battery {status.battery_level}%</span>
        )}

        {/* State indicator */}
        <span className={`flex items-center gap-1.5 ${stateTextColor}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${stateColor}`} />
          <span className="text-[11px] font-medium">{stateLabel}</span>
        </span>

        {/* BT Scan — only when not connected */}
        {!isConnected && !isConnecting && !isAuthenticating && (
          <button
            onClick={handleScan}
            disabled={scanning || isBusy}
            className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 text-sm disabled:opacity-50"
          >
            {scanning ? (
              <span className="flex items-center gap-1.5">
                <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                Scanning...
              </span>
            ) : 'BT Scan'}
          </button>
        )}

        {/* Sync — only when connected */}
        {isConnected && (
          <button
            onClick={handleSync}
            disabled={isBusy}
            className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 rounded-lg text-gray-300 text-sm disabled:opacity-50"
          >
            Sync
          </button>
        )}

        {/* Connect / Disconnect */}
        {isConnected ? (
          <button
            onClick={handleDisconnect}
            disabled={isBusy}
            className="px-5 py-1.5 rounded-lg text-sm font-medium disabled:opacity-50 bg-gray-800 hover:bg-gray-700 text-gray-300"
          >
            Disconnect
          </button>
        ) : (
          <button
            onClick={handleConnect}
            disabled={isBusy || scanning}
            className={`px-5 py-1.5 rounded-lg text-sm font-medium disabled:opacity-50 ${
              isConnecting || isAuthenticating
                ? 'bg-amber-700 text-amber-100'
                : 'bg-green-600 hover:bg-green-500 text-white'
            }`}
          >
            {isConnecting ? (
              <span className="flex items-center gap-1.5">
                <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                Connecting...
              </span>
            ) : isAuthenticating ? (
              <span className="flex items-center gap-1.5">
                <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24"><circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none"/><path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/></svg>
                Authenticating...
              </span>
            ) : hasDevice ? 'Connect' : 'BT Scan & Connect'}
          </button>
        )}
      </div>

      {/* Scan results dropdown */}
      {scanResults && scanResults.length > 0 && (
        <div className="absolute right-0 top-full mt-2 bg-gray-800 border border-gray-700 rounded-lg shadow-xl z-50 min-w-[300px]">
          <div className="px-3 py-2 border-b border-gray-700 flex items-center justify-between">
            <span className="text-xs text-gray-400 font-semibold uppercase tracking-wide">
              Found {scanResults.length} device{scanResults.length > 1 ? 's' : ''}
            </span>
            <span className="text-[10px] text-gray-500">Select to connect</span>
          </div>
          {scanResults.map((d) => (
            <button
              key={d.address}
              onClick={() => handleConnectTo(d.address)}
              disabled={isBusy}
              className="w-full px-3 py-2.5 text-left hover:bg-gray-700 flex items-center justify-between text-sm border-b border-gray-700/50 last:border-0 disabled:opacity-50"
            >
              <div>
                <div className="text-gray-200 font-medium">{d.name}</div>
                <div className="text-[10px] text-gray-500 font-mono mt-0.5">{d.address}</div>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-[10px] text-gray-500">{d.rssi} dBm</span>
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-green-500">
                  <polyline points="9 18 15 12 9 6"/>
                </svg>
              </div>
            </button>
          ))}
          <button
            onClick={() => setScanResults(null)}
            className="w-full px-3 py-1.5 text-xs text-gray-500 hover:text-gray-300 border-t border-gray-700"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
}
