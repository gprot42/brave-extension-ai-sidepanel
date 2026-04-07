/**
 * Password Dialog
 * Provides a modal dialog for password entry, setup, and change
 */
import { PasswordDialogResult } from '../../types';
/**
 * Password Dialog Manager
 */
export declare class PasswordDialogManager {
    private dialogHandle;
    /**
     * Shows an unlock password dialog
     */
    showUnlockDialog(notebookName: string, error?: string): Promise<PasswordDialogResult>;
    /**
     * Shows a setup encryption dialog
     */
    showSetupDialog(notebookName: string, error?: string): Promise<PasswordDialogResult>;
    /**
     * Shows a change password dialog
     */
    showChangePasswordDialog(notebookName: string, error?: string): Promise<PasswordDialogResult>;
    /**
     * Ensures the dialog exists and returns its handle
     */
    private ensureDialog;
}
/**
 * Gets the singleton password dialog manager instance
 */
export declare function getPasswordDialogManager(): PasswordDialogManager;
//# sourceMappingURL=passwordDialog.d.ts.map