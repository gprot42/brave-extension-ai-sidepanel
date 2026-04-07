/**
 * Plugin Settings Registration
 * Registers plugin settings with Joplin
 */

import joplin from 'api';
import { SettingItemType } from 'api/types';
import { CONSTANTS } from './types';
import { getPasswordCache } from './services/passwordCache';

/**
 * Setting keys used by the plugin
 */
export const SETTING_KEYS = {
  CACHE_TIMEOUT: 'encryptionCacheTimeout',
  ENCRYPTED_NOTEBOOKS: 'encryptedNotebooks',
  SHOW_LOCK_INDICATOR: 'showLockIndicator',
  CLEAR_CACHE_ON_LOCK: 'clearCacheOnLock',
  REQUIRE_PASSWORD_ON_SYNC: 'requirePasswordOnSync',
};

/**
 * Registers all plugin settings
 */
export async function registerSettings(): Promise<void> {
  // Register the settings section
  await joplin.settings.registerSection('notebookEncryption', {
    label: 'Notebook Encryption',
    iconName: 'fas fa-lock',
    description: 'Settings for notebook encryption plugin',
  });

  // Register individual settings
  await joplin.settings.registerSettings({
    [SETTING_KEYS.CACHE_TIMEOUT]: {
      value: CONSTANTS.DEFAULT_CACHE_TIMEOUT,
      type: SettingItemType.Int,
      section: 'notebookEncryption',
      public: true,
      label: 'Password cache timeout (minutes)',
      description:
        'How long to keep passwords cached in memory. Set to 0 to disable caching (will prompt for password every time).',
      minimum: 0,
      maximum: 60,
      step: 1,
    },

    [SETTING_KEYS.ENCRYPTED_NOTEBOOKS]: {
      value: '{}',
      type: SettingItemType.String,
      section: 'notebookEncryption',
      public: false, // Hidden from user, managed internally
      label: 'Encrypted notebooks configuration',
      description:
        'Internal storage for encrypted notebook configurations. Do not modify manually.',
    },

    [SETTING_KEYS.SHOW_LOCK_INDICATOR]: {
      value: true,
      type: SettingItemType.Bool,
      section: 'notebookEncryption',
      public: true,
      label: 'Show lock indicator',
      description: 'Show a lock icon (🔒) prefix on encrypted notebook names.',
    },

    [SETTING_KEYS.CLEAR_CACHE_ON_LOCK]: {
      value: true,
      type: SettingItemType.Bool,
      section: 'notebookEncryption',
      public: true,
      label: 'Clear cache on system lock',
      description: 'Automatically clear cached passwords when the computer is locked.',
    },

    [SETTING_KEYS.REQUIRE_PASSWORD_ON_SYNC]: {
      value: false,
      type: SettingItemType.Bool,
      section: 'notebookEncryption',
      public: true,
      label: 'Require password after sync',
      description: 'Prompt for password again after synchronization completes.',
    },
  });

  // Listen for setting changes
  await joplin.settings.onChange(handleSettingChange);
}

/**
 * Handles changes to plugin settings
 */
async function handleSettingChange(event: { keys: string[] }): Promise<void> {
  for (const key of event.keys) {
    switch (key) {
      case SETTING_KEYS.CACHE_TIMEOUT:
        await updateCacheTimeout();
        break;
      // Other setting changes can be handled here
    }
  }
}

/**
 * Updates the password cache timeout from settings
 */
async function updateCacheTimeout(): Promise<void> {
  const timeout = await joplin.settings.value(SETTING_KEYS.CACHE_TIMEOUT);
  const cache = getPasswordCache();
  cache.setTimeout(timeout as number);
}

/**
 * Gets the current cache timeout setting
 */
export async function getCacheTimeout(): Promise<number> {
  return (await joplin.settings.value(SETTING_KEYS.CACHE_TIMEOUT)) as number;
}

/**
 * Gets whether lock indicator should be shown
 */
export async function shouldShowLockIndicator(): Promise<boolean> {
  return (await joplin.settings.value(SETTING_KEYS.SHOW_LOCK_INDICATOR)) as boolean;
}

/**
 * Gets whether cache should be cleared on system lock
 */
export async function shouldClearCacheOnLock(): Promise<boolean> {
  return (await joplin.settings.value(SETTING_KEYS.CLEAR_CACHE_ON_LOCK)) as boolean;
}

/**
 * Gets whether password should be required after sync
 */
export async function shouldRequirePasswordOnSync(): Promise<boolean> {
  return (await joplin.settings.value(SETTING_KEYS.REQUIRE_PASSWORD_ON_SYNC)) as boolean;
}