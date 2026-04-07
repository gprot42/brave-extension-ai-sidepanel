import React, { useRef, useState } from 'react';

interface Props {
  onImported: () => void;
}

export default function ImportDb({ onImported }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [dbFileName, setDbFileName] = useState('');
  const [keyFileName, setKeyFileName] = useState('');
  const [dbReady, setDbReady] = useState(false);
  const dbFileRef = useRef<HTMLInputElement>(null);
  const keyFileRef = useRef<HTMLInputElement>(null);
  const dbDataRef = useRef<number[] | null>(null);
  const keyDataRef = useRef<number[] | null>(null);

  function handleDbFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setDbFileName(file.name);
    setDbReady(false);
    const reader = new FileReader();
    reader.onload = () => {
      dbDataRef.current = Array.from(new Uint8Array(reader.result as ArrayBuffer));
      setDbReady(true);
    };
    reader.readAsArrayBuffer(file);
  }

  function handleKeyFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setKeyFileName(file.name);
    const reader = new FileReader();
    reader.onload = () => {
      keyDataRef.current = Array.from(new Uint8Array(reader.result as ArrayBuffer));
    };
    reader.readAsArrayBuffer(file);
  }

  async function handleImport() {
    if (!dbDataRef.current) {
      setError('Please select a .kdbx file');
      return;
    }

    setLoading(true);
    setError('');

    try {
      const message: Record<string, unknown> = {
        type: 'IMPORT_DATABASE',
        data: dbDataRef.current,
      };
      if (keyDataRef.current) {
        message.keyFileData = keyDataRef.current;
      }

      const response = await chrome.runtime.sendMessage(message);
      if (response.success) {
        onImported();
      } else {
        setError(response.error || 'Import failed');
      }
    } catch (err) {
      setError('Failed to import database');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-4 flex flex-col gap-4">
      <div className="text-center py-6">
        <div className="w-16 h-16 bg-primary-100 rounded-full flex items-center justify-center mx-auto mb-3">
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" className="w-8 h-8 text-primary-600">
            <path fillRule="evenodd" d="M12 1.5a5.25 5.25 0 00-5.25 5.25v3a3 3 0 00-3 3v6.75a3 3 0 003 3h10.5a3 3 0 003-3v-6.75a3 3 0 00-3-3v-3c0-2.9-2.35-5.25-5.25-5.25zm3.75 8.25v-3a3.75 3.75 0 10-7.5 0v3h7.5z" clipRule="evenodd" />
          </svg>
        </div>
        <h2 className="text-lg font-semibold text-gray-900">Import Database</h2>
        <p className="text-sm text-gray-500 mt-1">Select your KeePass .kdbx file to get started</p>
      </div>

      {/* KDBX file picker */}
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Database file (.kdbx) *
        </label>
        <div
          onClick={() => dbFileRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded-lg p-3 text-center cursor-pointer hover:border-primary-400 hover:bg-primary-50 transition-colors"
        >
          <input
            ref={dbFileRef}
            type="file"
            accept=".kdbx"
            onChange={handleDbFile}
            className="hidden"
          />
          {dbFileName ? (
            <span className="text-sm text-gray-700">{dbFileName}</span>
          ) : (
            <span className="text-sm text-gray-400">Click to select .kdbx file</span>
          )}
        </div>
      </div>

      {/* Key file picker */}
      <div>
        <label className="block text-xs font-medium text-gray-700 mb-1">
          Key file (.key / .keyx) - optional
        </label>
        <div
          onClick={() => keyFileRef.current?.click()}
          className="border-2 border-dashed border-gray-300 rounded-lg p-3 text-center cursor-pointer hover:border-gray-400 transition-colors"
        >
          <input
            ref={keyFileRef}
            type="file"
            accept=".key,.keyx"
            onChange={handleKeyFile}
            className="hidden"
          />
          {keyFileName ? (
            <span className="text-sm text-gray-700">{keyFileName}</span>
          ) : (
            <span className="text-sm text-gray-400">Click to select key file</span>
          )}
        </div>
      </div>

      {error && (
        <p className="text-xs text-red-600">{error}</p>
      )}

      <button
        onClick={handleImport}
        disabled={loading || !dbReady}
        className="w-full py-2.5 bg-primary-600 text-white text-sm font-medium rounded-lg hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? 'Importing...' : 'Import Database'}
      </button>
    </div>
  );
}
