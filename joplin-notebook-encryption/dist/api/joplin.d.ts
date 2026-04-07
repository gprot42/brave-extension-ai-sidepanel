/**
 * Main Joplin Plugin API module
 * This is the entry point for accessing all Joplin plugin APIs
 */
import JoplinData from './JoplinData';
import JoplinSettings from './JoplinSettings';
import JoplinWorkspace from './JoplinWorkspace';
import JoplinViews from './JoplinViews';
import JoplinCommands from './JoplinCommands';
export interface JoplinPlugins {
    register(plugin: {
        onStart: () => Promise<void>;
    }): Promise<void>;
}
declare class Joplin {
    data: JoplinData;
    settings: JoplinSettings;
    workspace: JoplinWorkspace;
    views: JoplinViews;
    commands: JoplinCommands;
    plugins: JoplinPlugins;
    /**
     * Check if Joplin should use dark colors
     */
    shouldUseDarkColors(): Promise<boolean>;
    /**
     * Get version info
     */
    versionInfo(): Promise<{
        version: string;
        profileVersion: number;
        syncVersion: number;
    }>;
    /**
     * Require a module (like fs, path from Node.js)
     */
    require(module: string): unknown;
}
declare const joplin: Joplin;
export default joplin;
//# sourceMappingURL=joplin.d.ts.map