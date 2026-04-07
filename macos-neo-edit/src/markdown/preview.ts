import { marked } from 'marked';
import { getEditor } from '../editor/editor-manager';
import { getActiveTab } from '../tabs/tab-store';
import { settingsStore } from '../settings/settings-store';

let previewEl: HTMLElement | null = null;
let visible = false;
let debounceTimer: ReturnType<typeof setTimeout> | null = null;
let scrollDisposable: { dispose(): void } | null = null;
let contentDisposable: { dispose(): void } | null = null;

const previewStyles: Record<string, string> = {
  light: `
    body { background: #fff; color: #24292f; }
    a { color: #0969da; }
    code { background: #f0f3f6; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
    pre { background: #f6f8fa; padding: 16px; border-radius: 6px; overflow-x: auto; }
    pre code { background: none; padding: 0; }
    blockquote { border-left: 4px solid #d1d9e0; padding: 0 16px; color: #636c76; margin: 16px 0; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #d1d9e0; padding: 8px 12px; text-align: left; }
    th { background: #f6f8fa; font-weight: 600; }
    hr { border: none; border-top: 2px solid #d1d9e0; margin: 24px 0; }
    img { max-width: 100%; }
    h1, h2 { border-bottom: 1px solid #d1d9e0; padding-bottom: 8px; }
    .task-list-item { list-style: none; }
    .task-list-item input { margin-right: 6px; }
  `,
  dark: `
    body { background: #1e1e1e; color: #d4d4d4; }
    a { color: #4fc1ff; }
    code { background: #2d2d2d; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; }
    pre { background: #252526; padding: 16px; border-radius: 6px; overflow-x: auto; }
    pre code { background: none; padding: 0; }
    blockquote { border-left: 4px solid #3c3c3c; padding: 0 16px; color: #858585; margin: 16px 0; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #3c3c3c; padding: 8px 12px; text-align: left; }
    th { background: #252526; font-weight: 600; }
    hr { border: none; border-top: 2px solid #3c3c3c; margin: 24px 0; }
    img { max-width: 100%; }
    h1, h2 { border-bottom: 1px solid #3c3c3c; padding-bottom: 8px; }
    .task-list-item { list-style: none; }
    .task-list-item input { margin-right: 6px; }
  `,
  'tokyo-night': `
    body { background: #1a1b26; color: #a9b1d6; }
    a { color: #7aa2f7; }
    code { background: #1f2335; padding: 2px 6px; border-radius: 4px; font-size: 0.9em; color: #9ece6a; }
    pre { background: #16161e; padding: 16px; border-radius: 6px; overflow-x: auto; }
    pre code { background: none; padding: 0; color: #a9b1d6; }
    blockquote { border-left: 4px solid #292e42; padding: 0 16px; color: #565f89; margin: 16px 0; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #292e42; padding: 8px 12px; text-align: left; }
    th { background: #16161e; font-weight: 600; }
    hr { border: none; border-top: 2px solid #292e42; margin: 24px 0; }
    img { max-width: 100%; }
    h1, h2 { border-bottom: 1px solid #292e42; padding-bottom: 8px; }
    h1 { color: #c0caf5; }
    h2 { color: #bb9af7; }
    h3 { color: #7aa2f7; }
    h4 { color: #7dcfff; }
    h5 { color: #73daca; }
    h6 { color: #9ece6a; }
    strong { color: #c0caf5; }
    .task-list-item { list-style: none; }
    .task-list-item input { margin-right: 6px; }
  `,
};

function getPreviewHTML(markdown: string): string {
  const theme = settingsStore.get().theme;
  const css = previewStyles[theme] ?? previewStyles['tokyo-night'];
  const html = marked.parse(markdown, { async: false }) as string;
  return `<!DOCTYPE html>
<html><head><style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
    font-size: 15px;
    line-height: 1.7;
    padding: 24px;
    word-wrap: break-word;
  }
  h1 { font-size: 2em; margin: 24px 0 16px; }
  h2 { font-size: 1.5em; margin: 24px 0 16px; }
  h3 { font-size: 1.25em; margin: 20px 0 12px; }
  h4, h5, h6 { margin: 16px 0 8px; }
  p { margin: 0 0 16px; }
  ul, ol { padding-left: 2em; margin: 0 0 16px; }
  li { margin: 4px 0; }
  ${css}
</style></head><body>${html}</body></html>`;
}

function renderPreview(): void {
  if (!visible || !previewEl) return;
  const tab = getActiveTab();
  if (!tab || tab.language !== 'markdown') return;

  const iframe = previewEl.querySelector('iframe');
  if (!iframe) return;

  const content = tab.model.getValue();
  const doc = iframe.contentDocument;
  if (doc) {
    const scrollY = doc.documentElement?.scrollTop ?? 0;
    doc.open();
    doc.write(getPreviewHTML(content));
    doc.close();
    doc.documentElement.scrollTop = scrollY;
  }
}

function scheduleRender(): void {
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(renderPreview, 150);
}

function syncScroll(): void {
  const editor = getEditor();
  if (!editor || !previewEl || !visible) return;

  const iframe = previewEl.querySelector('iframe');
  if (!iframe?.contentDocument) return;

  const editorScrollTop = editor.getScrollTop();
  const editorScrollHeight = editor.getScrollHeight() - editor.getLayoutInfo().height;
  if (editorScrollHeight <= 0) return;

  const ratio = editorScrollTop / editorScrollHeight;
  const previewDoc = iframe.contentDocument.documentElement;
  const previewScrollHeight = previewDoc.scrollHeight - previewDoc.clientHeight;
  previewDoc.scrollTop = ratio * previewScrollHeight;
}

export function isPreviewVisible(): boolean {
  return visible;
}

export function togglePreview(): void {
  visible = !visible;
  const el = document.getElementById('markdown-preview');
  if (el) {
    el.classList.toggle('hidden', !visible);
  }

  const editor = getEditor();

  if (visible) {
    renderPreview();
    if (editor) {
      scrollDisposable = editor.onDidScrollChange(() => syncScroll());
      contentDisposable = editor.onDidChangeModelContent(() => scheduleRender());
    }
  } else {
    scrollDisposable?.dispose();
    scrollDisposable = null;
    contentDisposable?.dispose();
    contentDisposable = null;
  }

  // Trigger layout recalc
  editor?.layout();
}

export function showPreviewIfMarkdown(): void {
  const tab = getActiveTab();
  const isMarkdown = tab?.language === 'markdown';

  if (isMarkdown && visible) {
    renderPreview();
    const editor = getEditor();
    if (editor) {
      scrollDisposable?.dispose();
      contentDisposable?.dispose();
      scrollDisposable = editor.onDidScrollChange(() => syncScroll());
      contentDisposable = editor.onDidChangeModelContent(() => scheduleRender());
    }
  }

  const el = document.getElementById('markdown-preview');
  if (el) {
    el.classList.toggle('hidden', !isMarkdown || !visible);
  }

  getEditor()?.layout();
}

export function initPreview(): void {
  previewEl = document.getElementById('markdown-preview');
  if (!previewEl) return;

  const iframe = document.createElement('iframe');
  iframe.style.width = '100%';
  iframe.style.height = '100%';
  iframe.style.border = 'none';
  previewEl.appendChild(iframe);

  // Re-render when theme changes
  settingsStore.onChange(() => {
    if (visible) renderPreview();
  });
}

export function getPreviewHTMLForExport(): string {
  const tab = getActiveTab();
  if (!tab) return '';
  return getPreviewHTML(tab.model.getValue());
}
