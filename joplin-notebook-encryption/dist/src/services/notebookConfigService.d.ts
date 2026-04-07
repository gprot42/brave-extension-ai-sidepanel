/**
 * Notebook Configuration Service
 * Manages encrypted notebook configurations
 */
import { NotebookConfig } from '../types';
/**
 * Notebook Configuration Service class
 */
export declare class NotebookConfigService {
    private configs;
    private loaded;
    /**
     * Loads configurations from Joplin settings
     */
    load(): Promise<void>;
    /**
     * Saves configurations to Joplin settings
     */
    save(): Promise<void>;
    /**
     * Ensures configurations are loaded
     */
    private ensureLoaded;
    /**
     * Checks if a notebook is encrypted
     * @param notebookId The notebook ID
     */
    isEncrypted(notebookId: string): Promise<boolean>;
    /**
     * Gets the configuration for a notebook
     * @param notebookId The notebook ID
     */
    getConfig(notebookId: string): Promise<NotebookConfig | null>;
    /**
     * Enables encryption for a notebook
     * @param notebookId The notebook ID
     * @param password The password to use for encryption
     */
    enableEncryption(notebookId: string, password: string): Promise<void>;
    /**
     * Disables encryption for a notebook
     * @param notebookId The notebook ID
     * @param password The password for verification
     */
    disableEncryption(notebookId: string, password: string): Promise<void>;
    /**
     * Verifies a password for a notebook
     * @param notebookId The notebook ID
     * @param password The password to verify
     */
    verifyPassword(notebookId: string, password: string): Promise<boolean>;
    /**
     * Changes the password for an encrypted notebook
     * @param notebookId The notebook ID
     * @param oldPassword The current password
     * @param newPassword The new password
     */
    changePassword(notebookId: string, oldPassword: string, newPassword: string): Promise<void>;
    /**
     * Gets all encrypted notebook IDs
     */
    getAllEncryptedNotebooks(): Promise<string[]>;
    /**
     * Updates the configuration for a notebook
     * Used internally for migrations or fixes
     * @param notebookId The notebook ID
     * @param updates Partial configuration updates
     */
    updateConfig(notebookId: string, updates: Partial<NotebookConfig>): Promise<void>;
    /**
     * Reloads configurations from settings
     * Useful when settings are changed externally
     */
    reload(): Promise<void>;
}
/**
 * Gets the singleton notebook config service instance
 */
export declare function getNotebookConfigService(): NotebookConfigService;
/**
 * Resets the singleton instance (useful for testing)
 */
export declare function resetNotebookConfigService(): void;
//# sourceMappingURL=notebookConfigService.d.ts.map