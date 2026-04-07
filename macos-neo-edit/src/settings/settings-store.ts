export interface Settings {
  fontSize: number;
  theme: 'light' | 'dark' | 'tokyo-night';
  wordWrap: 'off' | 'on' | 'wordWrapColumn' | 'bounded';
  wordWrapColumn: number;
  restoreWindowPosition: boolean;
}

const STORAGE_KEY = 'neo-edit-settings';

const defaults: Settings = {
  fontSize: 14,
  theme: 'tokyo-night',
  wordWrap: 'wordWrapColumn',
  wordWrapColumn: 80,
  restoreWindowPosition: true,
};

type SettingsListener = (settings: Settings) => void;
const listeners: SettingsListener[] = [];

function load(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) {
      return { ...defaults, ...JSON.parse(raw) };
    }
  } catch {
    // ignore
  }
  return { ...defaults };
}

function save(settings: Settings): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

let current = load();

export const settingsStore = {
  get(): Settings {
    return { ...current };
  },

  update(partial: Partial<Settings>): void {
    current = { ...current, ...partial };
    save(current);
    listeners.forEach((fn) => fn(current));
  },

  onChange(fn: SettingsListener): void {
    listeners.push(fn);
  },
};
