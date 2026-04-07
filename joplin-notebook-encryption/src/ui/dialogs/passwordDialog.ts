/**
 * Password Dialog
 * Provides a modal dialog for password entry, setup, and change
 */

import joplin from 'api';
import { PasswordDialogResult } from '../../types';

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
function getUnlockDialogHtml(notebookName: string, error?: string): string {
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
function getSetupDialogHtml(notebookName: string, error?: string): string {
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
function getChangePasswordDialogHtml(notebookName: string, error?: string): string {
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
function escapeHtml(text: string): string {
  return text.replace(/[&<>"']/g, (char) => {
    const entities: Record<string, string> = {
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
export class PasswordDialogManager {
  private dialogHandle: string | null = null;

  /**
   * Shows an unlock password dialog
   */
  async showUnlockDialog(notebookName: string, error?: string): Promise<PasswordDialogResult> {
    const handle = await this.ensureDialog();

    await joplin.views.dialogs.setHtml(handle, getUnlockDialogHtml(notebookName, error));
    await joplin.views.dialogs.setButtons(handle, [
      { id: 'ok', title: 'Unlock' },
      { id: 'cancel', title: 'Cancel' },
    ]);
    await joplin.views.dialogs.setFitToContent(handle, true);

    const result = await joplin.views.dialogs.open(handle);

    if (result.id === 'ok' && result.formData) {
      const password = (result.formData as Record<string, Record<string, string>>)['password-form']
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
  async showSetupDialog(notebookName: string, error?: string): Promise<PasswordDialogResult> {
    const handle = await this.ensureDialog();

    await joplin.views.dialogs.setHtml(handle, getSetupDialogHtml(notebookName, error));
    await joplin.views.dialogs.setButtons(handle, [
      { id: 'ok', title: 'Encrypt' },
      { id: 'cancel', title: 'Cancel' },
    ]);
    await joplin.views.dialogs.setFitToContent(handle, true);

    const result = await joplin.views.dialogs.open(handle);

    if (result.id === 'ok' && result.formData) {
      const password = (result.formData as Record<string, Record<string, string>>)['password-form']
        ?.password;
      const confirmPassword = (result.formData as Record<string, Record<string, string>>)[
        'password-form'
      ]?.confirmPassword;

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
  async showChangePasswordDialog(
    notebookName: string,
    error?: string
  ): Promise<PasswordDialogResult> {
    const handle = await this.ensureDialog();

    await joplin.views.dialogs.setHtml(handle, getChangePasswordDialogHtml(notebookName, error));
    await joplin.views.dialogs.setButtons(handle, [
      { id: 'ok', title: 'Change' },
      { id: 'cancel', title: 'Cancel' },
    ]);
    await joplin.views.dialogs.setFitToContent(handle, true);

    const result = await joplin.views.dialogs.open(handle);

    if (result.id === 'ok' && result.formData) {
      const currentPassword = (result.formData as Record<string, Record<string, string>>)[
        'password-form'
      ]?.currentPassword;
      const newPassword = (result.formData as Record<string, Record<string, string>>)[
        'password-form'
      ]?.newPassword;
      const confirmPassword = (result.formData as Record<string, Record<string, string>>)[
        'password-form'
      ]?.confirmPassword;

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
  private async ensureDialog(): Promise<string> {
    if (!this.dialogHandle) {
      this.dialogHandle = await joplin.views.dialogs.create('notebook-encryption-dialog');
    }
    return this.dialogHandle;
  }
}

// Singleton instance
let dialogManager: PasswordDialogManager | null = null;

/**
 * Gets the singleton password dialog manager instance
 */
export function getPasswordDialogManager(): PasswordDialogManager {
  if (!dialogManager) {
    dialogManager = new PasswordDialogManager();
  }
  return dialogManager;
}