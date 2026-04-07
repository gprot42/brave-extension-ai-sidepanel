/**
 * Plugin-specific type definitions for Notebook Encryption
 */
/**
 * Configuration for an encrypted notebook
 */
export interface NotebookConfig {
    /** Notebook/folder ID */
    id: string;
    /** Is encryption enabled for this notebook */
    enabled: boolean;
    /** Hash of the password for verification (not the password itself) */
    passwordHash: string;
    /** Base64 encoded salt for key derivation */
    salt: string;
    /** Timestamp when encryption was enabled */
    createdAt: number;
    /** Encryption version for future migrations */
    version: number;
}
/**
 * Stored configuration for all encrypted notebooks
 */
export interface EncryptedNotebooksConfig {
    [notebookId: string]: NotebookConfig;
}
/**
 * Password cache entry
 */
export interface CacheEntry {
    /** The cached password */
    password: string;
    /** Timestamp when the cache expires */
    expiry: number;
}
/**
 * Encryption metadata stored with encrypted content
 */
export interface EncryptionMetadata {
    /** Version of encryption format */
    version: number;
    /** Algorithm identifier */
    algorithm: string;
    /** Base64 encoded salt */
    salt: string;
    /** Base64 encoded IV */
    iv: string;
    /** Base64 encoded ciphertext */
    ciphertext: string;
}
/**
 * Result of a decryption attempt
 */
export interface DecryptionResult {
    success: boolean;
    plaintext?: string;
    error?: string;
}
/**
 * Dialog types for password prompts
 */
export declare enum DialogType {
    /** Unlock existing encrypted notebook */
    Unlock = "unlock",
    /** Set up encryption for a notebook */
    Setup = "setup",
    /** Change password for encrypted notebook */
    ChangePassword = "change"
}
/**
 * Result from password dialog
 */
export interface PasswordDialogResult {
    /** Whether the user submitted the dialog (not cancelled) */
    submitted: boolean;
    /** The entered password */
    password?: string;
    /** New password (for change password dialog) */
    newPassword?: string;
}
/**
 * Plugin settings
 */
export interface PluginSettings {
    /** Cache timeout in minutes */
    cacheTimeout: number;
    /** JSON string of encrypted notebooks config */
    encryptedNotebooks: string;
    /** Show lock indicator on encrypted notebooks */
    showLockIndicator: boolean;
    /** Clear cache when computer is locked */
    clearCacheOnLock: boolean;
    /** Re-prompt for password after sync */
    requirePasswordOnSync: boolean;
}
/**
 * Constants for the plugin
 */
export declare const CONSTANTS: {
    /** Current encryption format version */
    readonly ENCRYPTION_VERSION: 1;
    /** Algorithm identifier */
    readonly ALGORITHM: "AES-256-GCM";
    /** PBKDF2 iteration count */
    readonly PBKDF2_ITERATIONS: 100000;
    /** Salt length in bytes */
    readonly SALT_LENGTH: 16;
    /** IV length in bytes for GCM */
    readonly IV_LENGTH: 12;
    /** Auth tag length in bytes for GCM */
    readonly AUTH_TAG_LENGTH: 16;
    /** Default cache timeout in minutes */
    readonly DEFAULT_CACHE_TIMEOUT: 10;
    /** Prefix for encrypted content */
    readonly ENCRYPTED_PREFIX: "🔒ENCRYPTED:";
};
//# sourceMappingURL=types.d.ts.map