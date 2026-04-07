/**
 * Plugin Commands
 * Registers commands and context menu actions for notebook encryption
 */

import joplin from 'api';
import { MenuItemLocation } from 'api/types';
import { getNotebookConfigService } from './services/notebookConfigService';
import { getPasswordCache } from './services/passwordCache';
import { getPasswordDialogManager } from './ui/dialogs/passwordDialog';
import {
  encryptAllNotesInNotebook,
  decryptAllNotesInNotebook,
  reencryptAllNotesInNotebook,
} from './handlers/noteHandler';

/**
 * Command names
 */
export const COMMANDS = {
  ENABLE_ENCRYPTION: 'notebookEncryption.enableEncryption',
  DISABLE_ENCRYPTION: 'notebookEncryption.disableEncryption',
  CHANGE_PASSWORD: 'notebookEncryption.changePassword',
  LOCK_NOTEBOOK: 'notebookEncryption.lockNotebook',
  LOCK_ALL: 'notebookEncryption.lockAll',
};

/**
 * Gets the currently selected folder
 */
async function getSelectedFolder(): Promise<{ id: string; title: string } | null> {
  try {
    const folder = await joplin.workspace.selectedFolder();
    return folder as { id: string; title: string } | null;
  } catch {
    return null;
  }
}

/**
 * Registers all plugin commands
 */
export async function registerCommands(): Promise<void> {
  // Command: Enable Encryption
  await joplin.commands.register({
    name: COMMANDS.ENABLE_ENCRYPTION,
    label: '🔐 Encrypt Notebook',
    iconName: 'fas fa-lock',
    execute: async () => {
      const folder = await getSelectedFolder();
      if (!folder) {
        await joplin.views.dialogs.showMessageBox('Please select a notebook first.');
        return;
      }

      const configService = getNotebookConfigService();
      const dialogManager = getPasswordDialogManager();

      // Check if already encrypted
      if (await configService.isEncrypted(folder.id)) {
        await joplin.views.dialogs.showMessageBox('This notebook is already encrypted.');
        return;
      }

      // Show setup dialog
      const result = await dialogManager.showSetupDialog(folder.title);
      if (!result.submitted || !result.password) {
        return; // User cancelled
      }

      try {
        // Show progress message
        await joplin.views.dialogs.showMessageBox(
          `Encrypting notebook "${folder.title}"...\n\nThis may take a moment depending on the number of notes.`
        );

        // Enable encryption
        await configService.enableEncryption(folder.id, result.password);

        // Encrypt all existing notes
        const encryptResult = await encryptAllNotesInNotebook(folder.id, result.password);

        // Cache the password
        const passwordCache = getPasswordCache();
        passwordCache.set(folder.id, result.password);

        // Show result
        await joplin.views.dialogs.showMessageBox(
          `Encryption enabled for "${folder.title}"!\n\n` +
            `Notes encrypted: ${encryptResult.success}\n` +
            `Failed: ${encryptResult.failed}`
        );
      } catch (error) {
        console.error('Failed to enable encryption:', error);
        await joplin.views.dialogs.showMessageBox(`Failed to enable encryption: ${error}`);
      }
    },
  });

  // Command: Disable Encryption
  await joplin.commands.register({
    name: COMMANDS.DISABLE_ENCRYPTION,
    label: '🔓 Decrypt Notebook',
    iconName: 'fas fa-unlock',
    execute: async () => {
      const folder = await getSelectedFolder();
      if (!folder) {
        await joplin.views.dialogs.showMessageBox('Please select a notebook first.');
        return;
      }

      const configService = getNotebookConfigService();
      const dialogManager = getPasswordDialogManager();

      // Check if not encrypted
      if (!(await configService.isEncrypted(folder.id))) {
        await joplin.views.dialogs.showMessageBox('This notebook is not encrypted.');
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
        await joplin.views.dialogs.showMessageBox('Incorrect password.');
        return;
      }

      try {
        // Show progress message
        await joplin.views.dialogs.showMessageBox(
          `Decrypting notebook "${folder.title}"...\n\nThis may take a moment depending on the number of notes.`
        );

        // Decrypt all notes
        const decryptResult = await decryptAllNotesInNotebook(folder.id, result.password);

        // Disable encryption
        await configService.disableEncryption(folder.id, result.password);

        // Clear password from cache
        const passwordCache = getPasswordCache();
        passwordCache.clear(folder.id);

        // Show result
        await joplin.views.dialogs.showMessageBox(
          `Encryption disabled for "${folder.title}"!\n\n` +
            `Notes decrypted: ${decryptResult.success}\n` +
            `Failed: ${decryptResult.failed}`
        );
      } catch (error) {
        console.error('Failed to disable encryption:', error);
        await joplin.views.dialogs.showMessageBox(`Failed to disable encryption: ${error}`);
      }
    },
  });

  // Command: Change Password
  await joplin.commands.register({
    name: COMMANDS.CHANGE_PASSWORD,
    label: '🔑 Change Password',
    iconName: 'fas fa-key',
    execute: async () => {
      const folder = await getSelectedFolder();
      if (!folder) {
        await joplin.views.dialogs.showMessageBox('Please select a notebook first.');
        return;
      }

      const configService = getNotebookConfigService();
      const dialogManager = getPasswordDialogManager();

      // Check if encrypted
      if (!(await configService.isEncrypted(folder.id))) {
        await joplin.views.dialogs.showMessageBox('This notebook is not encrypted.');
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
        await joplin.views.dialogs.showMessageBox('Incorrect current password.');
        return;
      }

      try {
        // Show progress message
        await joplin.views.dialogs.showMessageBox(
          `Changing password for "${folder.title}"...\n\nThis may take a moment as all notes need to be re-encrypted.`
        );

        // Re-encrypt all notes with new password
        const reencryptResult = await reencryptAllNotesInNotebook(
          folder.id,
          result.password,
          result.newPassword
        );

        // Update password hash in config
        await configService.changePassword(folder.id, result.password, result.newPassword);

        // Update cache with new password
        const passwordCache = getPasswordCache();
        passwordCache.set(folder.id, result.newPassword);

        // Show result
        await joplin.views.dialogs.showMessageBox(
          `Password changed for "${folder.title}"!\n\n` +
            `Notes re-encrypted: ${reencryptResult.success}\n` +
            `Failed: ${reencryptResult.failed}`
        );
      } catch (error) {
        console.error('Failed to change password:', error);
        await joplin.views.dialogs.showMessageBox(`Failed to change password: ${error}`);
      }
    },
  });

  // Command: Lock Notebook (clear cache)
  await joplin.commands.register({
    name: COMMANDS.LOCK_NOTEBOOK,
    label: '🔒 Lock Notebook',
    iconName: 'fas fa-lock',
    execute: async () => {
      const folder = await getSelectedFolder();
      if (!folder) {
        await joplin.views.dialogs.showMessageBox('Please select a notebook first.');
        return;
      }

      const configService = getNotebookConfigService();
      const passwordCache = getPasswordCache();

      // Check if encrypted
      if (!(await configService.isEncrypted(folder.id))) {
        await joplin.views.dialogs.showMessageBox('This notebook is not encrypted.');
        return;
      }

      // Clear from cache
      passwordCache.clear(folder.id);

      await joplin.views.dialogs.showMessageBox(
        `Notebook "${folder.title}" has been locked.\n\nYou will need to enter the password to access notes again.`
      );
    },
  });

  // Command: Lock All Notebooks
  await joplin.commands.register({
    name: COMMANDS.LOCK_ALL,
    label: '🔒 Lock All Notebooks',
    iconName: 'fas fa-lock',
    execute: async () => {
      const passwordCache = getPasswordCache();
      passwordCache.clearAll();

      await joplin.views.dialogs.showMessageBox(
        'All encrypted notebooks have been locked.\n\nYou will need to enter passwords to access notes again.'
      );
    },
  });
}

/**
 * Registers context menu items for notebooks
 */
export async function registerContextMenus(): Promise<void> {
  // Enable Encryption menu item
  await joplin.views.menuItems.create(
    'contextMenu-enableEncryption',
    COMMANDS.ENABLE_ENCRYPTION,
    MenuItemLocation.FolderContextMenu
  );

  // Disable Encryption menu item
  await joplin.views.menuItems.create(
    'contextMenu-disableEncryption',
    COMMANDS.DISABLE_ENCRYPTION,
    MenuItemLocation.FolderContextMenu
  );

  // Change Password menu item
  await joplin.views.menuItems.create(
    'contextMenu-changePassword',
    COMMANDS.CHANGE_PASSWORD,
    MenuItemLocation.FolderContextMenu
  );

  // Lock Notebook menu item
  await joplin.views.menuItems.create(
    'contextMenu-lockNotebook',
    COMMANDS.LOCK_NOTEBOOK,
    MenuItemLocation.FolderContextMenu
  );
}

/**
 * Registers toolbar buttons
 */
export async function registerToolbarButtons(): Promise<void> {
  // Lock All button in Tools menu could be added here if needed
}