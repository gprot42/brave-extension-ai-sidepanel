/**
 * Plugin Settings Registration
 * Registers plugin settings with Joplin
 */
/**
 * Setting keys used by the plugin
 */
export declare const SETTING_KEYS: {
    CACHE_TIMEOUT: string;
    ENCRYPTED_NOTEBOOKS: string;
    SHOW_LOCK_INDICATOR: string;
    CLEAR_CACHE_ON_LOCK: string;
    REQUIRE_PASSWORD_ON_SYNC: string;
};
/**
 * Registers all plugin settings
 */
export declare function registerSettings(): Promise<void>;
/**
 * Gets the current cache timeout setting
 */
export declare function getCacheTimeout(): Promise<number>;
/**
 * Gets whether lock indicator should be shown
 */
export declare function shouldShowLockIndicator(): Promise<boolean>;
/**
 * Gets whether cache should be cleared on system lock
 */
export declare function shouldClearCacheOnLock(): Promise<boolean>;
/**
 * Gets whether password should be required after sync
 */
export declare function shouldRequirePasswordOnSync(): Promise<boolean>;
//# sourceMappingURL=settings.d.ts.map