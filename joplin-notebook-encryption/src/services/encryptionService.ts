/**
 * Encryption Service
 * Provides AES-256-GCM encryption and decryption using Web Crypto API
 */

import { CONSTANTS, EncryptionMetadata, DecryptionResult } from '../types';

/**
 * Converts a string to Uint8Array
 */
function stringToBytes(str: string): Uint8Array {
  return new TextEncoder().encode(str);
}

/**
 * Converts Uint8Array to string
 */
function bytesToString(bytes: Uint8Array): string {
  return new TextDecoder().decode(bytes);
}

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
 * Generates a cryptographically secure random salt
 */
export function generateSalt(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(CONSTANTS.SALT_LENGTH));
}

/**
 * Generates a cryptographically secure random IV
 */
export function generateIV(): Uint8Array {
  return crypto.getRandomValues(new Uint8Array(CONSTANTS.IV_LENGTH));
}

/**
 * Derives an encryption key from a password using PBKDF2
 */
export async function deriveKey(password: string, salt: Uint8Array): Promise<CryptoKey> {
  const passwordBytes = stringToBytes(password);
  
  // Import the password as a key
  const passwordKey = await crypto.subtle.importKey(
    'raw',
    passwordBytes.buffer as ArrayBuffer,
    'PBKDF2',
    false,
    ['deriveKey']
  );

  // Derive the actual encryption key
  return crypto.subtle.deriveKey(
    {
      name: 'PBKDF2',
      salt: salt.buffer as ArrayBuffer,
      iterations: CONSTANTS.PBKDF2_ITERATIONS,
      hash: 'SHA-256',
    },
    passwordKey,
    {
      name: 'AES-GCM',
      length: 256,
    },
    false, // not extractable
    ['encrypt', 'decrypt']
  );
}

/**
 * Creates a password verification hash
 * Used to verify password without storing it
 */
export async function createPasswordHash(password: string, salt: Uint8Array): Promise<string> {
  const key = await deriveKey(password, salt);
  
  // Encrypt a known value to create a verification hash
  const testData = stringToBytes('NOTEBOOK_ENCRYPTION_VERIFY');
  const iv = new Uint8Array(CONSTANTS.IV_LENGTH); // Zero IV for deterministic hash
  
  const encrypted = await crypto.subtle.encrypt(
    {
      name: 'AES-GCM',
      iv: iv.buffer as ArrayBuffer,
    },
    key,
    testData.buffer as ArrayBuffer
  );
  
  return bytesToBase64(new Uint8Array(encrypted));
}

/**
 * Verifies a password against a stored hash
 */
export async function verifyPassword(
  password: string, 
  salt: Uint8Array, 
  storedHash: string
): Promise<boolean> {
  try {
    const computedHash = await createPasswordHash(password, salt);
    return computedHash === storedHash;
  } catch {
    return false;
  }
}

/**
 * Encrypts plaintext using AES-256-GCM
 */
export async function encrypt(password: string, plaintext: string): Promise<string> {
  const salt = generateSalt();
  const iv = generateIV();
  const key = await deriveKey(password, salt);
  
  const plaintextBytes = stringToBytes(plaintext);
  
  const ciphertext = await crypto.subtle.encrypt(
    {
      name: 'AES-GCM',
      iv: iv.buffer as ArrayBuffer,
      tagLength: CONSTANTS.AUTH_TAG_LENGTH * 8, // in bits
    },
    key,
    plaintextBytes.buffer as ArrayBuffer
  );
  
  // Create metadata object
  const metadata: EncryptionMetadata = {
    version: CONSTANTS.ENCRYPTION_VERSION,
    algorithm: CONSTANTS.ALGORITHM,
    salt: bytesToBase64(salt),
    iv: bytesToBase64(iv),
    ciphertext: bytesToBase64(new Uint8Array(ciphertext)),
  };
  
  // Return as prefixed JSON string
  return CONSTANTS.ENCRYPTED_PREFIX + JSON.stringify(metadata);
}

/**
 * Decrypts ciphertext using AES-256-GCM
 */
export async function decrypt(password: string, encryptedData: string): Promise<DecryptionResult> {
  try {
    // Check for encryption prefix
    if (!encryptedData.startsWith(CONSTANTS.ENCRYPTED_PREFIX)) {
      return {
        success: false,
        error: 'Content is not encrypted or has invalid format',
      };
    }
    
    // Parse metadata
    const jsonData = encryptedData.slice(CONSTANTS.ENCRYPTED_PREFIX.length);
    const metadata: EncryptionMetadata = JSON.parse(jsonData);
    
    // Validate version
    if (metadata.version !== CONSTANTS.ENCRYPTION_VERSION) {
      return {
        success: false,
        error: `Unsupported encryption version: ${metadata.version}`,
      };
    }
    
    // Decode components
    const salt = base64ToBytes(metadata.salt);
    const iv = base64ToBytes(metadata.iv);
    const ciphertext = base64ToBytes(metadata.ciphertext);
    
    // Derive key and decrypt
    const key = await deriveKey(password, salt);
    
    const plaintextBytes = await crypto.subtle.decrypt(
      {
        name: 'AES-GCM',
        iv: iv.buffer as ArrayBuffer,
        tagLength: CONSTANTS.AUTH_TAG_LENGTH * 8,
      },
      key,
      ciphertext.buffer as ArrayBuffer
    );
    
    return {
      success: true,
      plaintext: bytesToString(new Uint8Array(plaintextBytes)),
    };
  } catch (error) {
    // GCM authentication failure typically means wrong password
    return {
      success: false,
      error: error instanceof Error ? error.message : 'Decryption failed - incorrect password?',
    };
  }
}

/**
 * Checks if content is encrypted
 */
export function isEncrypted(content: string): boolean {
  return content.startsWith(CONSTANTS.ENCRYPTED_PREFIX);
}

/**
 * Re-encrypts content with a new password
 */
export async function reencrypt(
  oldPassword: string, 
  newPassword: string, 
  encryptedData: string
): Promise<string> {
  const decryptResult = await decrypt(oldPassword, encryptedData);
  
  if (!decryptResult.success || !decryptResult.plaintext) {
    throw new Error(decryptResult.error || 'Failed to decrypt with old password');
  }
  
  return encrypt(newPassword, decryptResult.plaintext);
}