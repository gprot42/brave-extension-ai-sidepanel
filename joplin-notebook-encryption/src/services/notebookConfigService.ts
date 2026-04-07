/**
 * Notebook Configuration Service
 * Manages encrypted notebook configurations
 */

import joplin from 'api';
import { NotebookConfig, CONSTANTS } from '../types';
import { generateSalt, createPasswordHash, verifyPassword } from './encryptionService';

/**
 * Converts Uint8Array to Base64 string
 */
function bytesToBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Converts Base64 string to Uint8Array
 */
function base64ToBytes(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/**
 * Notebook Configuration Service class
 */
export class NotebookConfigService {
  private configs: Record<string, NotebookConfig> = {};
  private loaded = false;

  /**
   * Loads configurations from Joplin settings
   */
  async load(): Promise<void> {
    try {
      const configJson = await joplin.settings.value('encryptedNotebooks');
      if (configJson) {
        this.configs = JSON.parse(configJson as string);
      }
      this.loaded = true;
    } catch (error) {
      console.error('Failed to load notebook encryption configs:', error);
      this.configs = {};
      this.loaded = true;
    }
  }

  /**
   * Saves configurations to Joplin settings
   */
  async save(): Promise<void> {
    try {
      const configJson = JSON.stringify(this.configs);
      await joplin.settings.setValue('encryptedNotebooks', configJson);
    } catch (error) {
      console.error('Failed to save notebook encryption configs:', error);
      throw error;
    }
  }

  /**
   * Ensures configurations are loaded
   */
  private async ensureLoaded(): Promise<void> {
    if (!this.loaded) {
      await this.load();
    }
  }

  /**
   * Checks if a notebook is encrypted
   * @param notebookId The notebook ID
   */
  async isEncrypted(notebookId: string): Promise<boolean> {
    await this.ensureLoaded();
    const config = this.configs[notebookId];
    return config ? config.enabled : false;
  }

  /**
   * Gets the configuration for a notebook
   * @param notebookId The notebook ID
   */
  async getConfig(notebookId: string): Promise<NotebookConfig | null> {
    await this.ensureLoaded();
    return this.configs[notebookId] || null;
  }

  /**
   * Enables encryption for a notebook
   * @param notebookId The notebook ID
   * @param password The password to use for encryption
   */
  async enableEncryption(notebookId: string, password: string): Promise<void> {
    await this.ensureLoaded();

    // Check if already encrypted
    if (this.configs[notebookId]?.enabled) {
      throw new Error('Notebook is already encrypted');
    }

    // Generate salt and create password hash for verification
    const salt = generateSalt();
    const passwordHash = await createPasswordHash(password, salt);

    // Create configuration
    const config: NotebookConfig = {
      id: notebookId,
      enabled: true,
      passwordHash,
      salt: bytesToBase64(salt),
      createdAt: Date.now(),
      version: CONSTANTS.ENCRYPTION_VERSION,
    };

    this.configs[notebookId] = config;
    await this.save();
  }

  /**
   * Disables encryption for a notebook
   * @param notebookId The notebook ID
   * @param password The password for verification
   */
  async disableEncryption(notebookId: string, password: string): Promise<void> {
    await this.ensureLoaded();

    const config = this.configs[notebookId];
    if (!config || !config.enabled) {
      throw new Error('Notebook is not encrypted');
    }

    // Verify password
    const isValid = await this.verifyPassword(notebookId, password);
    if (!isValid) {
      throw new Error('Invalid password');
    }

    // Remove configuration
    delete this.configs[notebookId];
    await this.save();
  }

  /**
   * Verifies a password for a notebook
   * @param notebookId The notebook ID
   * @param password The password to verify
   */
  async verifyPassword(notebookId: string, password: string): Promise<boolean> {
    await this.ensureLoaded();

    const config = this.configs[notebookId];
    if (!config) {
      return false;
    }

    const salt = base64ToBytes(config.salt);
    return verifyPassword(password, salt, config.passwordHash);
  }

  /**
   * Changes the password for an encrypted notebook
   * @param notebookId The notebook ID
   * @param oldPassword The current password
   * @param newPassword The new password
   */
  async changePassword(
    notebookId: string,
    oldPassword: string,
    newPassword: string
  ): Promise<void> {
    await this.ensureLoaded();

    const config = this.configs[notebookId];
    if (!config || !config.enabled) {
      throw new Error('Notebook is not encrypted');
    }

    // Verify old password
    const isValid = await this.verifyPassword(notebookId, oldPassword);
    if (!isValid) {
      throw new Error('Invalid current password');
    }

    // Generate new salt and hash
    const salt = generateSalt();
    const passwordHash = await createPasswordHash(newPassword, salt);

    // Update configuration
    config.salt = bytesToBase64(salt);
    config.passwordHash = passwordHash;
    await this.save();
  }

  /**
   * Gets all encrypted notebook IDs
   */
  async getAllEncryptedNotebooks(): Promise<string[]> {
    await this.ensureLoaded();
    return Object.keys(this.configs).filter((id) => this.configs[id].enabled);
  }

  /**
   * Updates the configuration for a notebook
   * Used internally for migrations or fixes
   * @param notebookId The notebook ID
   * @param updates Partial configuration updates
   */
  async updateConfig(notebookId: string, updates: Partial<NotebookConfig>): Promise<void> {
    await this.ensureLoaded();

    const config = this.configs[notebookId];
    if (!config) {
      throw new Error('Notebook configuration not found');
    }

    this.configs[notebookId] = { ...config, ...updates };
    await this.save();
  }

  /**
   * Reloads configurations from settings
   * Useful when settings are changed externally
   */
  async reload(): Promise<void> {
    this.loaded = false;
    await this.load();
  }
}

// Singleton instance
let instance: NotebookConfigService | null = null;

/**
 * Gets the singleton notebook config service instance
 */
export function getNotebookConfigService(): NotebookConfigService {
  if (!instance) {
    instance = new NotebookConfigService();
  }
  return instance;
}

/**
 * Resets the singleton instance (useful for testing)
 */
export function resetNotebookConfigService(): void {
  instance = null;
}