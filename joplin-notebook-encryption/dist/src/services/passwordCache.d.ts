/**
 * Password Cache Service
 * Manages in-memory caching of passwords with automatic expiration
 */
/**
 * Password Cache class for managing notebook passwords
 * Passwords are stored in memory only and never persisted
 */
export declare class PasswordCache {
    private cache;
    private timeoutMs;
    private timers;
    constructor(timeoutMinutes?: number);
    /**
     * Sets the cache timeout duration
     * @param minutes Timeout in minutes
     */
    setTimeout(minutes: number): void;
    /**
     * Gets the current timeout in minutes
     */
    getTimeout(): number;
    /**
     * Caches a password for a notebook
     * @param notebookId The notebook ID
     * @param password The password to cache
     */
    set(notebookId: string, password: string): void;
    /**
     * Gets a cached password for a notebook
     * Returns null if not cached or expired
     * @param notebookId The notebook ID
     */
    get(notebookId: string): string | null;
    /**
     * Checks if a notebook has a valid cached password
     * @param notebookId The notebook ID
     */
    has(notebookId: string): boolean;
    /**
     * Clears the cached password for a notebook
     * @param notebookId The notebook ID
     */
    clear(notebookId: string): void;
    /**
     * Clears all cached passwords
     */
    clearAll(): void;
    /**
     * Refreshes the expiry time for a cached password
     * Useful when the user is actively using the notebook
     * @param notebookId The notebook ID
     */
    refresh(notebookId: string): void;
    /**
     * Gets the remaining time until expiry in milliseconds
     * @param notebookId The notebook ID
     */
    getRemainingTime(notebookId: string): number;
    /**
     * Gets all currently cached notebook IDs
     */
    getCachedNotebookIds(): string[];
    /**
     * Schedules automatic cleanup when the cache expires
     */
    private scheduleCleanup;
    /**
     * Clears the timer for a notebook
     */
    private clearTimer;
}
/**
 * Gets the singleton password cache instance
 */
export declare function getPasswordCache(): PasswordCache;
/**
 * Resets the singleton instance (useful for testing)
 */
export declare function resetPasswordCache(): void;
//# sourceMappingURL=passwordCache.d.ts.map