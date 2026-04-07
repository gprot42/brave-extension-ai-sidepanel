import * as monaco from 'monaco-editor';
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';
import jsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker';
import cssWorker from 'monaco-editor/esm/vs/language/css/css.worker?worker';
import htmlWorker from 'monaco-editor/esm/vs/language/html/html.worker?worker';
import tsWorker from 'monaco-editor/esm/vs/language/typescript/ts.worker?worker';
import { registerThemes, themeMap } from './themes';
import { settingsStore } from '../settings/settings-store';

// Configure Monaco workers
self.MonacoEnvironment = {
  getWorker(_: unknown, label: string) {
    if (label === 'json') return new jsonWorker();
    if (label === 'css' || label === 'scss' || label === 'less') return new cssWorker();
    if (label === 'html' || label === 'handlebars' || label === 'razor') return new htmlWorker();
    if (label === 'typescript' || label === 'javascript') return new tsWorker();
    return new editorWorker();
  },
};

let editor: monaco.editor.IStandaloneCodeEditor | null = null;

export function initEditor(container: HTMLElement): monaco.editor.IStandaloneCodeEditor {
  registerThemes();

  const settings = settingsStore.get();
  const monacoTheme = themeMap[settings.theme] ?? 'neo-tokyo-night';

  editor = monaco.editor.create(container, {
    value: '',
    language: 'plaintext',
    theme: monacoTheme,
    fontSize: settings.fontSize,
    fontFamily: "'SF Mono', 'Fira Code', 'JetBrains Mono', Menlo, Monaco, 'Courier New', monospace",
    lineNumbers: 'on',
    minimap: { enabled: false },
    wordWrap: settings.wordWrap as 'off' | 'on' | 'wordWrapColumn' | 'bounded',
    wordWrapColumn: settings.wordWrapColumn,
    scrollBeyondLastLine: false,
    automaticLayout: true,
    tabSize: 2,
    insertSpaces: true,
    renderWhitespace: 'selection',
    smoothScrolling: true,
    cursorSmoothCaretAnimation: 'on',
    padding: { top: 8 },
    bracketPairColorization: { enabled: true },
  });

  return editor;
}

export function getEditor(): monaco.editor.IStandaloneCodeEditor | null {
  return editor;
}

export function updateEditorOptions(options: monaco.editor.IEditorOptions): void {
  editor?.updateOptions(options);
}

export function setEditorTheme(theme: string): void {
  const monacoTheme = themeMap[theme] ?? 'neo-tokyo-night';
  monaco.editor.setTheme(monacoTheme);
}

export function setEditorModel(model: monaco.editor.ITextModel | null): void {
  editor?.setModel(model);
}
