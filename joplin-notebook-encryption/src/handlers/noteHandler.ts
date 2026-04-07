/**
 * Note Handler
 * Handles encryption and decryption of notes when accessed
 */

import joplin from 'api';
import { encrypt, decrypt, isEncrypted } from '../services/encryptionService';
import { getPasswordCache } from '../services/passwordCache';
import { getNotebookConfigService } from '../services/notebookConfigService';
import { getPasswordDialogManager } from '../ui/dialogs/passwordDialog';

// Type for API response
interface ApiListResponse<T> {
  items?: T[];
  has_more?: boolean;
}

interface NoteData {
  id: string;
  body: string;
  parent_id?: string;
}

interface FolderData {
  id: string;
  title?: string;
  parent_id?: string;
}

/**
 * Gets a note by ID with specified fields
 */
async function getNote(
  noteId: string
): Promise<{ id: string; title: string; body: string; parent_id: string } | null> {
  try {
    const note = await joplin.data.get(['notes', noteId], {
      fields: ['id', 'title', 'body', 'parent_id'],
    });
    return note as { id: string; title: string; body: string; parent_id: string };
  } catch {
    return null;
  }
}

/**
 * Gets a folder/notebook by ID
 */
async function getFolder(folderId: string): Promise<{ id: string; title: string } | null> {
  try {
    const folder = await joplin.data.get(['folders', folderId], { fields: ['id', 'title'] });
    return folder as { id: string; title: string };
  } catch {
    return null;
  }
}

/**
 * Gets all folders from the database
 */
async function getAllFolders(): Promise<FolderData[]> {
  const folders: FolderData[] = [];
  let page = 1;
  let hasMore = true;

  while (hasMore) {
    try {
      const response = await joplin.data.get(['folders'], {
        fields: ['id', 'title', 'parent_id'],
        page,
        limit: 100,
      });

      let items: FolderData[] = [];
      
      if (Array.isArray(response)) {
        items = response as FolderData[];
        hasMore = false;
      } else if (response && typeof response === 'object') {
        const apiResponse = response as ApiListResponse<FolderData>;
        if (apiResponse.items && Array.isArray(apiResponse.items)) {
          items = apiResponse.items;
          hasMore = apiResponse.has_more === true;
        } else {
          hasMore = false;
        }
      } else {
        hasMore = false;
      }

      folders.push(...items);
      page++;
    } catch (error) {
      console.error('Error fetching folders:', error);
      hasMore = false;
    }
  }

  return folders;
}

/**
 * Gets all child folder IDs recursively (including the parent folder)
 */
function getChildFolderIds(folderId: string, allFolders: FolderData[]): Set<string> {
  const result = new Set<string>();
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
async function promptForPassword(notebookId: string): Promise<string | null> {
  const configService = getNotebookConfigService();
  const dialogManager = getPasswordDialogManager();
  const passwordCache = getPasswordCache();

  const folder = await getFolder(notebookId);
  const notebookName = folder?.title || 'Unknown Notebook';

  let error: string | undefined;
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
  await joplin.views.dialogs.showMessageBox(
    'Maximum password attempts reached. Please try again later.'
  );
  return null;
}

/**
 * Gets the decryption password for a notebook
 * Returns cached password or prompts user
 */
async function getPassword(notebookId: string): Promise<string | null> {
  const passwordCache = getPasswordCache();

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
export async function decryptNoteContent(
  noteId: string
): Promise<{ content: string; wasEncrypted: boolean } | null> {
  const note = await getNote(noteId);
  if (!note) {
    return null;
  }

  const configService = getNotebookConfigService();
  const notebookId = note.parent_id;

  // Check if notebook is encrypted (check parent hierarchy)
  const allFolders = await getAllFolders();
  const encryptedParentId = await findEncryptedParent(notebookId, allFolders, configService);
  
  if (!encryptedParentId) {
    return { content: note.body, wasEncrypted: false };
  }

  // Check if content is actually encrypted
  if (!isEncrypted(note.body)) {
    // Content not encrypted yet (new note in encrypted notebook)
    return { content: note.body, wasEncrypted: false };
  }

  // Get password (from cache or prompt)
  const password = await getPassword(encryptedParentId);
  if (!password) {
    return null; // User cancelled password prompt
  }

  // Decrypt content
  const result = await decrypt(password, note.body);
  if (!result.success) {
    console.error('Failed to decrypt note:', result.error);
    await joplin.views.dialogs.showMessageBox(`Failed to decrypt note: ${result.error}`);
    return null;
  }

  return { content: result.plaintext || '', wasEncrypted: true };
}

/**
 * Finds the encrypted parent folder in the hierarchy
 */
async function findEncryptedParent(
  folderId: string,
  allFolders: FolderData[],
  configService: ReturnType<typeof getNotebookConfigService>
): Promise<string | null> {
  let currentId: string | null = folderId;
  
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
export async function encryptNoteContent(
  noteId: string,
  content: string
): Promise<string | null> {
  const note = await getNote(noteId);
  if (!note) {
    return content; // Return original content if note not found
  }

  const configService = getNotebookConfigService();
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
    const encryptedContent = await encrypt(password, content);
    return encryptedContent;
  } catch (error) {
    console.error('Failed to encrypt note:', error);
    await joplin.views.dialogs.showMessageBox(`Failed to encrypt note: ${error}`);
    return null;
  }
}

/**
 * Saves an encrypted note
 */
export async function saveEncryptedNote(noteId: string, plainContent: string): Promise<boolean> {
  const encryptedContent = await encryptNoteContent(noteId, plainContent);
  if (encryptedContent === null) {
    return false; // Encryption failed or cancelled
  }

  try {
    await joplin.data.put(['notes', noteId], null, { body: encryptedContent });
    return true;
  } catch (error) {
    console.error('Failed to save encrypted note:', error);
    return false;
  }
}

/**
 * Gets all notes in a folder and its sub-folders
 */
async function getNotesInFolderRecursive(folderId: string): Promise<NoteData[]> {
  const notes: NoteData[] = [];

  // Get all folders to build the tree
  const allFolders = await getAllFolders();
  
  // Get all folder IDs that are children of this folder (including itself)
  const targetFolderIds = getChildFolderIds(folderId, allFolders);

  // Fetch all notes and filter by parent_id
  let page = 1;
  let hasMore = true;

  while (hasMore) {
    try {
      const response = await joplin.data.get(['notes'], {
        fields: ['id', 'body', 'parent_id'],
        page,
        limit: 100,
      });

      let items: NoteData[] = [];
      
      if (Array.isArray(response)) {
        items = response as NoteData[];
        hasMore = false;
      } else if (response && typeof response === 'object') {
        const apiResponse = response as ApiListResponse<NoteData>;
        if (apiResponse.items && Array.isArray(apiResponse.items)) {
          items = apiResponse.items;
          hasMore = apiResponse.has_more === true;
        } else {
          hasMore = false;
        }
      } else {
        hasMore = false;
      }

      // Filter by parent_id matching any of the target folders
      for (const item of items) {
        if (item.parent_id && targetFolderIds.has(item.parent_id)) {
          notes.push({ id: item.id, body: item.body, parent_id: item.parent_id });
        }
      }
      
      page++;
    } catch (error) {
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
export async function encryptAllNotesInNotebook(
  notebookId: string,
  password: string
): Promise<{ success: number; failed: number }> {
  const result = { success: 0, failed: 0 };

  const notes = await getNotesInFolderRecursive(notebookId);

  for (const note of notes) {
    // Skip if already encrypted
    if (isEncrypted(note.body)) {
      result.success++;
      continue;
    }

    // Skip empty notes
    if (!note.body || note.body.trim() === '') {
      result.success++;
      continue;
    }

    try {
      const encryptedContent = await encrypt(password, note.body);
      await joplin.data.put(['notes', note.id], null, { body: encryptedContent });
      result.success++;
    } catch (error) {
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
export async function decryptAllNotesInNotebook(
  notebookId: string,
  password: string
): Promise<{ success: number; failed: number }> {
  const result = { success: 0, failed: 0 };

  const notes = await getNotesInFolderRecursive(notebookId);

  for (const note of notes) {
    // Skip if not encrypted
    if (!isEncrypted(note.body)) {
      result.success++;
      continue;
    }

    try {
      const decryptResult = await decrypt(password, note.body);
      if (decryptResult.success && decryptResult.plaintext) {
        await joplin.data.put(['notes', note.id], null, { body: decryptResult.plaintext });
        result.success++;
      } else {
        result.failed++;
      }
    } catch (error) {
      console.error(`Failed to decrypt note ${note.id}:`, error);
      result.failed++;
    }
  }

  return result;
}

/**
 * Re-encrypts all notes in a notebook with a new password
 */
export async function reencryptAllNotesInNotebook(
  notebookId: string,
  oldPassword: string,
  newPassword: string
): Promise<{ success: number; failed: number }> {
  const result = { success: 0, failed: 0 };

  const notes = await getNotesInFolderRecursive(notebookId);

  for (const note of notes) {
    if (!isEncrypted(note.body)) {
      // Encrypt unencrypted notes with new password
      try {
        const encryptedContent = await encrypt(newPassword, note.body);
        await joplin.data.put(['notes', note.id], null, { body: encryptedContent });
        result.success++;
      } catch {
        result.failed++;
      }
      continue;
    }

    try {
      // Decrypt with old password
      const decryptResult = await decrypt(oldPassword, note.body);
      if (!decryptResult.success || !decryptResult.plaintext) {
        result.failed++;
        continue;
      }

      // Re-encrypt with new password
      const encryptedContent = await encrypt(newPassword, decryptResult.plaintext);
      await joplin.data.put(['notes', note.id], null, { body: encryptedContent });
      result.success++;
    } catch (error) {
      console.error(`Failed to re-encrypt note ${note.id}:`, error);
      result.failed++;
    }
  }

  return result;
}