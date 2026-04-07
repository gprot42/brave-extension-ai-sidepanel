import { lockDatabase, isUnlocked, unlockDatabase } from './kdbx-manager';
import { DEFAULT_SETTINGS, type ExtensionSettings } from '../shared/types';

let settings: ExtensionSettings = { ...DEFAULT_SETTINGS };

export async function loadSettings(): Promise<ExtensionSettings> {
  const result = await chrome.storage.local.get('settings');
  if (result.settings) {
    settings = { ...DEFAULT_SETTINGS, ...result.settings };
  }
  return settings;
}

export async function saveSettings(partial: Partial<ExtensionSettings>): Promise<ExtensionSettings> {
  settings = { ...settings, ...partial };
  await chrome.storage.local.set({ settings });
  return settings;
}

export function getSettings(): ExtensionSettings {
  return settings;
}

// --- Session credential persistence for MV3 SW restarts ---

interface SessionData {
  password: string;
  unlockTimestamp: number;
}

export async function saveSessionCredentials(password: string): Promise<void> {
  const data: SessionData = {
    password,
    unlockTimestamp: Date.now(),
  };
  await chrome.storage.session.set({ sessionData: data });
}

export async function clearSessionCredentials(): Promise<void> {
  await chrome.storage.session.remove('sessionData');
}

/**
 * Try to restore the unlocked state after a service worker restart.
 * Returns true if the database was re-unlocked from session credentials.
 */
export async function tryRestoreSession(): Promise<boolean> {
  if (isUnlocked()) return true;

  try {
    const result = await chrome.storage.session.get('sessionData');
    const data = result.sessionData as SessionData | undefined;
    if (!data?.password || !data.unlockTimestamp) return false;

    // Check if the session has expired
    if (settings.lockTimeoutMinutes > 0) {
      const elapsed = Date.now() - data.unlockTimestamp;
      const timeoutMs = settings.lockTimeoutMinutes * 60 * 1000;
      if (elapsed >= timeoutMs) {
        await clearSessionCredentials();
        return false;
      }
    }

    // Re-unlock the database
    await unlockDatabase(data.password);
    return true;
  } catch {
    await clearSessionCredentials();
    return false;
  }
}

// --- Lock management ---

export function resetLockTimer(): void {
  // In MV3, setTimeout is unreliable because the SW can be terminated.
  // Lock expiration is checked via timestamp in tryRestoreSession() instead.
  // We still set an alarm as a best-effort lock trigger while the SW is alive.
  chrome.alarms.clear('lockTimer').catch(() => {});

  if (isUnlocked() && settings.lockTimeoutMinutes > 0) {
    chrome.alarms.create('lockTimer', {
      delayInMinutes: settings.lockTimeoutMinutes,
    });
  }
}

export function clearLockTimer(): void {
  chrome.alarms.clear('lockTimer').catch(() => {});
}

export function setupIdleListener(): void {
  // Set idle detection to the lock timeout (minimum 15 seconds per Chrome API)
  const idleSeconds = settings.lockTimeoutMinutes > 0
    ? Math.max(settings.lockTimeoutMinutes * 60, 15)
    : 0;

  if (idleSeconds > 0) {
    chrome.idle.setDetectionInterval(idleSeconds);
    chrome.idle.onStateChanged.addListener((state) => {
      // Only lock on system lock (screen lock), not on idle
      // Idle-based expiration is handled by timestamp checks
      if (state === 'locked') {
        if (isUnlocked()) {
          lockDatabase();
          clearLockTimer();
          clearSessionCredentials();
        }
      }
    });
  }

  // Alarm listener for lock timeout (survives SW restarts better than setTimeout)
  chrome.alarms.onAlarm.addListener(async (alarm) => {
    if (alarm.name === 'lockTimer') {
      if (isUnlocked()) {
        lockDatabase();
      }
      await clearSessionCredentials();
    }
  });
}
