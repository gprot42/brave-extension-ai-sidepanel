import { open, save } from '@tauri-apps/plugin-dialog';
import { readTextFile, writeTextFile } from '@tauri-apps/plugin-fs';
import {
  addTab,
  getActiveTab,
  markClean,
  updateTabInfo,
  closeAll,
  getDirtyTabs,
  removeTab,
  getTabs,
  getActiveId,
} from '../tabs/tab-store';
import { setEditorModel, getEditor } from '../editor/editor-manager';
import { detectLanguage } from '../editor/languages';

export async function newFile(): Promise<void> {
  const tab = addTab();
  setEditorModel(tab.model);
  getEditor()?.focus();
}

export async function openFile(): Promise<void> {
  const result = await open({
    multiple: true,
    filters: [
      { name: 'All Files', extensions: ['*'] },
      { name: 'Text Files', extensions: ['txt', 'md', 'json', 'yaml', 'yml', 'toml', 'xml', 'html', 'css', 'js', 'ts', 'py', 'rs', 'go', 'java', 'c', 'cpp', 'h', 'hpp', 'cs', 'php', 'rb', 'swift', 'sql', 'sh'] },
    ],
  });

  if (!result) return;

  const paths = Array.isArray(result) ? result : [result];

  for (const filePath of paths) {
    if (typeof filePath !== 'string') continue;
    try {
      const content = await readTextFile(filePath);
      const lang = detectLanguage(filePath);
      const tab = addTab(filePath, content, lang);
      setEditorModel(tab.model);
      markClean(tab.id);
    } catch (err) {
      console.error('Failed to open file:', err);
    }
  }

  getEditor()?.focus();
}

export async function saveFile(): Promise<void> {
  const tab = getActiveTab();
  if (!tab) return;

  if (tab.filePath) {
    try {
      await writeTextFile(tab.filePath, tab.model.getValue());
      markClean(tab.id);
    } catch (err) {
      console.error('Failed to save file:', err);
    }
  } else {
    await saveFileAs();
  }
}

export async function saveFileAs(): Promise<void> {
  const tab = getActiveTab();
  if (!tab) return;

  const filePath = await save({
    filters: [
      { name: 'All Files', extensions: ['*'] },
    ],
  });

  if (!filePath) return;

  try {
    await writeTextFile(filePath, tab.model.getValue());
    const lang = detectLanguage(filePath);
    updateTabInfo(tab.id, filePath, lang);
    markClean(tab.id);
  } catch (err) {
    console.error('Failed to save file:', err);
  }
}

export async function closeTab(): Promise<void> {
  const tab = getActiveTab();
  if (!tab) return;

  if (tab.isDirty) {
    const shouldSave = confirm(`Save changes to "${tab.title}" before closing?`);
    if (shouldSave) {
      await saveFile();
    }
  }

  removeTab(tab.id);
  const tabs = getTabs();
  const activeId = getActiveId();
  const active = tabs.find((t) => t.id === activeId) ?? null;
  setEditorModel(active?.model ?? null);
}

export async function closeAllFiles(): Promise<void> {
  const dirty = getDirtyTabs();
  if (dirty.length > 0) {
    const shouldSave = confirm(`Save changes to ${dirty.length} file(s) before closing?`);
    if (shouldSave) {
      for (const tab of dirty) {
        if (tab.filePath) {
          await writeTextFile(tab.filePath, tab.model.getValue());
        }
      }
    }
  }
  closeAll();
  setEditorModel(null);
}
