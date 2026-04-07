export interface KdbxEntryData {
  uuid: string;
  title: string;
  username: string;
  password: string;
  url: string;
  notes: string;
  icon: number;
  groupName: string;
}

export interface KdbxGroupData {
  uuid: string;
  name: string;
  entries: KdbxEntryData[];
  groups: KdbxGroupData[];
}

export interface Credentials {
  username: string;
  password: string;
}

export interface LoginFormInfo {
  usernameField: { selector: string } | null;
  passwordField: { selector: string };
  formSelector: string | null;
}

export type ExtensionMode = 'standalone' | 'keepassxc';

export interface ExtensionSettings {
  mode: ExtensionMode;
  lockTimeoutMinutes: number;
  clipboardClearSeconds: number;
}

export const DEFAULT_SETTINGS: ExtensionSettings = {
  mode: 'standalone',
  lockTimeoutMinutes: 120,
  clipboardClearSeconds: 15,
};
