import * as monaco from 'monaco-editor';
import { getEditor } from '../editor/editor-manager';
import { getActiveTab } from '../tabs/tab-store';

function isMarkdown(): boolean {
  return getActiveTab()?.language === 'markdown';
}

function wrapSelection(wrapper: string): void {
  const editor = getEditor();
  if (!editor || !isMarkdown()) return;

  const selection = editor.getSelection();
  if (!selection) return;

  const model = editor.getModel();
  if (!model) return;

  const text = model.getValueInRange(selection);

  // Toggle: if already wrapped, unwrap
  if (text.startsWith(wrapper) && text.endsWith(wrapper) && text.length >= wrapper.length * 2) {
    editor.executeEdits('markdown-format', [{
      range: selection,
      text: text.slice(wrapper.length, -wrapper.length),
    }]);
    return;
  }

  // Check surrounding context for unwrap
  const beforeRange = new monaco.Range(
    selection.startLineNumber,
    Math.max(1, selection.startColumn - wrapper.length),
    selection.startLineNumber,
    selection.startColumn,
  );
  const afterRange = new monaco.Range(
    selection.endLineNumber,
    selection.endColumn,
    selection.endLineNumber,
    selection.endColumn + wrapper.length,
  );
  const before = model.getValueInRange(beforeRange);
  const after = model.getValueInRange(afterRange);

  if (before === wrapper && after === wrapper) {
    editor.executeEdits('markdown-format', [
      { range: new monaco.Range(beforeRange.startLineNumber, beforeRange.startColumn, afterRange.endLineNumber, afterRange.endColumn), text },
    ]);
    return;
  }

  // Wrap
  editor.executeEdits('markdown-format', [{
    range: selection,
    text: `${wrapper}${text || 'text'}${wrapper}`,
  }]);
}

function toggleHeading(level: number): void {
  const editor = getEditor();
  if (!editor || !isMarkdown()) return;

  const model = editor.getModel();
  const pos = editor.getPosition();
  if (!model || !pos) return;

  const lineNumber = pos.lineNumber;
  const lineContent = model.getLineContent(lineNumber);
  const headingMatch = lineContent.match(/^(#{1,6})\s/);
  const prefix = '#'.repeat(level) + ' ';

  let newLine: string;
  if (headingMatch) {
    const existing = headingMatch[1].length;
    if (existing === level) {
      // Remove heading
      newLine = lineContent.replace(/^#{1,6}\s/, '');
    } else {
      // Change level
      newLine = lineContent.replace(/^#{1,6}\s/, prefix);
    }
  } else {
    newLine = prefix + lineContent;
  }

  const range = new monaco.Range(lineNumber, 1, lineNumber, lineContent.length + 1);
  editor.executeEdits('markdown-format', [{ range, text: newLine }]);
}

function insertLink(): void {
  const editor = getEditor();
  if (!editor || !isMarkdown()) return;

  const selection = editor.getSelection();
  const model = editor.getModel();
  if (!selection || !model) return;

  const text = model.getValueInRange(selection) || 'link text';
  editor.executeEdits('markdown-format', [{
    range: selection,
    text: `[${text}](url)`,
  }]);
}

function insertImage(): void {
  const editor = getEditor();
  if (!editor || !isMarkdown()) return;

  const selection = editor.getSelection();
  if (!selection) return;

  editor.executeEdits('markdown-format', [{
    range: selection,
    text: '![alt text](image-url)',
  }]);
}

function toggleCodeBlock(): void {
  const editor = getEditor();
  if (!editor || !isMarkdown()) return;

  const selection = editor.getSelection();
  const model = editor.getModel();
  if (!selection || !model) return;

  const text = model.getValueInRange(selection);

  if (selection.startLineNumber !== selection.endLineNumber || text.includes('\n')) {
    // Multi-line: fenced code block
    if (text.startsWith('```') && text.endsWith('```')) {
      const inner = text.slice(text.indexOf('\n') + 1, text.lastIndexOf('\n'));
      editor.executeEdits('markdown-format', [{ range: selection, text: inner }]);
    } else {
      editor.executeEdits('markdown-format', [{ range: selection, text: `\`\`\`\n${text}\n\`\`\`` }]);
    }
  } else {
    // Single line: inline code
    wrapSelection('`');
  }
}

function toggleBlockquote(): void {
  const editor = getEditor();
  if (!editor || !isMarkdown()) return;

  const selection = editor.getSelection();
  const model = editor.getModel();
  if (!selection || !model) return;

  const startLine = selection.startLineNumber;
  const endLine = selection.endLineNumber;
  const lines: string[] = [];
  let allQuoted = true;

  for (let i = startLine; i <= endLine; i++) {
    const line = model.getLineContent(i);
    if (!line.startsWith('> ')) allQuoted = false;
    lines.push(line);
  }

  const newLines = allQuoted
    ? lines.map((l) => l.replace(/^> /, ''))
    : lines.map((l) => `> ${l}`);

  const range = new monaco.Range(startLine, 1, endLine, model.getLineContent(endLine).length + 1);
  editor.executeEdits('markdown-format', [{ range, text: newLines.join('\n') }]);
}

function insertHorizontalRule(): void {
  const editor = getEditor();
  if (!editor || !isMarkdown()) return;

  const pos = editor.getPosition();
  if (!pos) return;

  const model = editor.getModel();
  if (!model) return;

  const lineContent = model.getLineContent(pos.lineNumber);
  const range = new monaco.Range(pos.lineNumber, lineContent.length + 1, pos.lineNumber, lineContent.length + 1);
  editor.executeEdits('markdown-format', [{ range, text: '\n\n---\n\n' }]);
}

let actionsRegistered = false;

export function registerFormattingActions(): void {
  const editor = getEditor();
  if (!editor || actionsRegistered) return;
  actionsRegistered = true;

  editor.addAction({
    id: 'md.bold',
    label: 'Markdown: Bold',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyB],
    precondition: undefined,
    run: () => wrapSelection('**'),
  });

  editor.addAction({
    id: 'md.italic',
    label: 'Markdown: Italic',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyI],
    precondition: undefined,
    run: () => wrapSelection('*'),
  });

  editor.addAction({
    id: 'md.strikethrough',
    label: 'Markdown: Strikethrough',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyX],
    precondition: undefined,
    run: () => wrapSelection('~~'),
  });

  editor.addAction({
    id: 'md.link',
    label: 'Markdown: Insert Link',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.KeyK],
    precondition: undefined,
    run: () => insertLink(),
  });

  editor.addAction({
    id: 'md.image',
    label: 'Markdown: Insert Image',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyK],
    precondition: undefined,
    run: () => insertImage(),
  });

  editor.addAction({
    id: 'md.code',
    label: 'Markdown: Toggle Code',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyCode.Backquote],
    precondition: undefined,
    run: () => toggleCodeBlock(),
  });

  editor.addAction({
    id: 'md.blockquote',
    label: 'Markdown: Toggle Blockquote',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.Period],
    precondition: undefined,
    run: () => toggleBlockquote(),
  });

  editor.addAction({
    id: 'md.hr',
    label: 'Markdown: Insert Horizontal Rule',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.Minus],
    precondition: undefined,
    run: () => insertHorizontalRule(),
  });

  for (let i = 1; i <= 6; i++) {
    const keyCode = [
      monaco.KeyCode.Digit1, monaco.KeyCode.Digit2, monaco.KeyCode.Digit3,
      monaco.KeyCode.Digit4, monaco.KeyCode.Digit5, monaco.KeyCode.Digit6,
    ][i - 1];
    editor.addAction({
      id: `md.heading${i}`,
      label: `Markdown: Heading ${i}`,
      keybindings: [monaco.KeyMod.CtrlCmd | keyCode],
      precondition: undefined,
      run: () => toggleHeading(i),
    });
  }
}

// Toolbar rendering
export function renderFormattingToolbar(): void {
  let toolbar = document.getElementById('md-toolbar');
  if (!toolbar) return;

  toolbar.innerHTML = '';

  const buttons: Array<{ icon: string; title: string; action: () => void }> = [
    { icon: 'B', title: 'Bold (Cmd+B)', action: () => wrapSelection('**') },
    { icon: 'I', title: 'Italic (Cmd+I)', action: () => wrapSelection('*') },
    { icon: 'S', title: 'Strikethrough (Cmd+Shift+X)', action: () => wrapSelection('~~') },
    { icon: '<>', title: 'Code (Cmd+`)', action: () => toggleCodeBlock() },
    { icon: '---', title: 'Horizontal Rule', action: () => insertHorizontalRule() },
    { icon: 'H1', title: 'Heading 1 (Cmd+1)', action: () => toggleHeading(1) },
    { icon: 'H2', title: 'Heading 2 (Cmd+2)', action: () => toggleHeading(2) },
    { icon: 'H3', title: 'Heading 3 (Cmd+3)', action: () => toggleHeading(3) },
    { icon: '"', title: 'Blockquote (Cmd+Shift+.)', action: () => toggleBlockquote() },
    { icon: '[]', title: 'Link (Cmd+K)', action: () => insertLink() },
    { icon: 'Img', title: 'Image (Cmd+Shift+K)', action: () => insertImage() },
  ];

  for (const btn of buttons) {
    const el = document.createElement('button');
    el.className = 'md-toolbar-btn';
    el.textContent = btn.icon;
    el.title = btn.title;
    el.addEventListener('click', (e) => {
      e.preventDefault();
      btn.action();
      getEditor()?.focus();
    });
    toolbar.appendChild(el);
  }
}

export function showToolbarIfMarkdown(): void {
  const tab = getActiveTab();
  const toolbar = document.getElementById('md-toolbar');
  if (toolbar) {
    toolbar.classList.toggle('hidden', tab?.language !== 'markdown');
  }
}
