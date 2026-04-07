import * as monaco from 'monaco-editor';
import { getEditor } from '../editor/editor-manager';
import { getActiveTab } from '../tabs/tab-store';

function isMarkdown(): boolean {
  return getActiveTab()?.language === 'markdown';
}

function isInsideTable(model: monaco.editor.ITextModel, lineNumber: number): boolean {
  const line = model.getLineContent(lineNumber).trim();
  return line.startsWith('|') && line.endsWith('|');
}

export function registerTableActions(): void {
  const editor = getEditor();
  if (!editor) return;

  // Insert table dialog
  editor.addAction({
    id: 'md.insert-table',
    label: 'Markdown: Insert Table',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyT],
    precondition: undefined,
    run: (ed) => {
      if (!isMarkdown()) return;
      showTableDialog(ed as monaco.editor.IStandaloneCodeEditor);
    },
  });

  // Align table
  editor.addAction({
    id: 'md.align-table',
    label: 'Markdown: Align Table',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Alt | monaco.KeyCode.KeyT],
    precondition: undefined,
    run: (ed) => {
      if (!isMarkdown()) return;
      alignTableAtCursor(ed as monaco.editor.IStandaloneCodeEditor);
    },
  });
}

function showTableDialog(editor: monaco.editor.IStandaloneCodeEditor): void {
  // Remove any existing dialog
  const existing = document.getElementById('md-table-dialog');
  if (existing) existing.remove();

  const overlay = document.createElement('div');
  overlay.id = 'md-table-dialog';
  overlay.className = 'md-table-overlay';

  overlay.innerHTML = `
    <div class="md-table-panel">
      <h3>Insert Table</h3>
      <div class="md-table-fields">
        <label>Columns <input type="number" id="md-table-cols" min="1" max="20" value="3" /></label>
        <label>Rows <input type="number" id="md-table-rows" min="1" max="50" value="3" /></label>
      </div>
      <div class="md-table-actions">
        <button id="md-table-cancel">Cancel</button>
        <button id="md-table-insert">Insert</button>
      </div>
    </div>
  `;

  document.body.appendChild(overlay);

  const colsInput = document.getElementById('md-table-cols') as HTMLInputElement;
  const rowsInput = document.getElementById('md-table-rows') as HTMLInputElement;

  colsInput.focus();
  colsInput.select();

  document.getElementById('md-table-cancel')!.addEventListener('click', () => {
    overlay.remove();
    editor.focus();
  });

  document.getElementById('md-table-insert')!.addEventListener('click', () => {
    const cols = Math.max(1, Math.min(20, parseInt(colsInput.value, 10) || 3));
    const rows = Math.max(1, Math.min(50, parseInt(rowsInput.value, 10) || 3));
    insertTable(editor, cols, rows);
    overlay.remove();
    editor.focus();
  });

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      overlay.remove();
      editor.focus();
    }
  });

  const handleKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      overlay.remove();
      editor.focus();
      document.removeEventListener('keydown', handleKey);
    }
    if (e.key === 'Enter') {
      const cols = Math.max(1, Math.min(20, parseInt(colsInput.value, 10) || 3));
      const rows = Math.max(1, Math.min(50, parseInt(rowsInput.value, 10) || 3));
      insertTable(editor, cols, rows);
      overlay.remove();
      editor.focus();
      document.removeEventListener('keydown', handleKey);
    }
  };
  document.addEventListener('keydown', handleKey);
}

function insertTable(editor: monaco.editor.IStandaloneCodeEditor, cols: number, rows: number): void {
  const cell = ' Header ';
  const sep = '--------';
  const dataCell = '        ';

  const headerRow = '|' + Array(cols).fill(cell).join('|') + '|';
  const sepRow = '|' + Array(cols).fill(sep).join('|') + '|';
  const dataRow = '|' + Array(cols).fill(dataCell).join('|') + '|';

  const lines = [headerRow, sepRow];
  for (let i = 0; i < rows; i++) {
    lines.push(dataRow);
  }

  const pos = editor.getPosition();
  if (!pos) return;

  const text = '\n' + lines.join('\n') + '\n';
  const model = editor.getModel();
  if (!model) return;

  const lineContent = model.getLineContent(pos.lineNumber);
  const range = new monaco.Range(pos.lineNumber, lineContent.length + 1, pos.lineNumber, lineContent.length + 1);
  editor.executeEdits('md-table', [{ range, text }]);
}

function alignTableAtCursor(editor: monaco.editor.IStandaloneCodeEditor): void {
  const model = editor.getModel();
  const pos = editor.getPosition();
  if (!model || !pos) return;

  // Find table boundaries
  let startLine = pos.lineNumber;
  let endLine = pos.lineNumber;

  while (startLine > 1 && isInsideTable(model, startLine - 1)) startLine--;
  while (endLine < model.getLineCount() && isInsideTable(model, endLine + 1)) endLine++;

  if (startLine === endLine && !isInsideTable(model, startLine)) return;

  // Parse all rows
  const rows: string[][] = [];
  for (let i = startLine; i <= endLine; i++) {
    const line = model.getLineContent(i).trim();
    const cells = line.split('|').slice(1, -1).map((c) => c.trim());
    rows.push(cells);
  }

  if (rows.length === 0) return;

  // Find max width per column
  const colCount = Math.max(...rows.map((r) => r.length));
  const widths: number[] = Array(colCount).fill(3);

  for (const row of rows) {
    for (let c = 0; c < row.length; c++) {
      const isSep = /^[-:]+$/.test(row[c]);
      if (!isSep) {
        widths[c] = Math.max(widths[c], row[c].length);
      }
    }
  }

  // Rebuild aligned table
  const aligned: string[] = [];
  for (let r = 0; r < rows.length; r++) {
    const cells = rows[r];
    const parts: string[] = [];
    for (let c = 0; c < colCount; c++) {
      const cell = cells[c] ?? '';
      const isSepRow = r > 0 && /^[-:]+$/.test(cell);
      if (isSepRow) {
        parts.push('-'.repeat(widths[c]));
      } else {
        parts.push(cell.padEnd(widths[c]));
      }
    }
    aligned.push('| ' + parts.join(' | ') + ' |');
  }

  const range = new monaco.Range(startLine, 1, endLine, model.getLineContent(endLine).length + 1);
  editor.executeEdits('md-table', [{ range, text: aligned.join('\n') }]);
}
