import React, { useState } from 'react';
import type { KdbxEntryData, Credentials } from '../../shared/types';

interface Props {
  entry: KdbxEntryData;
  onAutofill: (credentials: Credentials) => void;
}

export default function EntryItem({ entry, onAutofill }: Props) {
  const [copiedField, setCopiedField] = useState<string>('');
  const [expanded, setExpanded] = useState(false);

  async function handleCopy(text: string, field: string) {
    try {
      await navigator.clipboard.writeText(text);
      setCopiedField(field);
      setTimeout(() => setCopiedField(''), 2000);
    } catch {
      // Fallback
    }
  }

  function handleAutofill() {
    onAutofill({
      username: entry.username,
      password: entry.password,
    });
  }

  return (
    <div className="border-b border-gray-100 last:border-b-0">
      <div
        className="flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 cursor-pointer"
        onClick={handleAutofill}
      >
        <div className="w-8 h-8 bg-primary-100 rounded flex items-center justify-center flex-shrink-0">
          <span className="text-primary-700 text-xs font-bold">
            {entry.title.charAt(0).toUpperCase() || '?'}
          </span>
        </div>

        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-gray-900 truncate">{entry.title || 'Untitled'}</div>
          <div className="text-xs text-gray-500 truncate">{entry.username}</div>
        </div>

        {/* Quick action buttons */}
        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
            className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded"
            title="Details"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
              <path fillRule="evenodd" d={expanded ? "M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.938a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z" : "M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z"} clipRule="evenodd" />
            </svg>
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); handleCopy(entry.username, 'user'); }}
            className={`p-1.5 rounded ${copiedField === 'user' ? 'text-green-600 bg-green-50' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'}`}
            title="Copy username"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
              <path d="M13 4.5a2.5 2.5 0 11.702 1.737L6.97 9.604a2.518 2.518 0 010 .792l6.733 3.367a2.5 2.5 0 11-.671 1.341l-6.733-3.367a2.5 2.5 0 110-3.474l6.733-3.367A2.52 2.52 0 0113 4.5z" />
            </svg>
          </button>
          <button
            onClick={(e) => { e.stopPropagation(); handleCopy(entry.password, 'pass'); }}
            className={`p-1.5 rounded ${copiedField === 'pass' ? 'text-green-600 bg-green-50' : 'text-gray-400 hover:text-gray-600 hover:bg-gray-100'}`}
            title="Copy password"
          >
            <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-3.5 h-3.5">
              <path fillRule="evenodd" d="M15.988 3.012A2.25 2.25 0 0118 5.25v6.5A2.25 2.25 0 0115.75 14H13.5V7A2.5 2.5 0 0011 4.5H8.128a2.252 2.252 0 011.884-1.488A2.25 2.25 0 0112.25 1h1.5a2.25 2.25 0 012.238 2.012zM11.5 6.5V14H5.25A2.25 2.25 0 013 11.75v-3.5A2.25 2.25 0 015.25 6h6.25z" clipRule="evenodd" />
            </svg>
          </button>
        </div>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="px-4 pb-3 pl-15 text-xs space-y-1.5 bg-gray-50">
          <div className="pl-11">
            {entry.url && (
              <div className="flex items-center gap-1 text-gray-500">
                <span className="font-medium w-16">URL:</span>
                <a href={entry.url} target="_blank" rel="noopener noreferrer" className="text-primary-600 hover:underline truncate">
                  {entry.url}
                </a>
              </div>
            )}
            {entry.notes && (
              <div className="flex gap-1 text-gray-500 mt-1">
                <span className="font-medium w-16 flex-shrink-0">Notes:</span>
                <span className="text-gray-600 whitespace-pre-wrap break-words">{entry.notes}</span>
              </div>
            )}
            {entry.groupName && (
              <div className="flex items-center gap-1 text-gray-500 mt-1">
                <span className="font-medium w-16">Group:</span>
                <span className="text-gray-600">{entry.groupName}</span>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
