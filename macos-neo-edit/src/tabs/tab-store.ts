import * as monaco from 'monaco-editor';
import { detectLanguage } from '../editor/languages';

export interface Tab {
  id: string;
  title: string;
  filePath: string | null;
  language: string;
  isDirty: boolean;
  model: monaco.editor.ITextModel;
}

type TabListener = () => void;

let tabs: Tab[] = [];
let activeId: string | null = null;
let untitledCounter = 0;
const listeners: TabListener[] = [];

function notify(): void {
  listeners.forEach((fn) => fn());
}

export function onTabsChange(fn: TabListener): void {
  listeners.push(fn);
}

export function getTabs(): Tab[] {
  return tabs;
}

export function getActiveTab(): Tab | null {
  return tabs.find((t) => t.id === activeId) ?? null;
}

export function getActiveId(): string | null {
  return activeId;
}

export function addTab(
  filePath: string | null = null,
  content: string = '',
  language?: string,
): Tab {
  const id = crypto.randomUUID();
  const lang = language ?? (filePath ? detectLanguage(filePath) : 'plaintext');
  const title = filePath ? filePath.split('/').pop()! : `Untitled-${++untitledCounter}`;
  const uri = monaco.Uri.parse(`file:///${id}`);
  const model = monaco.editor.createModel(content, lang, uri);

  const tab: Tab = { id, title, filePath, language: lang, isDirty: false, model };
  tabs.push(tab);
  activeId = id;

  model.onDidChangeContent(() => {
    if (!tab.isDirty) {
      tab.isDirty = true;
      notify();
    }
  });

  notify();
  return tab;
}

export function removeTab(id: string): void {
  const idx = tabs.findIndex((t) => t.id === id);
  if (idx === -1) return;

  const tab = tabs[idx];
  tab.model.dispose();
  tabs.splice(idx, 1);

  if (activeId === id) {
    if (tabs.length > 0) {
      const newIdx = Math.min(idx, tabs.length - 1);
      activeId = tabs[newIdx].id;
    } else {
      activeId = null;
    }
  }

  notify();
}

export function setActive(id: string): void {
  if (tabs.some((t) => t.id === id)) {
    activeId = id;
    notify();
  }
}

export function closeAll(): void {
  tabs.forEach((t) => t.model.dispose());
  tabs = [];
  activeId = null;
  untitledCounter = 0;
  notify();
}

export function markClean(id: string): void {
  const tab = tabs.find((t) => t.id === id);
  if (tab) {
    tab.isDirty = false;
    notify();
  }
}

export function updateTabInfo(
  id: string,
  filePath: string,
  language?: string,
): void {
  const tab = tabs.find((t) => t.id === id);
  if (tab) {
    tab.filePath = filePath;
    tab.title = filePath.split('/').pop()!;
    if (language) {
      tab.language = language;
      monaco.editor.setModelLanguage(tab.model, language);
    }
    notify();
  }
}

export function setTabLanguage(id: string, language: string): void {
  const tab = tabs.find((t) => t.id === id);
  if (tab) {
    tab.language = language;
    monaco.editor.setModelLanguage(tab.model, language);
    notify();
  }
}

export function getDirtyTabs(): Tab[] {
  return tabs.filter((t) => t.isDirty);
}
