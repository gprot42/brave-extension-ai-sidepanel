/**
 * Plugin Commands
 * Registers commands and context menu actions for notebook encryption
 */
/**
 * Command names
 */
export declare const COMMANDS: {
    ENABLE_ENCRYPTION: string;
    DISABLE_ENCRYPTION: string;
    CHANGE_PASSWORD: string;
    LOCK_NOTEBOOK: string;
    LOCK_ALL: string;
};
/**
 * Registers all plugin commands
 */
export declare function registerCommands(): Promise<void>;
/**
 * Registers context menu items for notebooks
 */
export declare function registerContextMenus(): Promise<void>;
/**
 * Registers toolbar buttons
 */
export declare function registerToolbarButtons(): Promise<void>;
//# sourceMappingURL=commands.d.ts.map