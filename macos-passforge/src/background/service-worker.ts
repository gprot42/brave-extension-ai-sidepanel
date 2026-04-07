import type { BackgroundMessage, StatusResponse, BackgroundResponse } from '../shared/messages';
import type { Credentials } from '../shared/types';
import {
  importDatabase,
  removeDatabase,
  hasDatabase,
  unlockDatabase,
  lockDatabase,
  isUnlocked,
  searchEntries,
  getEntriesForUrl,
  getEntryCount,
} from './kdbx-manager';
import {
  loadSettings,
  saveSettings,
  getSettings,
  resetLockTimer,
  clearLockTimer,
  setupIdleListener,
  saveSessionCredentials,
  clearSessionCredentials,
  tryRestoreSession,
} from './auto-lock';
import {
  connectKeePassXC,
  disconnectKeePassXC,
  getLoginsForUrl,
  isKeePassXCConnected,
} from './native-messaging';

// Initialize on service worker start (including restarts)
loadSettings().then(async () => {
  setupIdleListener();
  // Try to restore unlocked state from session credentials
  await tryRestoreSession();
});

// Update badge when tab changes
chrome.tabs.onActivated.addListener(async (activeInfo) => {
  try {
    const tab = await chrome.tabs.get(activeInfo.tabId);
    await updateBadge(tab);
  } catch {
    // Tab may no longer exist
  }
});

chrome.tabs.onUpdated.addListener(async (_tabId, changeInfo, tab) => {
  if (changeInfo.url || changeInfo.status === 'complete') {
    await updateBadge(tab);
  }
});

async function updateBadge(tab: chrome.tabs.Tab): Promise<void> {
  if (!tab.id || !tab.url) {
    await chrome.action.setBadgeText({ text: '' });
    return;
  }

  if (!isUnlocked()) {
    await chrome.action.setBadgeText({ text: '', tabId: tab.id });
    return;
  }

  const entries = getEntriesForUrl(tab.url);
  const count = entries.length;
  await chrome.action.setBadgeText({
    text: count > 0 ? String(count) : '',
    tabId: tab.id,
  });
  await chrome.action.setBadgeBackgroundColor({
    color: '#3b82f6',
    tabId: tab.id,
  });
}

// Message handler
chrome.runtime.onMessage.addListener(
  (message: BackgroundMessage, _sender, sendResponse: (response: BackgroundResponse) => void) => {
    handleMessage(message)
      .then(sendResponse)
      .catch((err) => sendResponse({ success: false, error: String(err.message ?? err) }));
    return true; // Keep channel open for async response
  }
);

async function handleMessage(message: BackgroundMessage): Promise<BackgroundResponse> {
  resetLockTimer();

  switch (message.type) {
    case 'IMPORT_DATABASE': {
      const data = new Uint8Array(message.data).buffer;
      const keyFile = message.keyFileData
        ? new Uint8Array(message.keyFileData).buffer
        : undefined;
      await importDatabase(data, keyFile);
      return { success: true };
    }

    case 'REMOVE_DATABASE': {
      await removeDatabase();
      await clearSessionCredentials();
      return { success: true };
    }

    case 'UNLOCK': {
      const keyFile = message.keyFileData
        ? new Uint8Array(message.keyFileData).buffer
        : undefined;
      const count = await unlockDatabase(message.password, keyFile);
      // Persist credentials in session storage for SW restart recovery
      await saveSessionCredentials(message.password);
      resetLockTimer();
      // Update badge for current tab
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tab) await updateBadge(tab);
      return { success: true, data: { entryCount: count } };
    }

    case 'LOCK': {
      lockDatabase();
      clearLockTimer();
      await clearSessionCredentials();
      return { success: true };
    }

    case 'GET_STATUS': {
      // Try to restore session if SW was restarted
      if (!isUnlocked()) {
        await tryRestoreSession();
      }
      const dbExists = await hasDatabase();
      const settings = getSettings();
      const status: StatusResponse = {
        hasDatabase: dbExists,
        isUnlocked: isUnlocked(),
        mode: settings.mode,
        entryCount: isUnlocked() ? getEntryCount() : undefined,
      };
      return { success: true, data: status };
    }

    case 'SEARCH_ENTRIES': {
      if (!isUnlocked()) await tryRestoreSession();
      const settings = getSettings();
      if (settings.mode === 'keepassxc' && isKeePassXCConnected() && message.url) {
        const entries = await getLoginsForUrl(message.url);
        return { success: true, data: entries };
      }
      const entries = searchEntries(message.query, message.url);
      return { success: true, data: entries };
    }

    case 'GET_ENTRIES_FOR_URL': {
      if (!isUnlocked()) await tryRestoreSession();
      const settings = getSettings();
      if (settings.mode === 'keepassxc' && isKeePassXCConnected()) {
        const entries = await getLoginsForUrl(message.url);
        return { success: true, data: entries };
      }
      const entries = getEntriesForUrl(message.url);
      return { success: true, data: entries };
    }

    case 'AUTOFILL': {
      const tabId = message.tabId;

      // Ensure content script is injected in all frames (handles tabs opened before extension load)
      try {
        await chrome.scripting.executeScript({
          target: { tabId, allFrames: true },
          files: ['content-script.js'],
        });
      } catch {
        // Script may already be injected or page may not allow injection
      }

      // Small delay to let the injected script initialize
      await new Promise((resolve) => setTimeout(resolve, 150));

      try {
        const response = await chrome.tabs.sendMessage(tabId, {
          type: 'FILL_CREDENTIALS',
          credentials: message.entry,
        });
        if (response && response.success) {
          return { success: true };
        }
        return { success: false, error: 'Could not fill credentials. No login form found on this page.' };
      } catch (err) {
        return { success: false, error: 'Could not reach the page. Please refresh the page and try again.' };
      }
    }

    case 'GET_SETTINGS': {
      const settings = getSettings();
      return { success: true, data: settings };
    }

    case 'UPDATE_SETTINGS': {
      const updated = await saveSettings(message.settings);
      return { success: true, data: updated };
    }

    case 'CONNECT_KEEPASSXC': {
      await connectKeePassXC();
      return { success: true };
    }

    case 'DISCONNECT_KEEPASSXC': {
      disconnectKeePassXC();
      return { success: true };
    }

    default:
      return { success: false, error: 'Unknown message type' };
  }
}
