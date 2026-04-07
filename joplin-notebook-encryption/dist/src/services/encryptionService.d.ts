/**
 * Encryption Service
 * Provides AES-256-GCM encryption and decryption using Web Crypto API
 */
import { DecryptionResult } from '../types';
/**
 * Generates a cryptographically secure random salt
 */
export declare function generateSalt(): Uint8Array;
/**
 * Generates a cryptographically secure random IV
 */
export declare function generateIV(): Uint8Array;
/**
 * Derives an encryption key from a password using PBKDF2
 */
export declare function deriveKey(password: string, salt: Uint8Array): Promise<CryptoKey>;
/**
 * Creates a password verification hash
 * Used to verify password without storing it
 */
export declare function createPasswordHash(password: string, salt: Uint8Array): Promise<string>;
/**
 * Verifies a password against a stored hash
 */
export declare function verifyPassword(password: string, salt: Uint8Array, storedHash: string): Promise<boolean>;
/**
 * Encrypts plaintext using AES-256-GCM
 */
export declare function encrypt(password: string, plaintext: string): Promise<string>;
/**
 * Decrypts ciphertext using AES-256-GCM
 */
export declare function decrypt(password: string, encryptedData: string): Promise<DecryptionResult>;
/**
 * Checks if content is encrypted
 */
export declare function isEncrypted(content: string): boolean;
/**
 * Re-encrypts content with a new password
 */
export declare function reencrypt(oldPassword: string, newPassword: string, encryptedData: string): Promise<string>;
//# sourceMappingURL=encryptionService.d.ts.map