/**
 * Joplin Workspace API interface
 * Provides access to currently selected items and workspace events
 */
import { Folder, Note } from './types';
export interface Disposable {
    dispose(): void;
}
declare class JoplinWorkspace {
    /**
     * Gets the currently selected folder
     */
    selectedFolder(): Promise<Folder | null>;
    /**
     * Gets the currently selected note
     */
    selectedNote(): Promise<Note | null>;
    /**
     * Gets the IDs of all currently selected notes
     */
    selectedNoteIds(): Promise<string[]>;
    /**
     * Called when a note selection changes
     */
    onNoteSelectionChange(callback: () => void): Promise<Disposable>;
    /**
     * Called when a note content changes
     */
    onNoteContentChange(callback: () => void): Promise<Disposable>;
    /**
     * Called when sync starts
     */
    onSyncStart(callback: () => void): Promise<Disposable>;
    /**
     * Called when sync completes
     */
    onSyncComplete(callback: () => void): Promise<Disposable>;
    /**
     * Called when a note alarm triggers
     */
    onNoteAlarmTrigger(callback: (event: {
        noteId: string;
    }) => void): Promise<Disposable>;
    /**
     * Called when a resource changes
     */
    onResourceChange(callback: (event: {
        id: string;
    }) => void): Promise<Disposable>;
    /**
     * Filters the editor context menu
     */
    filterEditorContextMenu(callback: (items: unknown[]) => Promise<unknown[]>): void;
}
export default JoplinWorkspace;
//# sourceMappingURL=JoplinWorkspace.d.ts.map