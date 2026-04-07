/**
 * Note Handler
 * Handles encryption and decryption of notes when accessed
 */
/**
 * Decrypts note content if the notebook is encrypted
 * Returns the decrypted content or original content if not encrypted
 */
export declare function decryptNoteContent(noteId: string): Promise<{
    content: string;
    wasEncrypted: boolean;
} | null>;
/**
 * Encrypts note content if the notebook is encrypted
 * Returns the encrypted content or original content if not in encrypted notebook
 */
export declare function encryptNoteContent(noteId: string, content: string): Promise<string | null>;
/**
 * Saves an encrypted note
 */
export declare function saveEncryptedNote(noteId: string, plainContent: string): Promise<boolean>;
/**
 * Encrypts all notes in a notebook (including sub-notebooks)
 * Used when enabling encryption for a notebook
 */
export declare function encryptAllNotesInNotebook(notebookId: string, password: string): Promise<{
    success: number;
    failed: number;
}>;
/**
 * Decrypts all notes in a notebook (including sub-notebooks)
 * Used when disabling encryption for a notebook
 */
export declare function decryptAllNotesInNotebook(notebookId: string, password: string): Promise<{
    success: number;
    failed: number;
}>;
/**
 * Re-encrypts all notes in a notebook with a new password
 */
export declare function reencryptAllNotesInNotebook(notebookId: string, oldPassword: string, newPassword: string): Promise<{
    success: number;
    failed: number;
}>;
//# sourceMappingURL=noteHandler.d.ts.map