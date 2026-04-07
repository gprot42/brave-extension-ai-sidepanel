/**
 * Joplin Settings API interface
 */

import { SettingItem, SettingSection } from './types';

declare class JoplinSettings {
  /**
   * Registers a new setting section
   */
  registerSection(name: string, section: SettingSection): Promise<void>;

  /**
   * Registers a new setting
   */
  registerSetting(name: string, setting: SettingItem): Promise<void>;

  /**
   * Registers multiple settings at once
   */
  registerSettings(settings: Record<string, SettingItem>): Promise<void>;

  /**
   * Gets the value of a setting
   */
  value(name: string): Promise<unknown>;

  /**
   * Sets the value of a setting
   */
  setValue(name: string, value: unknown): Promise<void>;

  /**
   * Gets all global values
   */
  globalValue(name: string): Promise<unknown>;

  /**
   * Listens for changes to settings
   */
  onChange(callback: (event: { keys: string[] }) => void): Promise<void>;
}

export default JoplinSettings;