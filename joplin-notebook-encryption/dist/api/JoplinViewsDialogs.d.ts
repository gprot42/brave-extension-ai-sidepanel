/**
 * Joplin Views Dialogs API interface
 * Allows creating and managing modal dialogs
 */
import { ButtonSpec, DialogResult } from './types';
export type ViewHandle = string;
declare class JoplinViewsDialogs {
    /**
     * Creates a new dialog
     */
    create(id: string): Promise<ViewHandle>;
    /**
     * Shows the dialog
     */
    open(handle: ViewHandle): Promise<DialogResult>;
    /**
     * Sets the dialog HTML content
     */
    setHtml(handle: ViewHandle, html: string): Promise<void>;
    /**
     * Sets the dialog buttons
     */
    setButtons(handle: ViewHandle, buttons: ButtonSpec[]): Promise<void>;
    /**
     * Sets whether the dialog should fit its content
     */
    setFitToContent(handle: ViewHandle, fit: boolean): Promise<void>;
    /**
     * Adds a script to the dialog
     */
    addScript(handle: ViewHandle, script: string): Promise<void>;
    /**
     * Shows a simple message box
     */
    showMessageBox(message: string): Promise<number>;
    /**
     * Shows a file/folder open dialog
     */
    showOpenDialog(options: {
        properties?: ('openFile' | 'openDirectory' | 'multiSelections' | 'showHiddenFiles')[];
        filters?: {
            name: string;
            extensions: string[];
        }[];
        defaultPath?: string;
    }): Promise<string[] | undefined>;
    /**
     * Shows a toast notification
     */
    showToast(message: string): Promise<void>;
}
export default JoplinViewsDialogs;
//# sourceMappingURL=JoplinViewsDialogs.d.ts.map