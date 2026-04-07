import * as monaco from 'monaco-editor';
import { getEditor } from '../editor/editor-manager';
import { getActiveTab } from '../tabs/tab-store';

let outlineEl: HTMLElement | null = null;
let visible = false;
let debounceTimer: ReturnType<typeof setTimeout> | null = null;
let contentDisposable: { dispose(): void } | null = null;
let cursorDisposable: { dispose(): void } | null = null;

interface Heading {
  level: number;
  text: string;
  lineNumber: number;
}

function parseHeadings(content: string): Heading[] {
  const headings: Heading[] = [];
  const lines = content.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const match = lines[i].match(/^(#{1,6})\s+(.+)$/);
    if (match) {
      headings.push({
        level: match[1].length,
        text: match[2].replace(/\s*#+\s*$/, ''), // strip trailing #
        lineNumber: i + 1,
      });
    }
  }
  return headings;
}

function renderOutline(headings: Heading[]): void {
  if (!outlineEl) return;

  const list = outlineEl.querySelector('.outline-list');
  if (!list) return;
  list.innerHTML = '';

  if (headings.length === 0) {
    list.innerHTML = '<div class="outline-empty">No headings found</div>';
    return;
  }

  const editor = getEditor();

  for (const h of headings) {
    const item = document.createElement('div');
    item.className = `outline-item outline-h${h.level}`;
    item.textContent = h.text;
    item.title = `Line ${h.lineNumber}`;
    item.addEventListener('click', () => {
      if (editor) {
        editor.revealLineInCenter(h.lineNumber);
        editor.setPosition({ lineNumber: h.lineNumber, column: 1 });
        editor.focus();
      }
    });
    list.appendChild(item);
  }
}

function updateOutline(): void {
  const tab = getActiveTab();
  if (!tab || tab.language !== 'markdown') return;

  const headings = parseHeadings(tab.model.getValue());
  renderOutline(headings);
}

function scheduleUpdate(): void {
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(updateOutline, 300);
}

export function getBreadcrumb(): string {
  const tab = getActiveTab();
  if (!tab || tab.language !== 'markdown') return '';

  const editor = getEditor();
  const pos = editor?.getPosition();
  if (!pos) return '';

  const headings = parseHeadings(tab.model.getValue());
  const currentLine = pos.lineNumber;

  // Find the heading hierarchy at cursor position
  const breadcrumb: string[] = [];
  const stack: Heading[] = [];

  for (const h of headings) {
    if (h.lineNumber > currentLine) break;

    // Pop headings of same or higher level
    while (stack.length > 0 && stack[stack.length - 1].level >= h.level) {
      stack.pop();
    }
    stack.push(h);
  }

  for (const h of stack) {
    breadcrumb.push(h.text);
  }

  return breadcrumb.join(' > ');
}

export function isOutlineVisible(): boolean {
  return visible;
}

export function toggleOutline(): void {
  visible = !visible;
  const el = document.getElementById('outline-sidebar');
  if (el) {
    el.classList.toggle('hidden', !visible);
  }

  if (visible) {
    updateOutline();
    attachListeners();
  } else {
    detachListeners();
  }

  getEditor()?.layout();
}

function attachListeners(): void {
  const editor = getEditor();
  if (!editor) return;

  contentDisposable?.dispose();
  cursorDisposable?.dispose();

  contentDisposable = editor.onDidChangeModelContent(() => scheduleUpdate());
  cursorDisposable = editor.onDidChangeCursorPosition(() => {
    // breadcrumb updated via status bar
  });
}

function detachListeners(): void {
  contentDisposable?.dispose();
  contentDisposable = null;
  cursorDisposable?.dispose();
  cursorDisposable = null;
}

export function showOutlineIfMarkdown(): void {
  const tab = getActiveTab();
  const isMarkdown = tab?.language === 'markdown';

  const el = document.getElementById('outline-sidebar');
  if (el) {
    el.classList.toggle('hidden', !isMarkdown || !visible);
  }

  if (isMarkdown && visible) {
    updateOutline();
    attachListeners();
  } else {
    detachListeners();
  }

  getEditor()?.layout();
}

export function initOutline(): void {
  outlineEl = document.getElementById('outline-sidebar');
}
