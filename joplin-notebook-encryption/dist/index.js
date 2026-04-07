var notebookEncryption;
/******/ (() => { // webpackBootstrap
/******/ 	"use strict";
/******/ 	var __webpack_modules__ = ({

/***/ "./api/index.ts":
/*!**********************!*\
  !*** ./api/index.ts ***!
  \**********************/
/***/ ((__unused_webpack_module, exports) => {


Object.defineProperty(exports, "__esModule", ({ value: true }));
exports["default"] = joplin;


/***/ }),

/***/ "./api/types.ts":
/*!**********************!*\
  !*** ./api/types.ts ***!
  \**********************/
/***/ ((__unused_webpack_module, exports) => {


/**
 * Joplin Plugin API Type Definitions
 */
Object.defineProperty(exports, "__esModule", ({ value: true }));
exports.ImportModuleOutputFormat = exports.MenuItemLocation = exports.ToolbarButtonLocation = exports.SettingItemSubType = exports.SettingItemType = exports.ContentScriptType = void 0;
var ContentScriptType;
(function (ContentScriptType) {
    ContentScriptType["MarkdownItPlugin"] = "markdownItPlugin";
    ContentScriptType["CodeMirrorPlugin"] = "codeMirrorPlugin";
})(ContentScriptType || (exports.ContentScriptType = ContentScriptType = {}));
var SettingItemType;
(function (SettingItemType) {
    SettingItemType[SettingItemType["Int"] = 1] = "Int";
    SettingItemType[SettingItemType["String"] = 2] = "String";
    SettingItemType[SettingItemType["Bool"] = 3] = "Bool";
    SettingItemType[SettingItemType["Array"] = 4] = "Array";
    SettingItemType[SettingItemType["Object"] = 5] = "Object";
    SettingItemType[SettingItemType["Button"] = 6] = "Button";
})(SettingItemType || (exports.SettingItemType = SettingItemType = {}));
var SettingItemSubType;
(function (SettingItemSubType) {
    SettingItemSubType["FilePathAndArgs"] = "file_path_and_args";
    SettingItemSubType["FilePath"] = "file_path";
    SettingItemSubType["DirectoryPath"] = "directory_path";
})(SettingItemSubType || (exports.SettingItemSubType = SettingItemSubType = {}));
var ToolbarButtonLocation;
(function (ToolbarButtonLocation) {
    ToolbarButtonLocation["EditorToolbar"] = "editorToolbar";
    ToolbarButtonLocation["NoteToolbar"] = "noteToolbar";
})(ToolbarButtonLocation || (exports.ToolbarButtonLocation = ToolbarButtonLocation = {}));
var MenuItemLocation;
(function (MenuItemLocation) {
    MenuItemLocation["File"] = "file";
    MenuItemLocation["Edit"] = "edit";
    MenuItemLocation["View"] = "view";
    MenuItemLocation["Note"] = "note";
    MenuItemLocation["Tools"] = "tools";
    MenuItemLocation["Help"] = "help";
    MenuItemLocation["Context"] = "context";
    MenuItemLocation["EditorContextMenu"] = "editorContextMenu";
    MenuItemLocation["FolderContextMenu"] = "folderContextMenu";
    MenuItemLocation["NoteListContextMenu"] = "noteListContextMenu";
    MenuItemLocation["TagContextMenu"] = "tagContextMenu";
})(MenuItemLocation || (exports.MenuItemLocation = MenuItemLocation = {}));
var ImportModuleOutputFormat;
(function (ImportModuleOutputFormat) {
    ImportModuleOutputFormat["Markdown"] = "md";
    ImportModuleOutputFormat["Html"] = "html";
})(ImportModuleOutputFormat || (exports.ImportModuleOutputFormat = ImportModuleOutputFormat = {}));


/***/ }),

/***/ "./src/commands.ts":
/*!*************************!*\
  !*** ./src/commands.ts ***!
  \*************************/
/***/ (function(__unused_webpack_module, exports, __webpack_require__) {


/**
 * Plugin Commands
 * Registers commands and context menu actions for notebook encryption
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", ({ value: true }));
exports.COMMANDS = void 0;
exports.registerCommands = registerCommands;
exports.registerContextMenus = registerContextMenus;
exports.registerToolbarButtons = registerToolbarButtons;
const api_1 = __importDefault(__webpack_require__(/*! api */ "./api/index.ts"));
const types_1 = __webpack_require__(/*! api/types */ "./api/types.ts");
const notebookConfigService_1 = __webpack_require__(/*! ./services/notebookConfigService */ "./src/services/notebookConfigService.ts");
const passwordCache_1 = __webpack_require__(/*! ./services/passwordCache */ "./src/services/passwordCache.ts");
const passwordDialog_1 = __webpack_require__(/*! ./ui/dialogs/passwordDialog */ "./src/ui/dialogs/passwordDialog.ts");
const noteHandler_1 = __webpack_require__(/*! ./handlers/noteHandler */ "./src/handlers/noteHandler.ts");
/**
 * Command names
 */
exports.COMMANDS = {
    ENABLE_ENCRYPTION: 'notebookEncryption.enableEncryption',
    DISABLE_ENCRYPTION: 'notebookEncryption.disableEncryption',
    CHANGE_PASSWORD: 'notebookEncryption.changePassword',
    LOCK_NOTEBOOK: 'notebookEncryption.lockNotebook',
    LOCK_ALL: 'notebookEncryption.lockAll',
};
/**
 * Gets the currently selected folder
 */
async function getSelectedFolder() {
    try {
        const folder = await api_1.default.workspace.selectedFolder();
        return folder;
    }
    catch {
        return null;
    }
}
/**
 * Registers all plugin commands
 */
async function registerCommands() {
    // Command: Enable Encryption
    await api_1.default.commands.register({
        name: exports.COMMANDS.ENABLE_ENCRYPTION,
        label: '🔐 Encrypt Notebook',
        iconName: 'fas fa-lock',
        execute: async () => {
            const folder = await getSelectedFolder();
            if (!folder) {
                await api_1.default.views.dialogs.showMessageBox('Please select a notebook first.');
                return;
            }
            const configService = (0, notebookConfigService_1.getNotebookConfigService)();
            const dialogManager = (0, passwordDialog_1.getPasswordDialogManager)();
            // Check if already encrypted
            if (await configService.isEncrypted(folder.id)) {
                await api_1.default.views.dialogs.showMessageBox('This notebook is already encrypted.');
                return;
            }
            // Show setup dialog
            const result = await dialogManager.showSetupDialog(folder.title);
            if (!result.submitted || !result.password) {
                return; // User cancelled
            }
            try {
                // Show progress message
                await api_1.default.views.dialogs.showMessageBox(`Encrypting notebook "${folder.title}"...\n\nThis may take a moment depending on the number of notes.`);
                // Enable encryption
                await configService.enableEncryption(folder.id, result.password);
                // Encrypt all existing notes
                const encryptResult = await (0, noteHandler_1.encryptAllNotesInNotebook)(folder.id, result.password);
                // Cache the password
                const passwordCache = (0, passwordCache_1.getPasswordCache)();
                passwordCache.set(folder.id, result.password);
                // Show result
                await api_1.default.views.dialogs.showMessageBox(`Encryption enabled for "${folder.title}"!\n\n` +
                    `Notes encrypted: ${encryptResult.success}\n` +
                    `Failed: ${encryptResult.failed}`);
            }
            catch (error) {
                console.error('Failed to enable encryption:', error);
                await api_1.default.views.dialogs.showMessageBox(`Failed to enable encryption: ${error}`);
            }
        },
    });
    // Command: Disable Encryption
    await api_1.default.commands.register({
        name: exports.COMMANDS.DISABLE_ENCRYPTION,
        label: '🔓 Decrypt Notebook',
        iconName: 'fas fa-unlock',
        execute: async () => {
            const folder = await getSelectedFolder();
            if (!folder) {
                await api_1.default.views.dialogs.showMessageBox('Please select a notebook first.');
                return;
            }
            const configService = (0, notebookConfigService_1.getNotebookConfigService)();
            const dialogManager = (0, passwordDialog_1.getPasswordDialogManager)();
            // Check if not encrypted
            if (!(await configService.isEncrypted(folder.id))) {
                await api_1.default.views.dialogs.showMessageBox('This notebook is not encrypted.');
                return;
            }
            // Prompt for password
            const result = await dialogManager.showUnlockDialog(folder.title);
            if (!result.submitted || !result.password) {
                return; // User cancelled
            }
            // Verify password
            const isValid = await configService.verifyPassword(folder.id, result.password);
            if (!isValid) {
                await api_1.default.views.dialogs.showMessageBox('Incorrect password.');
                return;
            }
            try {
                // Show progress message
                await api_1.default.views.dialogs.showMessageBox(`Decrypting notebook "${folder.title}"...\n\nThis may take a moment depending on the number of notes.`);
                // Decrypt all notes
                const decryptResult = await (0, noteHandler_1.decryptAllNotesInNotebook)(folder.id, result.password);
                // Disable encryption
                await configService.disableEncryption(folder.id, result.password);
                // Clear password from cache
                const passwordCache = (0, passwordCache_1.getPasswordCache)();
                passwordCache.clear(folder.id);
                // Show result
                await api_1.default.views.dialogs.showMessageBox(`Encryption disabled for "${folder.title}"!\n\n` +
                    `Notes decrypted: ${decryptResult.success}\n` +
                    `Failed: ${decryptResult.failed}`);
            }
            catch (error) {
                console.error('Failed to disable encryption:', error);
                await api_1.default.views.dialogs.showMessageBox(`Failed to disable encryption: ${error}`);
            }
        },
    });
    // Command: Change Password
    await api_1.default.commands.register({
        name: exports.COMMANDS.CHANGE_PASSWORD,
        label: '🔑 Change Password',
        iconName: 'fas fa-key',
        execute: async () => {
            const folder = await getSelectedFolder();
            if (!folder) {
                await api_1.default.views.dialogs.showMessageBox('Please select a notebook first.');
                return;
            }
            const configService = (0, notebookConfigService_1.getNotebookConfigService)();
            const dialogManager = (0, passwordDialog_1.getPasswordDialogManager)();
            // Check if encrypted
            if (!(await configService.isEncrypted(folder.id))) {
                await api_1.default.views.dialogs.showMessageBox('This notebook is not encrypted.');
                return;
            }
            // Show change password dialog
            const result = await dialogManager.showChangePasswordDialog(folder.title);
            if (!result.submitted || !result.password || !result.newPassword) {
                return; // User cancelled
            }
            // Verify current password
            const isValid = await configService.verifyPassword(folder.id, result.password);
            if (!isValid) {
                await api_1.default.views.dialogs.showMessageBox('Incorrect current password.');
                return;
            }
            try {
                // Show progress message
                await api_1.default.views.dialogs.showMessageBox(`Changing password for "${folder.title}"...\n\nThis may take a moment as all notes need to be re-encrypted.`);
                // Re-encrypt all notes with new password
                const reencryptResult = await (0, noteHandler_1.reencryptAllNotesInNotebook)(folder.id, result.password, result.newPassword);
                // Update password hash in config
                await configService.changePassword(folder.id, result.password, result.newPassword);
                // Update cache with new password
                const passwordCache = (0, passwordCache_1.getPasswordCache)();
                passwordCache.set(folder.id, result.newPassword);
                // Show result
                await api_1.default.views.dialogs.showMessageBox(`Password changed for "${folder.title}"!\n\n` +
                    `Notes re-encrypted: ${reencryptResult.success}\n` +
                    `Failed: ${reencryptResult.failed}`);
            }
            catch (error) {
                console.error('Failed to change password:', error);
                await api_1.default.views.dialogs.showMessageBox(`Failed to change password: ${error}`);
            }
        },
    });
    // Command: Lock Notebook (clear cache)
    await api_1.default.commands.register({
        name: exports.COMMANDS.LOCK_NOTEBOOK,
        label: '🔒 Lock Notebook',
        iconName: 'fas fa-lock',
        execute: async () => {
            const folder = await getSelectedFolder();
            if (!folder) {
                await api_1.default.views.dialogs.showMessageBox('Please select a notebook first.');
                return;
            }
            const configService = (0, notebookConfigService_1.getNotebookConfigService)();
            const passwordCache = (0, passwordCache_1.getPasswordCache)();
            // Check if encrypted
            if (!(await configService.isEncrypted(folder.id))) {
                await api_1.default.views.dialogs.showMessageBox('This notebook is not encrypted.');
                return;
            }
            // Clear from cache
            passwordCache.clear(folder.id);
            await api_1.default.views.dialogs.showMessageBox(`Notebook "${folder.title}" has been locked.\n\nYou will need to enter the password to access notes again.`);
        },
    });
    // Command: Lock All Notebooks
    await api_1.default.commands.register({
        name: exports.COMMANDS.LOCK_ALL,
        label: '🔒 Lock All Notebooks',
        iconName: 'fas fa-lock',
        execute: async () => {
            const passwordCache = (0, passwordCache_1.getPasswordCache)();
            passwordCache.clearAll();
            await api_1.default.views.dialogs.showMessageBox('All encrypted notebooks have been locked.\n\nYou will need to enter passwords to access notes again.');
        },
    });
}
/**
 * Registers context menu items for notebooks
 */
async function registerContextMenus() {
    // Enable Encryption menu item
    await api_1.default.views.menuItems.create('contextMenu-enableEncryption', exports.COMMANDS.ENABLE_ENCRYPTION, types_1.MenuItemLocation.FolderContextMenu);
    // Disable Encryption menu item
    await api_1.default.views.menuItems.create('contextMenu-disableEncryption', exports.COMMANDS.DISABLE_ENCRYPTION, types_1.MenuItemLocation.FolderContextMenu);
    // Change Password menu item
    await api_1.default.views.menuItems.create('contextMenu-changePassword', exports.COMMANDS.CHANGE_PASSWORD, types_1.MenuItemLocation.FolderContextMenu);
    // Lock Notebook menu item
    await api_1.default.views.menuItems.create('contextMenu-lockNotebook', exports.COMMANDS.LOCK_NOTEBOOK, types_1.MenuItemLocation.FolderContextMenu);
}
/**
 * Registers toolbar buttons
 */
async function registerToolbarButtons() {
    // Lock All button in Tools menu could be added here if needed
}


/***/ }),

/***/ "./src/handlers/noteHandler.ts":
/*!*************************************!*\
  !*** ./src/handlers/noteHandler.ts ***!
  \*************************************/
/***/ (function(__unused_webpack_module, exports, __webpack_require__) {


/**
 * Note Handler
 * Handles encryption and decryption of notes when accessed
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", ({ value: true }));
exports.decryptNoteContent = decryptNoteContent;
exports.encryptNoteContent = encryptNoteContent;
exports.saveEncryptedNote = saveEncryptedNote;
exports.encryptAllNotesInNotebook = encryptAllNotesInNotebook;
exports.decryptAllNotesInNotebook = decryptAllNotesInNotebook;
exports.reencryptAllNotesInNotebook = reencryptAllNotesInNotebook;
const api_1 = __importDefault(__webpack_require__(/*! api */ "./api/index.ts"));
const encryptionService_1 = __webpack_require__(/*! ../services/encryptionService */ "./src/services/encryptionService.ts");
const passwordCache_1 = __webpack_require__(/*! ../services/passwordCache */ "./src/services/passwordCache.ts");
const notebookConfigService_1 = __webpack_require__(/*! ../services/notebookConfigService */ "./src/services/notebookConfigService.ts");
const passwordDialog_1 = __webpack_require__(/*! ../ui/dialogs/passwordDialog */ "./src/ui/dialogs/passwordDialog.ts");
/**
 * Gets a note by ID with specified fields
 */
async function getNote(noteId) {
    try {
        const note = await api_1.default.data.get(['notes', noteId], {
            fields: ['id', 'title', 'body', 'parent_id'],
        });
        return note;
    }
    catch {
        return null;
    }
}
/**
 * Gets a folder/notebook by ID
 */
async function getFolder(folderId) {
    try {
        const folder = await api_1.default.data.get(['folders', folderId], { fields: ['id', 'title'] });
        return folder;
    }
    catch {
        return null;
    }
}
/**
 * Gets all folders from the database
 */
async function getAllFolders() {
    const folders = [];
    let page = 1;
    let hasMore = true;
    while (hasMore) {
        try {
            const response = await api_1.default.data.get(['folders'], {
                fields: ['id', 'title', 'parent_id'],
                page,
                limit: 100,
            });
            let items = [];
            if (Array.isArray(response)) {
                items = response;
                hasMore = false;
            }
            else if (response && typeof response === 'object') {
                const apiResponse = response;
                if (apiResponse.items && Array.isArray(apiResponse.items)) {
                    items = apiResponse.items;
                    hasMore = apiResponse.has_more === true;
                }
                else {
                    hasMore = false;
                }
            }
            else {
                hasMore = false;
            }
            folders.push(...items);
            page++;
        }
        catch (error) {
            console.error('Error fetching folders:', error);
            hasMore = false;
        }
    }
    return folders;
}
/**
 * Gets all child folder IDs recursively (including the parent folder)
 */
function getChildFolderIds(folderId, allFolders) {
    const result = new Set();
    result.add(folderId);
    // Find direct children
    const directChildren = allFolders.filter(f => f.parent_id === folderId);
    // Recursively add children
    for (const child of directChildren) {
        const childIds = getChildFolderIds(child.id, allFolders);
        childIds.forEach(id => result.add(id));
    }
    return result;
}
/**
 * Prompts for password and caches it
 * Returns the password if successful, null if cancelled
 */
async function promptForPassword(notebookId) {
    const configService = (0, notebookConfigService_1.getNotebookConfigService)();
    const dialogManager = (0, passwordDialog_1.getPasswordDialogManager)();
    const passwordCache = (0, passwordCache_1.getPasswordCache)();
    const folder = await getFolder(notebookId);
    const notebookName = folder?.title || 'Unknown Notebook';
    let error;
    let attempts = 0;
    const maxAttempts = 3;
    while (attempts < maxAttempts) {
        const result = await dialogManager.showUnlockDialog(notebookName, error);
        if (!result.submitted) {
            return null; // User cancelled
        }
        const password = result.password || '';
        const isValid = await configService.verifyPassword(notebookId, password);
        if (isValid) {
            passwordCache.set(notebookId, password);
            return password;
        }
        attempts++;
        error = `Incorrect password. ${maxAttempts - attempts} attempts remaining.`;
    }
    // Max attempts reached
    await api_1.default.views.dialogs.showMessageBox('Maximum password attempts reached. Please try again later.');
    return null;
}
/**
 * Gets the decryption password for a notebook
 * Returns cached password or prompts user
 */
async function getPassword(notebookId) {
    const passwordCache = (0, passwordCache_1.getPasswordCache)();
    // Check cache first
    const cachedPassword = passwordCache.get(notebookId);
    if (cachedPassword) {
        return cachedPassword;
    }
    // Prompt for password
    return promptForPassword(notebookId);
}
/**
 * Decrypts note content if the notebook is encrypted
 * Returns the decrypted content or original content if not encrypted
 */
async function decryptNoteContent(noteId) {
    const note = await getNote(noteId);
    if (!note) {
        return null;
    }
    const configService = (0, notebookConfigService_1.getNotebookConfigService)();
    const notebookId = note.parent_id;
    // Check if notebook is encrypted (check parent hierarchy)
    const allFolders = await getAllFolders();
    const encryptedParentId = await findEncryptedParent(notebookId, allFolders, configService);
    if (!encryptedParentId) {
        return { content: note.body, wasEncrypted: false };
    }
    // Check if content is actually encrypted
    if (!(0, encryptionService_1.isEncrypted)(note.body)) {
        // Content not encrypted yet (new note in encrypted notebook)
        return { content: note.body, wasEncrypted: false };
    }
    // Get password (from cache or prompt)
    const password = await getPassword(encryptedParentId);
    if (!password) {
        return null; // User cancelled password prompt
    }
    // Decrypt content
    const result = await (0, encryptionService_1.decrypt)(password, note.body);
    if (!result.success) {
        console.error('Failed to decrypt note:', result.error);
        await api_1.default.views.dialogs.showMessageBox(`Failed to decrypt note: ${result.error}`);
        return null;
    }
    return { content: result.plaintext || '', wasEncrypted: true };
}
/**
 * Finds the encrypted parent folder in the hierarchy
 */
async function findEncryptedParent(folderId, allFolders, configService) {
    let currentId = folderId;
    while (currentId) {
        if (await configService.isEncrypted(currentId)) {
            return currentId;
        }
        // Find parent
        const folder = allFolders.find(f => f.id === currentId);
        currentId = folder?.parent_id || null;
    }
    return null;
}
/**
 * Encrypts note content if the notebook is encrypted
 * Returns the encrypted content or original content if not in encrypted notebook
 */
async function encryptNoteContent(noteId, content) {
    const note = await getNote(noteId);
    if (!note) {
        return content; // Return original content if note not found
    }
    const configService = (0, notebookConfigService_1.getNotebookConfigService)();
    const notebookId = note.parent_id;
    // Check if any parent notebook is encrypted
    const allFolders = await getAllFolders();
    const encryptedParentId = await findEncryptedParent(notebookId, allFolders, configService);
    if (!encryptedParentId) {
        return content; // Return original content
    }
    // Get password (from cache or prompt)
    const password = await getPassword(encryptedParentId);
    if (!password) {
        return null; // User cancelled - don't save
    }
    // Encrypt content
    try {
        const encryptedContent = await (0, encryptionService_1.encrypt)(password, content);
        return encryptedContent;
    }
    catch (error) {
        console.error('Failed to encrypt note:', error);
        await api_1.default.views.dialogs.showMessageBox(`Failed to encrypt note: ${error}`);
        return null;
    }
}
/**
 * Saves an encrypted note
 */
async function saveEncryptedNote(noteId, plainContent) {
    const encryptedContent = await encryptNoteContent(noteId, plainContent);
    if (encryptedContent === null) {
        return false; // Encryption failed or cancelled
    }
    try {
        await api_1.default.data.put(['notes', noteId], null, { body: encryptedContent });
        return true;
    }
    catch (error) {
        console.error('Failed to save encrypted note:', error);
        return false;
    }
}
/**
 * Gets all notes in a folder and its sub-folders
 */
async function getNotesInFolderRecursive(folderId) {
    const notes = [];
    // Get all folders to build the tree
    const allFolders = await getAllFolders();
    // Get all folder IDs that are children of this folder (including itself)
    const targetFolderIds = getChildFolderIds(folderId, allFolders);
    // Fetch all notes and filter by parent_id
    let page = 1;
    let hasMore = true;
    while (hasMore) {
        try {
            const response = await api_1.default.data.get(['notes'], {
                fields: ['id', 'body', 'parent_id'],
                page,
                limit: 100,
            });
            let items = [];
            if (Array.isArray(response)) {
                items = response;
                hasMore = false;
            }
            else if (response && typeof response === 'object') {
                const apiResponse = response;
                if (apiResponse.items && Array.isArray(apiResponse.items)) {
                    items = apiResponse.items;
                    hasMore = apiResponse.has_more === true;
                }
                else {
                    hasMore = false;
                }
            }
            else {
                hasMore = false;
            }
            // Filter by parent_id matching any of the target folders
            for (const item of items) {
                if (item.parent_id && targetFolderIds.has(item.parent_id)) {
                    notes.push({ id: item.id, body: item.body, parent_id: item.parent_id });
                }
            }
            page++;
        }
        catch (error) {
            console.error('Error fetching notes:', error);
            hasMore = false;
        }
    }
    return notes;
}
/**
 * Encrypts all notes in a notebook (including sub-notebooks)
 * Used when enabling encryption for a notebook
 */
async function encryptAllNotesInNotebook(notebookId, password) {
    const result = { success: 0, failed: 0 };
    const notes = await getNotesInFolderRecursive(notebookId);
    for (const note of notes) {
        // Skip if already encrypted
        if ((0, encryptionService_1.isEncrypted)(note.body)) {
            result.success++;
            continue;
        }
        // Skip empty notes
        if (!note.body || note.body.trim() === '') {
            result.success++;
            continue;
        }
        try {
            const encryptedContent = await (0, encryptionService_1.encrypt)(password, note.body);
            await api_1.default.data.put(['notes', note.id], null, { body: encryptedContent });
            result.success++;
        }
        catch (error) {
            console.error(`Failed to encrypt note ${note.id}:`, error);
            result.failed++;
        }
    }
    return result;
}
/**
 * Decrypts all notes in a notebook (including sub-notebooks)
 * Used when disabling encryption for a notebook
 */
async function decryptAllNotesInNotebook(notebookId, password) {
    const result = { success: 0, failed: 0 };
    const notes = await getNotesInFolderRecursive(notebookId);
    for (const note of notes) {
        // Skip if not encrypted
        if (!(0, encryptionService_1.isEncrypted)(note.body)) {
            result.success++;
            continue;
        }
        try {
            const decryptResult = await (0, encryptionService_1.decrypt)(password, note.body);
            if (decryptResult.success && decryptResult.plaintext) {
                await api_1.default.data.put(['notes', note.id], null, { body: decryptResult.plaintext });
                result.success++;
            }
            else {
                result.failed++;
            }
        }
        catch (error) {
            console.error(`Failed to decrypt note ${note.id}:`, error);
            result.failed++;
        }
    }
    return result;
}
/**
 * Re-encrypts all notes in a notebook with a new password
 */
async function reencryptAllNotesInNotebook(notebookId, oldPassword, newPassword) {
    const result = { success: 0, failed: 0 };
    const notes = await getNotesInFolderRecursive(notebookId);
    for (const note of notes) {
        if (!(0, encryptionService_1.isEncrypted)(note.body)) {
            // Encrypt unencrypted notes with new password
            try {
                const encryptedContent = await (0, encryptionService_1.encrypt)(newPassword, note.body);
                await api_1.default.data.put(['notes', note.id], null, { body: encryptedContent });
                result.success++;
            }
            catch {
                result.failed++;
            }
            continue;
        }
        try {
            // Decrypt with old password
            const decryptResult = await (0, encryptionService_1.decrypt)(oldPassword, note.body);
            if (!decryptResult.success || !decryptResult.plaintext) {
                result.failed++;
                continue;
            }
            // Re-encrypt with new password
            const encryptedContent = await (0, encryptionService_1.encrypt)(newPassword, decryptResult.plaintext);
            await api_1.default.data.put(['notes', note.id], null, { body: encryptedContent });
            result.success++;
        }
        catch (error) {
            console.error(`Failed to re-encrypt note ${note.id}:`, error);
            result.failed++;
        }
    }
    return result;
}


/***/ }),

/***/ "./src/index.ts":
/*!**********************!*\
  !*** ./src/index.ts ***!
  \**********************/
/***/ (function(__unused_webpack_module, exports, __webpack_require__) {


/**
 * Joplin Notebook Encryption Plugin
 *
 * This plugin adds notebook-level encryption to Joplin, allowing users to
 * protect sensitive notes with password-based encryption.
 *
 * Features:
 * - AES-256-GCM encryption for note content
 * - Password caching with configurable timeout
 * - Per-notebook encryption with unique passwords
 * - Context menu actions for encryption management
 * - Sync compatible encrypted content
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", ({ value: true }));
const api_1 = __importDefault(__webpack_require__(/*! api */ "./api/index.ts"));
const settings_1 = __webpack_require__(/*! ./settings */ "./src/settings.ts");
const commands_1 = __webpack_require__(/*! ./commands */ "./src/commands.ts");
const notebookConfigService_1 = __webpack_require__(/*! ./services/notebookConfigService */ "./src/services/notebookConfigService.ts");
const passwordCache_1 = __webpack_require__(/*! ./services/passwordCache */ "./src/services/passwordCache.ts");
const noteHandler_1 = __webpack_require__(/*! ./handlers/noteHandler */ "./src/handlers/noteHandler.ts");
const encryptionService_1 = __webpack_require__(/*! ./services/encryptionService */ "./src/services/encryptionService.ts");
/**
 * Current note being edited (for tracking changes)
 */
let currentNoteId = null;
let currentDecryptedContent = null;
/**
 * Initializes the plugin
 */
async function initPlugin() {
    console.log('Notebook Encryption plugin starting...');
    // Register settings
    await (0, settings_1.registerSettings)();
    // Initialize cache timeout from settings
    const timeout = await (0, settings_1.getCacheTimeout)();
    const passwordCache = (0, passwordCache_1.getPasswordCache)();
    passwordCache.setTimeout(timeout);
    // Load notebook configurations
    const configService = (0, notebookConfigService_1.getNotebookConfigService)();
    await configService.load();
    // Register commands and menus
    await (0, commands_1.registerCommands)();
    await (0, commands_1.registerContextMenus)();
    // Set up event listeners
    await setupEventListeners();
    console.log('Notebook Encryption plugin started successfully');
}
/**
 * Sets up event listeners for note changes
 */
async function setupEventListeners() {
    // Listen for note selection changes
    await api_1.default.workspace.onNoteSelectionChange(async () => {
        await handleNoteSelectionChange();
    });
    // Listen for note content changes (for auto-encrypt on save)
    await api_1.default.workspace.onNoteContentChange(async () => {
        await handleNoteContentChange();
    });
    // Listen for sync completion (optional re-lock)
    await api_1.default.workspace.onSyncComplete(async () => {
        await handleSyncComplete();
    });
}
/**
 * Handles note selection change
 */
async function handleNoteSelectionChange() {
    try {
        // Save any pending changes to previous note
        if (currentNoteId && currentDecryptedContent !== null) {
            // Note: In a full implementation, we would check if content changed
            // and save the encrypted version. For now, Joplin's auto-save handles this.
        }
        // Get the newly selected note
        const note = await api_1.default.workspace.selectedNote();
        if (!note) {
            currentNoteId = null;
            currentDecryptedContent = null;
            return;
        }
        currentNoteId = note.id;
        const notebookId = note.parent_id;
        // Check if the notebook is encrypted
        const configService = (0, notebookConfigService_1.getNotebookConfigService)();
        const isNotebookEncrypted = await configService.isEncrypted(notebookId);
        if (!isNotebookEncrypted) {
            currentDecryptedContent = null;
            return;
        }
        // Check if the note content is encrypted
        const noteBody = note.body;
        if (!(0, encryptionService_1.isEncrypted)(noteBody)) {
            currentDecryptedContent = null;
            return;
        }
        // Decrypt the note content
        const result = await (0, noteHandler_1.decryptNoteContent)(currentNoteId);
        if (result) {
            currentDecryptedContent = result.content;
            // Refresh the password cache expiry since user is actively using the notebook
            const passwordCache = (0, passwordCache_1.getPasswordCache)();
            passwordCache.refresh(notebookId);
        }
    }
    catch (error) {
        console.error('Error handling note selection change:', error);
    }
}
/**
 * Handles note content change
 */
async function handleNoteContentChange() {
    // This is called when the note content changes
    // In a full implementation, we would track changes and encrypt on save
    // For now, the encryption happens when the note is explicitly saved
    // through our commands or when switching notes
}
/**
 * Handles sync completion
 */
async function handleSyncComplete() {
    try {
        const requirePassword = await (0, settings_1.shouldRequirePasswordOnSync)();
        if (requirePassword) {
            // Clear all cached passwords after sync
            const passwordCache = (0, passwordCache_1.getPasswordCache)();
            passwordCache.clearAll();
            console.log('Passwords cleared after sync (as per settings)');
        }
        // Reload configurations in case they changed
        const configService = (0, notebookConfigService_1.getNotebookConfigService)();
        await configService.reload();
    }
    catch (error) {
        console.error('Error handling sync complete:', error);
    }
}
/**
 * Plugin registration
 */
api_1.default.plugins.register({
    onStart: async function () {
        await initPlugin();
    },
});


/***/ }),

/***/ "./src/services/encryptionService.ts":
/*!*******************************************!*\
  !*** ./src/services/encryptionService.ts ***!
  \*******************************************/
/***/ ((__unused_webpack_module, exports, __webpack_require__) => {


/**
 * Encryption Service
 * Provides AES-256-GCM encryption and decryption using Web Crypto API
 */
Object.defineProperty(exports, "__esModule", ({ value: true }));
exports.generateSalt = generateSalt;
exports.generateIV = generateIV;
exports.deriveKey = deriveKey;
exports.createPasswordHash = createPasswordHash;
exports.verifyPassword = verifyPassword;
exports.encrypt = encrypt;
exports.decrypt = decrypt;
exports.isEncrypted = isEncrypted;
exports.reencrypt = reencrypt;
const types_1 = __webpack_require__(/*! ../types */ "./src/types.ts");
/**
 * Converts a string to Uint8Array
 */
function stringToBytes(str) {
    return new TextEncoder().encode(str);
}
/**
 * Converts Uint8Array to string
 */
function bytesToString(bytes) {
    return new TextDecoder().decode(bytes);
}
/**
 * Converts Uint8Array to Base64 string
 */
function bytesToBase64(bytes) {
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}
/**
 * Converts Base64 string to Uint8Array
 */
function base64ToBytes(base64) {
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
function generateSalt() {
    return crypto.getRandomValues(new Uint8Array(types_1.CONSTANTS.SALT_LENGTH));
}
/**
 * Generates a cryptographically secure random IV
 */
function generateIV() {
    return crypto.getRandomValues(new Uint8Array(types_1.CONSTANTS.IV_LENGTH));
}
/**
 * Derives an encryption key from a password using PBKDF2
 */
async function deriveKey(password, salt) {
    const passwordBytes = stringToBytes(password);
    // Import the password as a key
    const passwordKey = await crypto.subtle.importKey('raw', passwordBytes.buffer, 'PBKDF2', false, ['deriveKey']);
    // Derive the actual encryption key
    return crypto.subtle.deriveKey({
        name: 'PBKDF2',
        salt: salt.buffer,
        iterations: types_1.CONSTANTS.PBKDF2_ITERATIONS,
        hash: 'SHA-256',
    }, passwordKey, {
        name: 'AES-GCM',
        length: 256,
    }, false, // not extractable
    ['encrypt', 'decrypt']);
}
/**
 * Creates a password verification hash
 * Used to verify password without storing it
 */
async function createPasswordHash(password, salt) {
    const key = await deriveKey(password, salt);
    // Encrypt a known value to create a verification hash
    const testData = stringToBytes('NOTEBOOK_ENCRYPTION_VERIFY');
    const iv = new Uint8Array(types_1.CONSTANTS.IV_LENGTH); // Zero IV for deterministic hash
    const encrypted = await crypto.subtle.encrypt({
        name: 'AES-GCM',
        iv: iv.buffer,
    }, key, testData.buffer);
    return bytesToBase64(new Uint8Array(encrypted));
}
/**
 * Verifies a password against a stored hash
 */
async function verifyPassword(password, salt, storedHash) {
    try {
        const computedHash = await createPasswordHash(password, salt);
        return computedHash === storedHash;
    }
    catch {
        return false;
    }
}
/**
 * Encrypts plaintext using AES-256-GCM
 */
async function encrypt(password, plaintext) {
    const salt = generateSalt();
    const iv = generateIV();
    const key = await deriveKey(password, salt);
    const plaintextBytes = stringToBytes(plaintext);
    const ciphertext = await crypto.subtle.encrypt({
        name: 'AES-GCM',
        iv: iv.buffer,
        tagLength: types_1.CONSTANTS.AUTH_TAG_LENGTH * 8, // in bits
    }, key, plaintextBytes.buffer);
    // Create metadata object
    const metadata = {
        version: types_1.CONSTANTS.ENCRYPTION_VERSION,
        algorithm: types_1.CONSTANTS.ALGORITHM,
        salt: bytesToBase64(salt),
        iv: bytesToBase64(iv),
        ciphertext: bytesToBase64(new Uint8Array(ciphertext)),
    };
    // Return as prefixed JSON string
    return types_1.CONSTANTS.ENCRYPTED_PREFIX + JSON.stringify(metadata);
}
/**
 * Decrypts ciphertext using AES-256-GCM
 */
async function decrypt(password, encryptedData) {
    try {
        // Check for encryption prefix
        if (!encryptedData.startsWith(types_1.CONSTANTS.ENCRYPTED_PREFIX)) {
            return {
                success: false,
                error: 'Content is not encrypted or has invalid format',
            };
        }
        // Parse metadata
        const jsonData = encryptedData.slice(types_1.CONSTANTS.ENCRYPTED_PREFIX.length);
        const metadata = JSON.parse(jsonData);
        // Validate version
        if (metadata.version !== types_1.CONSTANTS.ENCRYPTION_VERSION) {
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
        const plaintextBytes = await crypto.subtle.decrypt({
            name: 'AES-GCM',
            iv: iv.buffer,
            tagLength: types_1.CONSTANTS.AUTH_TAG_LENGTH * 8,
        }, key, ciphertext.buffer);
        return {
            success: true,
            plaintext: bytesToString(new Uint8Array(plaintextBytes)),
        };
    }
    catch (error) {
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
function isEncrypted(content) {
    return content.startsWith(types_1.CONSTANTS.ENCRYPTED_PREFIX);
}
/**
 * Re-encrypts content with a new password
 */
async function reencrypt(oldPassword, newPassword, encryptedData) {
    const decryptResult = await decrypt(oldPassword, encryptedData);
    if (!decryptResult.success || !decryptResult.plaintext) {
        throw new Error(decryptResult.error || 'Failed to decrypt with old password');
    }
    return encrypt(newPassword, decryptResult.plaintext);
}


/***/ }),

/***/ "./src/services/notebookConfigService.ts":
/*!***********************************************!*\
  !*** ./src/services/notebookConfigService.ts ***!
  \***********************************************/
/***/ (function(__unused_webpack_module, exports, __webpack_require__) {


/**
 * Notebook Configuration Service
 * Manages encrypted notebook configurations
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", ({ value: true }));
exports.NotebookConfigService = void 0;
exports.getNotebookConfigService = getNotebookConfigService;
exports.resetNotebookConfigService = resetNotebookConfigService;
const api_1 = __importDefault(__webpack_require__(/*! api */ "./api/index.ts"));
const types_1 = __webpack_require__(/*! ../types */ "./src/types.ts");
const encryptionService_1 = __webpack_require__(/*! ./encryptionService */ "./src/services/encryptionService.ts");
/**
 * Converts Uint8Array to Base64 string
 */
function bytesToBase64(bytes) {
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
        binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
}
/**
 * Converts Base64 string to Uint8Array
 */
function base64ToBytes(base64) {
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) {
        bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
}
/**
 * Notebook Configuration Service class
 */
class NotebookConfigService {
    constructor() {
        this.configs = {};
        this.loaded = false;
    }
    /**
     * Loads configurations from Joplin settings
     */
    async load() {
        try {
            const configJson = await api_1.default.settings.value('encryptedNotebooks');
            if (configJson) {
                this.configs = JSON.parse(configJson);
            }
            this.loaded = true;
        }
        catch (error) {
            console.error('Failed to load notebook encryption configs:', error);
            this.configs = {};
            this.loaded = true;
        }
    }
    /**
     * Saves configurations to Joplin settings
     */
    async save() {
        try {
            const configJson = JSON.stringify(this.configs);
            await api_1.default.settings.setValue('encryptedNotebooks', configJson);
        }
        catch (error) {
            console.error('Failed to save notebook encryption configs:', error);
            throw error;
        }
    }
    /**
     * Ensures configurations are loaded
     */
    async ensureLoaded() {
        if (!this.loaded) {
            await this.load();
        }
    }
    /**
     * Checks if a notebook is encrypted
     * @param notebookId The notebook ID
     */
    async isEncrypted(notebookId) {
        await this.ensureLoaded();
        const config = this.configs[notebookId];
        return config ? config.enabled : false;
    }
    /**
     * Gets the configuration for a notebook
     * @param notebookId The notebook ID
     */
    async getConfig(notebookId) {
        await this.ensureLoaded();
        return this.configs[notebookId] || null;
    }
    /**
     * Enables encryption for a notebook
     * @param notebookId The notebook ID
     * @param password The password to use for encryption
     */
    async enableEncryption(notebookId, password) {
        await this.ensureLoaded();
        // Check if already encrypted
        if (this.configs[notebookId]?.enabled) {
            throw new Error('Notebook is already encrypted');
        }
        // Generate salt and create password hash for verification
        const salt = (0, encryptionService_1.generateSalt)();
        const passwordHash = await (0, encryptionService_1.createPasswordHash)(password, salt);
        // Create configuration
        const config = {
            id: notebookId,
            enabled: true,
            passwordHash,
            salt: bytesToBase64(salt),
            createdAt: Date.now(),
            version: types_1.CONSTANTS.ENCRYPTION_VERSION,
        };
        this.configs[notebookId] = config;
        await this.save();
    }
    /**
     * Disables encryption for a notebook
     * @param notebookId The notebook ID
     * @param password The password for verification
     */
    async disableEncryption(notebookId, password) {
        await this.ensureLoaded();
        const config = this.configs[notebookId];
        if (!config || !config.enabled) {
            throw new Error('Notebook is not encrypted');
        }
        // Verify password
        const isValid = await this.verifyPassword(notebookId, password);
        if (!isValid) {
            throw new Error('Invalid password');
        }
        // Remove configuration
        delete this.configs[notebookId];
        await this.save();
    }
    /**
     * Verifies a password for a notebook
     * @param notebookId The notebook ID
     * @param password The password to verify
     */
    async verifyPassword(notebookId, password) {
        await this.ensureLoaded();
        const config = this.configs[notebookId];
        if (!config) {
            return false;
        }
        const salt = base64ToBytes(config.salt);
        return (0, encryptionService_1.verifyPassword)(password, salt, config.passwordHash);
    }
    /**
     * Changes the password for an encrypted notebook
     * @param notebookId The notebook ID
     * @param oldPassword The current password
     * @param newPassword The new password
     */
    async changePassword(notebookId, oldPassword, newPassword) {
        await this.ensureLoaded();
        const config = this.configs[notebookId];
        if (!config || !config.enabled) {
            throw new Error('Notebook is not encrypted');
        }
        // Verify old password
        const isValid = await this.verifyPassword(notebookId, oldPassword);
        if (!isValid) {
            throw new Error('Invalid current password');
        }
        // Generate new salt and hash
        const salt = (0, encryptionService_1.generateSalt)();
        const passwordHash = await (0, encryptionService_1.createPasswordHash)(newPassword, salt);
        // Update configuration
        config.salt = bytesToBase64(salt);
        config.passwordHash = passwordHash;
        await this.save();
    }
    /**
     * Gets all encrypted notebook IDs
     */
    async getAllEncryptedNotebooks() {
        await this.ensureLoaded();
        return Object.keys(this.configs).filter((id) => this.configs[id].enabled);
    }
    /**
     * Updates the configuration for a notebook
     * Used internally for migrations or fixes
     * @param notebookId The notebook ID
     * @param updates Partial configuration updates
     */
    async updateConfig(notebookId, updates) {
        await this.ensureLoaded();
        const config = this.configs[notebookId];
        if (!config) {
            throw new Error('Notebook configuration not found');
        }
        this.configs[notebookId] = { ...config, ...updates };
        await this.save();
    }
    /**
     * Reloads configurations from settings
     * Useful when settings are changed externally
     */
    async reload() {
        this.loaded = false;
        await this.load();
    }
}
exports.NotebookConfigService = NotebookConfigService;
// Singleton instance
let instance = null;
/**
 * Gets the singleton notebook config service instance
 */
function getNotebookConfigService() {
    if (!instance) {
        instance = new NotebookConfigService();
    }
    return instance;
}
/**
 * Resets the singleton instance (useful for testing)
 */
function resetNotebookConfigService() {
    instance = null;
}


/***/ }),

/***/ "./src/services/passwordCache.ts":
/*!***************************************!*\
  !*** ./src/services/passwordCache.ts ***!
  \***************************************/
/***/ ((__unused_webpack_module, exports, __webpack_require__) => {


/**
 * Password Cache Service
 * Manages in-memory caching of passwords with automatic expiration
 */
Object.defineProperty(exports, "__esModule", ({ value: true }));
exports.PasswordCache = void 0;
exports.getPasswordCache = getPasswordCache;
exports.resetPasswordCache = resetPasswordCache;
const types_1 = __webpack_require__(/*! ../types */ "./src/types.ts");
/**
 * Password Cache class for managing notebook passwords
 * Passwords are stored in memory only and never persisted
 */
class PasswordCache {
    constructor(timeoutMinutes = types_1.CONSTANTS.DEFAULT_CACHE_TIMEOUT) {
        this.cache = new Map();
        this.timers = new Map();
        this.timeoutMs = timeoutMinutes * 60 * 1000;
    }
    /**
     * Sets the cache timeout duration
     * @param minutes Timeout in minutes
     */
    setTimeout(minutes) {
        this.timeoutMs = minutes * 60 * 1000;
    }
    /**
     * Gets the current timeout in minutes
     */
    getTimeout() {
        return this.timeoutMs / 60 / 1000;
    }
    /**
     * Caches a password for a notebook
     * @param notebookId The notebook ID
     * @param password The password to cache
     */
    set(notebookId, password) {
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
    get(notebookId) {
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
    has(notebookId) {
        return this.get(notebookId) !== null;
    }
    /**
     * Clears the cached password for a notebook
     * @param notebookId The notebook ID
     */
    clear(notebookId) {
        this.clearTimer(notebookId);
        this.cache.delete(notebookId);
    }
    /**
     * Clears all cached passwords
     */
    clearAll() {
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
    refresh(notebookId) {
        const entry = this.cache.get(notebookId);
        if (entry) {
            this.set(notebookId, entry.password);
        }
    }
    /**
     * Gets the remaining time until expiry in milliseconds
     * @param notebookId The notebook ID
     */
    getRemainingTime(notebookId) {
        const entry = this.cache.get(notebookId);
        if (!entry) {
            return 0;
        }
        return Math.max(0, entry.expiry - Date.now());
    }
    /**
     * Gets all currently cached notebook IDs
     */
    getCachedNotebookIds() {
        const ids = [];
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
    scheduleCleanup(notebookId) {
        const timer = setTimeout(() => {
            this.cache.delete(notebookId);
            this.timers.delete(notebookId);
        }, this.timeoutMs);
        this.timers.set(notebookId, timer);
    }
    /**
     * Clears the timer for a notebook
     */
    clearTimer(notebookId) {
        const timer = this.timers.get(notebookId);
        if (timer) {
            clearTimeout(timer);
            this.timers.delete(notebookId);
        }
    }
}
exports.PasswordCache = PasswordCache;
// Singleton instance
let instance = null;
/**
 * Gets the singleton password cache instance
 */
function getPasswordCache() {
    if (!instance) {
        instance = new PasswordCache();
    }
    return instance;
}
/**
 * Resets the singleton instance (useful for testing)
 */
function resetPasswordCache() {
    if (instance) {
        instance.clearAll();
        instance = null;
    }
}


/***/ }),

/***/ "./src/settings.ts":
/*!*************************!*\
  !*** ./src/settings.ts ***!
  \*************************/
/***/ (function(__unused_webpack_module, exports, __webpack_require__) {


/**
 * Plugin Settings Registration
 * Registers plugin settings with Joplin
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", ({ value: true }));
exports.SETTING_KEYS = void 0;
exports.registerSettings = registerSettings;
exports.getCacheTimeout = getCacheTimeout;
exports.shouldShowLockIndicator = shouldShowLockIndicator;
exports.shouldClearCacheOnLock = shouldClearCacheOnLock;
exports.shouldRequirePasswordOnSync = shouldRequirePasswordOnSync;
const api_1 = __importDefault(__webpack_require__(/*! api */ "./api/index.ts"));
const types_1 = __webpack_require__(/*! api/types */ "./api/types.ts");
const types_2 = __webpack_require__(/*! ./types */ "./src/types.ts");
const passwordCache_1 = __webpack_require__(/*! ./services/passwordCache */ "./src/services/passwordCache.ts");
/**
 * Setting keys used by the plugin
 */
exports.SETTING_KEYS = {
    CACHE_TIMEOUT: 'encryptionCacheTimeout',
    ENCRYPTED_NOTEBOOKS: 'encryptedNotebooks',
    SHOW_LOCK_INDICATOR: 'showLockIndicator',
    CLEAR_CACHE_ON_LOCK: 'clearCacheOnLock',
    REQUIRE_PASSWORD_ON_SYNC: 'requirePasswordOnSync',
};
/**
 * Registers all plugin settings
 */
async function registerSettings() {
    // Register the settings section
    await api_1.default.settings.registerSection('notebookEncryption', {
        label: 'Notebook Encryption',
        iconName: 'fas fa-lock',
        description: 'Settings for notebook encryption plugin',
    });
    // Register individual settings
    await api_1.default.settings.registerSettings({
        [exports.SETTING_KEYS.CACHE_TIMEOUT]: {
            value: types_2.CONSTANTS.DEFAULT_CACHE_TIMEOUT,
            type: types_1.SettingItemType.Int,
            section: 'notebookEncryption',
            public: true,
            label: 'Password cache timeout (minutes)',
            description: 'How long to keep passwords cached in memory. Set to 0 to disable caching (will prompt for password every time).',
            minimum: 0,
            maximum: 60,
            step: 1,
        },
        [exports.SETTING_KEYS.ENCRYPTED_NOTEBOOKS]: {
            value: '{}',
            type: types_1.SettingItemType.String,
            section: 'notebookEncryption',
            public: false, // Hidden from user, managed internally
            label: 'Encrypted notebooks configuration',
            description: 'Internal storage for encrypted notebook configurations. Do not modify manually.',
        },
        [exports.SETTING_KEYS.SHOW_LOCK_INDICATOR]: {
            value: true,
            type: types_1.SettingItemType.Bool,
            section: 'notebookEncryption',
            public: true,
            label: 'Show lock indicator',
            description: 'Show a lock icon (🔒) prefix on encrypted notebook names.',
        },
        [exports.SETTING_KEYS.CLEAR_CACHE_ON_LOCK]: {
            value: true,
            type: types_1.SettingItemType.Bool,
            section: 'notebookEncryption',
            public: true,
            label: 'Clear cache on system lock',
            description: 'Automatically clear cached passwords when the computer is locked.',
        },
        [exports.SETTING_KEYS.REQUIRE_PASSWORD_ON_SYNC]: {
            value: false,
            type: types_1.SettingItemType.Bool,
            section: 'notebookEncryption',
            public: true,
            label: 'Require password after sync',
            description: 'Prompt for password again after synchronization completes.',
        },
    });
    // Listen for setting changes
    await api_1.default.settings.onChange(handleSettingChange);
}
/**
 * Handles changes to plugin settings
 */
async function handleSettingChange(event) {
    for (const key of event.keys) {
        switch (key) {
            case exports.SETTING_KEYS.CACHE_TIMEOUT:
                await updateCacheTimeout();
                break;
            // Other setting changes can be handled here
        }
    }
}
/**
 * Updates the password cache timeout from settings
 */
async function updateCacheTimeout() {
    const timeout = await api_1.default.settings.value(exports.SETTING_KEYS.CACHE_TIMEOUT);
    const cache = (0, passwordCache_1.getPasswordCache)();
    cache.setTimeout(timeout);
}
/**
 * Gets the current cache timeout setting
 */
async function getCacheTimeout() {
    return (await api_1.default.settings.value(exports.SETTING_KEYS.CACHE_TIMEOUT));
}
/**
 * Gets whether lock indicator should be shown
 */
async function shouldShowLockIndicator() {
    return (await api_1.default.settings.value(exports.SETTING_KEYS.SHOW_LOCK_INDICATOR));
}
/**
 * Gets whether cache should be cleared on system lock
 */
async function shouldClearCacheOnLock() {
    return (await api_1.default.settings.value(exports.SETTING_KEYS.CLEAR_CACHE_ON_LOCK));
}
/**
 * Gets whether password should be required after sync
 */
async function shouldRequirePasswordOnSync() {
    return (await api_1.default.settings.value(exports.SETTING_KEYS.REQUIRE_PASSWORD_ON_SYNC));
}


/***/ }),

/***/ "./src/types.ts":
/*!**********************!*\
  !*** ./src/types.ts ***!
  \**********************/
/***/ ((__unused_webpack_module, exports) => {


/**
 * Plugin-specific type definitions for Notebook Encryption
 */
Object.defineProperty(exports, "__esModule", ({ value: true }));
exports.CONSTANTS = exports.DialogType = void 0;
/**
 * Dialog types for password prompts
 */
var DialogType;
(function (DialogType) {
    /** Unlock existing encrypted notebook */
    DialogType["Unlock"] = "unlock";
    /** Set up encryption for a notebook */
    DialogType["Setup"] = "setup";
    /** Change password for encrypted notebook */
    DialogType["ChangePassword"] = "change";
})(DialogType || (exports.DialogType = DialogType = {}));
/**
 * Constants for the plugin
 */
exports.CONSTANTS = {
    /** Current encryption format version */
    ENCRYPTION_VERSION: 1,
    /** Algorithm identifier */
    ALGORITHM: 'AES-256-GCM',
    /** PBKDF2 iteration count */
    PBKDF2_ITERATIONS: 100000,
    /** Salt length in bytes */
    SALT_LENGTH: 16,
    /** IV length in bytes for GCM */
    IV_LENGTH: 12,
    /** Auth tag length in bytes for GCM */
    AUTH_TAG_LENGTH: 16,
    /** Default cache timeout in minutes */
    DEFAULT_CACHE_TIMEOUT: 10,
    /** Prefix for encrypted content */
    ENCRYPTED_PREFIX: '🔒ENCRYPTED:',
};


/***/ }),

/***/ "./src/ui/dialogs/passwordDialog.ts":
/*!******************************************!*\
  !*** ./src/ui/dialogs/passwordDialog.ts ***!
  \******************************************/
/***/ (function(__unused_webpack_module, exports, __webpack_require__) {


/**
 * Password Dialog
 * Provides a modal dialog for password entry, setup, and change
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", ({ value: true }));
exports.PasswordDialogManager = void 0;
exports.getPasswordDialogManager = getPasswordDialogManager;
const api_1 = __importDefault(__webpack_require__(/*! api */ "./api/index.ts"));
/**
 * Common CSS styles for all dialogs
 */
const commonStyles = `
  .notebook-encryption-dialog {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
    padding: 12px;
    box-sizing: border-box;
  }
  .dialog-header {
    display: flex;
    align-items: center;
    margin-bottom: 12px;
  }
  .dialog-header .lock-icon {
    font-size: 20px;
    margin-right: 8px;
  }
  .dialog-header h3 {
    margin: 0;
    font-size: 16px;
    font-weight: 600;
  }
  .notebook-name {
    color: #666;
    font-size: 13px;
    margin-bottom: 12px;
  }
  .form-group {
    margin-bottom: 12px;
  }
  .form-group label {
    display: block;
    margin-bottom: 4px;
    font-weight: 500;
    font-size: 13px;
  }
  .form-group input {
    width: 100%;
    padding: 8px;
    border: 1px solid #ddd;
    border-radius: 4px;
    font-size: 13px;
    box-sizing: border-box;
  }
  .form-group input:focus {
    outline: none;
    border-color: #007bff;
  }
  .password-hint {
    font-size: 11px;
    color: #888;
    margin-top: 4px;
  }
  .error-message {
    color: #e74c3c;
    margin-bottom: 10px;
    padding: 8px;
    background: #fdf2f2;
    border-radius: 4px;
    font-size: 12px;
  }
  .warning-text {
    color: #856404;
    background: #fff3cd;
    padding: 8px;
    border-radius: 4px;
    font-size: 12px;
    margin-bottom: 12px;
  }
`;
/**
 * HTML template for the unlock dialog
 */
function getUnlockDialogHtml(notebookName, error) {
    const errorHtml = error
        ? `<div class="error-message">${escapeHtml(error)}</div>`
        : '';
    return `
    <style>${commonStyles}</style>
    <div class="notebook-encryption-dialog">
      <div class="dialog-header">
        <span class="lock-icon">🔒</span>
        <h3>Unlock</h3>
      </div>
      <div class="notebook-name">${escapeHtml(notebookName)}</div>
      ${errorHtml}
      <form name="password-form">
        <div class="form-group">
          <label for="password">Password</label>
          <input type="password" id="password" name="password" required autofocus>
        </div>
      </form>
    </div>
  `;
}
/**
 * HTML template for the setup dialog
 */
function getSetupDialogHtml(notebookName, error) {
    const errorHtml = error
        ? `<div class="error-message">${escapeHtml(error)}</div>`
        : '';
    return `
    <style>${commonStyles}</style>
    <div class="notebook-encryption-dialog">
      <div class="dialog-header">
        <span class="lock-icon">🔐</span>
        <h3>Encrypt</h3>
      </div>
      <div class="notebook-name">${escapeHtml(notebookName)}</div>
      <div class="warning-text">⚠️ No recovery if lost!</div>
      ${errorHtml}
      <form name="password-form">
        <div class="form-group">
          <label for="password">Password</label>
          <input type="password" id="password" name="password" required autofocus>
        </div>
        <div class="form-group">
          <label for="confirmPassword">Confirm</label>
          <input type="password" id="confirmPassword" name="confirmPassword" required>
        </div>
      </form>
    </div>
  `;
}
/**
 * HTML template for the change password dialog
 */
function getChangePasswordDialogHtml(notebookName, error) {
    const errorHtml = error
        ? `<div class="error-message">${escapeHtml(error)}</div>`
        : '';
    return `
    <style>${commonStyles}</style>
    <div class="notebook-encryption-dialog">
      <div class="dialog-header">
        <span class="lock-icon">🔑</span>
        <h3>Change Password</h3>
      </div>
      <div class="notebook-name">${escapeHtml(notebookName)}</div>
      ${errorHtml}
      <form name="password-form">
        <div class="form-group">
          <label for="currentPassword">Current</label>
          <input type="password" id="currentPassword" name="currentPassword" required autofocus>
        </div>
        <div class="form-group">
          <label for="newPassword">New</label>
          <input type="password" id="newPassword" name="newPassword" required>
        </div>
        <div class="form-group">
          <label for="confirmPassword">Confirm</label>
          <input type="password" id="confirmPassword" name="confirmPassword" required>
        </div>
      </form>
    </div>
  `;
}
/**
 * Escapes HTML special characters
 */
function escapeHtml(text) {
    return text.replace(/[&<>"']/g, (char) => {
        const entities = {
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;',
        };
        return entities[char] || char;
    });
}
/**
 * Password Dialog Manager
 */
class PasswordDialogManager {
    constructor() {
        this.dialogHandle = null;
    }
    /**
     * Shows an unlock password dialog
     */
    async showUnlockDialog(notebookName, error) {
        const handle = await this.ensureDialog();
        await api_1.default.views.dialogs.setHtml(handle, getUnlockDialogHtml(notebookName, error));
        await api_1.default.views.dialogs.setButtons(handle, [
            { id: 'ok', title: 'Unlock' },
            { id: 'cancel', title: 'Cancel' },
        ]);
        await api_1.default.views.dialogs.setFitToContent(handle, true);
        const result = await api_1.default.views.dialogs.open(handle);
        if (result.id === 'ok' && result.formData) {
            const password = result.formData['password-form']
                ?.password;
            return {
                submitted: true,
                password: password || '',
            };
        }
        return { submitted: false };
    }
    /**
     * Shows a setup encryption dialog
     */
    async showSetupDialog(notebookName, error) {
        const handle = await this.ensureDialog();
        await api_1.default.views.dialogs.setHtml(handle, getSetupDialogHtml(notebookName, error));
        await api_1.default.views.dialogs.setButtons(handle, [
            { id: 'ok', title: 'Encrypt' },
            { id: 'cancel', title: 'Cancel' },
        ]);
        await api_1.default.views.dialogs.setFitToContent(handle, true);
        const result = await api_1.default.views.dialogs.open(handle);
        if (result.id === 'ok' && result.formData) {
            const password = result.formData['password-form']
                ?.password;
            const confirmPassword = result.formData['password-form']?.confirmPassword;
            // Validate passwords match
            if (password !== confirmPassword) {
                return this.showSetupDialog(notebookName, 'Passwords do not match');
            }
            if (!password || password.length < 4) {
                return this.showSetupDialog(notebookName, 'Min 4 characters');
            }
            return {
                submitted: true,
                password: password,
            };
        }
        return { submitted: false };
    }
    /**
     * Shows a change password dialog
     */
    async showChangePasswordDialog(notebookName, error) {
        const handle = await this.ensureDialog();
        await api_1.default.views.dialogs.setHtml(handle, getChangePasswordDialogHtml(notebookName, error));
        await api_1.default.views.dialogs.setButtons(handle, [
            { id: 'ok', title: 'Change' },
            { id: 'cancel', title: 'Cancel' },
        ]);
        await api_1.default.views.dialogs.setFitToContent(handle, true);
        const result = await api_1.default.views.dialogs.open(handle);
        if (result.id === 'ok' && result.formData) {
            const currentPassword = result.formData['password-form']?.currentPassword;
            const newPassword = result.formData['password-form']?.newPassword;
            const confirmPassword = result.formData['password-form']?.confirmPassword;
            // Validate new passwords match
            if (newPassword !== confirmPassword) {
                return this.showChangePasswordDialog(notebookName, 'Passwords do not match');
            }
            if (!newPassword || newPassword.length < 4) {
                return this.showChangePasswordDialog(notebookName, 'Min 4 characters');
            }
            return {
                submitted: true,
                password: currentPassword || '',
                newPassword: newPassword,
            };
        }
        return { submitted: false };
    }
    /**
     * Ensures the dialog exists and returns its handle
     */
    async ensureDialog() {
        if (!this.dialogHandle) {
            this.dialogHandle = await api_1.default.views.dialogs.create('notebook-encryption-dialog');
        }
        return this.dialogHandle;
    }
}
exports.PasswordDialogManager = PasswordDialogManager;
// Singleton instance
let dialogManager = null;
/**
 * Gets the singleton password dialog manager instance
 */
function getPasswordDialogManager() {
    if (!dialogManager) {
        dialogManager = new PasswordDialogManager();
    }
    return dialogManager;
}


/***/ })

/******/ 	});
/************************************************************************/
/******/ 	// The module cache
/******/ 	var __webpack_module_cache__ = {};
/******/ 	
/******/ 	// The require function
/******/ 	function __webpack_require__(moduleId) {
/******/ 		// Check if module is in cache
/******/ 		var cachedModule = __webpack_module_cache__[moduleId];
/******/ 		if (cachedModule !== undefined) {
/******/ 			return cachedModule.exports;
/******/ 		}
/******/ 		// Create a new module (and put it into the cache)
/******/ 		var module = __webpack_module_cache__[moduleId] = {
/******/ 			// no module.id needed
/******/ 			// no module.loaded needed
/******/ 			exports: {}
/******/ 		};
/******/ 	
/******/ 		// Execute the module function
/******/ 		__webpack_modules__[moduleId].call(module.exports, module, module.exports, __webpack_require__);
/******/ 	
/******/ 		// Return the exports of the module
/******/ 		return module.exports;
/******/ 	}
/******/ 	
/************************************************************************/
/******/ 	
/******/ 	// startup
/******/ 	// Load entry module and return exports
/******/ 	// This entry module is referenced by other modules so it can't be inlined
/******/ 	var __webpack_exports__ = __webpack_require__("./src/index.ts");
/******/ 	notebookEncryption = __webpack_exports__;
/******/ 	
/******/ })()
;
//# sourceMappingURL=index.js.map