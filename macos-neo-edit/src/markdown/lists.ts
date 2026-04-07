import * as monaco from 'monaco-editor';
import { getEditor } from '../editor/editor-manager';
import { getActiveTab } from '../tabs/tab-store';

function isMarkdown(): boolean {
  return getActiveTab()?.language === 'markdown';
}

const bulletPattern = /^(\s*)([-*+])\s(.*)$/;
const numberedPattern = /^(\s*)(\d+)\.\s(.*)$/;
const checkboxPattern = /^(\s*)- \[([ xX])\]\s(.*)$/;

export function registerListActions(): void {
  const editor = getEditor();
  if (!editor) return;

  // Auto-continue lists on Enter
  editor.addAction({
    id: 'md.list-continue',
    label: 'Markdown: Continue List',
    keybindings: [monaco.KeyCode.Enter],
    precondition: undefined,
    run: (ed) => {
      if (!isMarkdown()) {
        // Fall through to default Enter behavior
        ed.trigger('keyboard', 'type', { text: '\n' });
        return;
      }

      const model = ed.getModel();
      const pos = ed.getPosition();
      if (!model || !pos) {
        ed.trigger('keyboard', 'type', { text: '\n' });
        return;
      }

      const line = model.getLineContent(pos.lineNumber);

      // Check checkbox pattern first
      const cbMatch = line.match(checkboxPattern);
      if (cbMatch) {
        const [, indent, , content] = cbMatch;
        if (!content.trim()) {
          // Empty checkbox item: remove it
          const range = new monaco.Range(pos.lineNumber, 1, pos.lineNumber, line.length + 1);
          ed.executeEdits('md-list', [{ range, text: '' }]);
          return;
        }
        ed.trigger('keyboard', 'type', { text: `\n${indent}- [ ] ` });
        return;
      }

      // Bullet lists
      const bulletMatch = line.match(bulletPattern);
      if (bulletMatch) {
        const [, indent, marker, content] = bulletMatch;
        if (!content.trim()) {
          // Empty bullet: remove it
          const range = new monaco.Range(pos.lineNumber, 1, pos.lineNumber, line.length + 1);
          ed.executeEdits('md-list', [{ range, text: '' }]);
          return;
        }
        ed.trigger('keyboard', 'type', { text: `\n${indent}${marker} ` });
        return;
      }

      // Numbered lists
      const numMatch = line.match(numberedPattern);
      if (numMatch) {
        const [, indent, num, content] = numMatch;
        if (!content.trim()) {
          const range = new monaco.Range(pos.lineNumber, 1, pos.lineNumber, line.length + 1);
          ed.executeEdits('md-list', [{ range, text: '' }]);
          return;
        }
        const next = parseInt(num, 10) + 1;
        ed.trigger('keyboard', 'type', { text: `\n${indent}${next}. ` });
        return;
      }

      // Default Enter
      ed.trigger('keyboard', 'type', { text: '\n' });
    },
  });

  // Toggle checkbox
  editor.addAction({
    id: 'md.toggle-checkbox',
    label: 'Markdown: Toggle Checkbox',
    keybindings: [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyC],
    precondition: undefined,
    run: (ed) => {
      if (!isMarkdown()) return;

      const model = ed.getModel();
      const pos = ed.getPosition();
      if (!model || !pos) return;

      const line = model.getLineContent(pos.lineNumber);
      const range = new monaco.Range(pos.lineNumber, 1, pos.lineNumber, line.length + 1);

      const cbMatch = line.match(checkboxPattern);
      if (cbMatch) {
        const [, indent, checked, content] = cbMatch;
        const newChecked = checked === ' ' ? 'x' : ' ';
        ed.executeEdits('md-list', [{ range, text: `${indent}- [${newChecked}] ${content}` }]);
      } else {
        // Convert to checkbox
        const bulletMatch = line.match(bulletPattern);
        if (bulletMatch) {
          const [, indent, , content] = bulletMatch;
          ed.executeEdits('md-list', [{ range, text: `${indent}- [ ] ${content}` }]);
        } else {
          ed.executeEdits('md-list', [{ range, text: `- [ ] ${line.trimStart()}` }]);
        }
      }
    },
  });

  // Indent list item
  editor.addAction({
    id: 'md.list-indent',
    label: 'Markdown: Indent List Item',
    keybindings: [monaco.KeyCode.Tab],
    precondition: undefined,
    run: (ed) => {
      if (!isMarkdown()) {
        ed.trigger('keyboard', 'type', { text: '\t' });
        return;
      }

      const model = ed.getModel();
      const pos = ed.getPosition();
      if (!model || !pos) {
        ed.trigger('keyboard', 'type', { text: '\t' });
        return;
      }

      const line = model.getLineContent(pos.lineNumber);
      if (bulletPattern.test(line) || numberedPattern.test(line) || checkboxPattern.test(line)) {
        const range = new monaco.Range(pos.lineNumber, 1, pos.lineNumber, 1);
        ed.executeEdits('md-list', [{ range, text: '  ' }]);
      } else {
        ed.trigger('keyboard', 'type', { text: '\t' });
      }
    },
  });

  // Outdent list item
  editor.addAction({
    id: 'md.list-outdent',
    label: 'Markdown: Outdent List Item',
    keybindings: [monaco.KeyMod.Shift | monaco.KeyCode.Tab],
    precondition: undefined,
    run: (ed) => {
      if (!isMarkdown()) {
        ed.trigger('keyboard', 'outdent', {});
        return;
      }

      const model = ed.getModel();
      const pos = ed.getPosition();
      if (!model || !pos) return;

      const line = model.getLineContent(pos.lineNumber);
      if (line.startsWith('  ')) {
        const range = new monaco.Range(pos.lineNumber, 1, pos.lineNumber, 3);
        ed.executeEdits('md-list', [{ range, text: '' }]);
      }
    },
  });
}
