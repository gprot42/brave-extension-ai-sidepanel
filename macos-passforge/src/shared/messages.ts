import type { KdbxEntryData, ExtensionSettings, Credentials, LoginFormInfo } from './types';

// Messages from popup/content script -> background service worker
export type BackgroundMessage =
  | { type: 'IMPORT_DATABASE'; data: number[]; keyFileData?: number[] }
  | { type: 'REMOVE_DATABASE' }
  | { type: 'UNLOCK'; password: string; keyFileData?: number[] }
  | { type: 'LOCK' }
  | { type: 'GET_STATUS' }
  | { type: 'SEARCH_ENTRIES'; query: string; url?: string }
  | { type: 'GET_ENTRIES_FOR_URL'; url: string }
  | { type: 'AUTOFILL'; entry: Credentials; tabId: number }
  | { type: 'GET_SETTINGS' }
  | { type: 'UPDATE_SETTINGS'; settings: Partial<ExtensionSettings> }
  | { type: 'CONNECT_KEEPASSXC' }
  | { type: 'DISCONNECT_KEEPASSXC' };

// Responses from background -> popup
export type BackgroundResponse =
  | { success: true; data?: unknown }
  | { success: false; error: string };

export interface StatusResponse {
  hasDatabase: boolean;
  isUnlocked: boolean;
  mode: ExtensionSettings['mode'];
  entryCount?: number;
}

// Messages from background -> content script
export type ContentMessage =
  | { type: 'FILL_CREDENTIALS'; credentials: Credentials }
  | { type: 'DETECT_FORMS' }
  | { type: 'GET_FORM_INFO' };

// Messages from content script -> background
export type ContentToBackgroundMessage =
  | { type: 'FORMS_DETECTED'; forms: LoginFormInfo[] }
  | { type: 'PAGE_URL'; url: string };
