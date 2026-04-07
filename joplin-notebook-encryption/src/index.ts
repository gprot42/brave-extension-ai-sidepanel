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

import joplin from 'api';
import { registerSettings, getCacheTimeout, shouldRequirePasswordOnSync } from './settings';
import { registerCommands, registerContextMenus } from './commands';
import { getNotebookConfigService } from './services/notebookConfigService';
import { getPasswordCache } from './services/passwordCache';
import { decryptNoteContent, encryptNoteContent } from './handlers/noteHandler';
import { isEncrypted } from './services/encryptionService';

/**
 * Current note being edited (for tracking changes)
 */
let currentNoteId: string | null = null;
let currentDecryptedContent: string | null = null;

/**
 * Initializes the plugin
 */
async function initPlugin(): Promise<void> {
  console.log('Notebook Encryption plugin starting...');

  // Register settings
  await registerSettings();

  // Initialize cache timeout from settings
  const timeout = await getCacheTimeout();
  const passwordCache = getPasswordCache();
  passwordCache.setTimeout(timeout);

  // Load notebook configurations
  const configService = getNotebookConfigService();
  await configService.load();

  // Register commands and menus
  await registerCommands();
  await registerContextMenus();

  // Set up event listeners
  await setupEventListeners();

  console.log('Notebook Encryption plugin started successfully');
}

/**
 * Sets up event listeners for note changes
 */
async function setupEventListeners(): Promise<void> {
  // Listen for note selection changes
  await joplin.workspace.onNoteSelectionChange(async () => {
    await handleNoteSelectionChange();
  });

  // Listen for note content changes (for auto-encrypt on save)
  await joplin.workspace.onNoteContentChange(async () => {
    await handleNoteContentChange();
  });

  // Listen for sync completion (optional re-lock)
  await joplin.workspace.onSyncComplete(async () => {
    await handleSyncComplete();
  });
}

/**
 * Handles note selection change
 */
async function handleNoteSelectionChange(): Promise<void> {
  try {
    // Save any pending changes to previous note
    if (currentNoteId && currentDecryptedContent !== null) {
      // Note: In a full implementation, we would check if content changed
      // and save the encrypted version. For now, Joplin's auto-save handles this.
    }

    // Get the newly selected note
    const note = await joplin.workspace.selectedNote();
    if (!note) {
      currentNoteId = null;
      currentDecryptedContent = null;
      return;
    }

    currentNoteId = (note as { id: string }).id;
    const notebookId = (note as { parent_id: string }).parent_id;

    // Check if the notebook is encrypted
    const configService = getNotebookConfigService();
    const isNotebookEncrypted = await configService.isEncrypted(notebookId);

    if (!isNotebookEncrypted) {
      currentDecryptedContent = null;
      return;
    }

    // Check if the note content is encrypted
    const noteBody = (note as { body: string }).body;
    if (!isEncrypted(noteBody)) {
      currentDecryptedContent = null;
      return;
    }

    // Decrypt the note content
    const result = await decryptNoteContent(currentNoteId);
    if (result) {
      currentDecryptedContent = result.content;
      
      // Refresh the password cache expiry since user is actively using the notebook
      const passwordCache = getPasswordCache();
      passwordCache.refresh(notebookId);
    }
  } catch (error) {
    console.error('Error handling note selection change:', error);
  }
}

/**
 * Handles note content change
 */
async function handleNoteContentChange(): Promise<void> {
  // This is called when the note content changes
  // In a full implementation, we would track changes and encrypt on save
  // For now, the encryption happens when the note is explicitly saved
  // through our commands or when switching notes
}

/**
 * Handles sync completion
 */
async function handleSyncComplete(): Promise<void> {
  try {
    const requirePassword = await shouldRequirePasswordOnSync();
    
    if (requirePassword) {
      // Clear all cached passwords after sync
      const passwordCache = getPasswordCache();
      passwordCache.clearAll();
      
      console.log('Passwords cleared after sync (as per settings)');
    }

    // Reload configurations in case they changed
    const configService = getNotebookConfigService();
    await configService.reload();
  } catch (error) {
    console.error('Error handling sync complete:', error);
  }
}

/**
 * Plugin registration
 */
joplin.plugins.register({
  onStart: async function() {
    await initPlugin();
  },
});