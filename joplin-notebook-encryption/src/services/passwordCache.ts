/**
 * Password Cache Service
 * Manages in-memory caching of passwords with automatic expiration
 */

import { CacheEntry, CONSTANTS } from '../types';

/**
 * Password Cache class for managing notebook passwords
 * Passwords are stored in memory only and never persisted
 */
export class PasswordCache {
  private cache: Map<string, CacheEntry> = new Map();
  private timeoutMs: number;
  private timers: Map<string, ReturnType<typeof setTimeout>> = new Map();

  constructor(timeoutMinutes: number = CONSTANTS.DEFAULT_CACHE_TIMEOUT) {
    this.timeoutMs = timeoutMinutes * 60 * 1000;
  }

  /**
   * Sets the cache timeout duration
   * @param minutes Timeout in minutes
   */
  setTimeout(minutes: number): void {
    this.timeoutMs = minutes * 60 * 1000;
  }

  /**
   * Gets the current timeout in minutes
   */
  getTimeout(): number {
    return this.timeoutMs / 60 / 1000;
  }

  /**
   * Caches a password for a notebook
   * @param notebookId The notebook ID
   * @param password The password to cache
   */
  set(notebookId: string, password: string): void {
    // Clear any existing timer for this notebook
    this.clearTimer(notebookId);

    const expiry = Date.now() + this.timeoutMs;
    this.cache.set(notebookId, { password, expiry });

    // Schedule automatic cleanup
    this.scheduleCleanup(notebookId);
  }

  /**
   * Gets a cached password for a notebook
   * Returns null if not cached or expired
   * @param notebookId The notebook ID
   */
  get(notebookId: string): string | null {
    const entry = this.cache.get(notebookId);
    
    if (!entry) {
      return null;
    }

    // Check if expired
    if (Date.now() > entry.expiry) {
      this.clear(notebookId);
      return null;
    }

    return entry.password;
  }

  /**
   * Checks if a notebook has a valid cached password
   * @param notebookId The notebook ID
   */
  has(notebookId: string): boolean {
    return this.get(notebookId) !== null;
  }

  /**
   * Clears the cached password for a notebook
   * @param notebookId The notebook ID
   */
  clear(notebookId: string): void {
    this.clearTimer(notebookId);
    this.cache.delete(notebookId);
  }

  /**
   * Clears all cached passwords
   */
  clearAll(): void {
    // Clear all timers
    for (const timerId of this.timers.values()) {
      clearTimeout(timerId);
    }
    this.timers.clear();
    this.cache.clear();
  }

  /**
   * Refreshes the expiry time for a cached password
   * Useful when the user is actively using the notebook
   * @param notebookId The notebook ID
   */
  refresh(notebookId: string): void {
    const entry = this.cache.get(notebookId);
    if (entry) {
      this.set(notebookId, entry.password);
    }
  }

  /**
   * Gets the remaining time until expiry in milliseconds
   * @param notebookId The notebook ID
   */
  getRemainingTime(notebookId: string): number {
    const entry = this.cache.get(notebookId);
    if (!entry) {
      return 0;
    }
    return Math.max(0, entry.expiry - Date.now());
  }

  /**
   * Gets all currently cached notebook IDs
   */
  getCachedNotebookIds(): string[] {
    const ids: string[] = [];
    for (const [notebookId] of this.cache) {
      if (this.has(notebookId)) {
        ids.push(notebookId);
      }
    }
    return ids;
  }

  /**
   * Schedules automatic cleanup when the cache expires
   */
  private scheduleCleanup(notebookId: string): void {
    const timer = setTimeout(() => {
      this.cache.delete(notebookId);
      this.timers.delete(notebookId);
    }, this.timeoutMs);

    this.timers.set(notebookId, timer);
  }

  /**
   * Clears the timer for a notebook
   */
  private clearTimer(notebookId: string): void {
    const timer = this.timers.get(notebookId);
    if (timer) {
      clearTimeout(timer);
      this.timers.delete(notebookId);
    }
  }
}

// Singleton instance
let instance: PasswordCache | null = null;

/**
 * Gets the singleton password cache instance
 */
export function getPasswordCache(): PasswordCache {
  if (!instance) {
    instance = new PasswordCache();
  }
  return instance;
}

/**
 * Resets the singleton instance (useful for testing)
 */
export function resetPasswordCache(): void {
  if (instance) {
    instance.clearAll();
    instance = null;
  }
}