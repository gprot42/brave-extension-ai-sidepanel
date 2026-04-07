/**
 * Joplin Views API interface
 * Provides access to view-related services
 */
import JoplinViewsDialogs from './JoplinViewsDialogs';
import { MenuItem, MenuItemLocation, ToolbarButtonLocation } from './types';
export type ViewHandle = string;
export interface JoplinViewsMenuItems {
    create(id: string, commandName: string, location: MenuItemLocation, options?: {
        accelerator?: string;
    }): Promise<void>;
}
export interface JoplinViewsMenus {
    create(id: string, label: string, menuItems: MenuItem[], location: MenuItemLocation): Promise<void>;
}
export interface JoplinViewsToolbarButtons {
    create(id: string, commandName: string, location: ToolbarButtonLocation): Promise<void>;
}
export interface JoplinViewsPanels {
    create(id: string): Promise<ViewHandle>;
    setHtml(handle: ViewHandle, html: string): Promise<void>;
    addScript(handle: ViewHandle, script: string): Promise<void>;
    show(handle: ViewHandle, show?: boolean): Promise<void>;
    visible(handle: ViewHandle): Promise<boolean>;
    onMessage(handle: ViewHandle, callback: (message: unknown) => void): void;
}
export interface JoplinViewsNoteList {
}
declare class JoplinViews {
    dialogs: JoplinViewsDialogs;
    menuItems: JoplinViewsMenuItems;
    menus: JoplinViewsMenus;
    toolbarButtons: JoplinViewsToolbarButtons;
    panels: JoplinViewsPanels;
    noteList: JoplinViewsNoteList;
}
export default JoplinViews;
//# sourceMappingURL=JoplinViews.d.ts.map