import { getEditor } from '../editor/editor-manager';

export function triggerFind(): void {
  const editor = getEditor();
  if (!editor) return;
  editor.getAction('actions.find')?.run();
}

export function triggerReplace(): void {
  const editor = getEditor();
  if (!editor) return;
  editor.getAction('editor.action.startFindReplaceAction')?.run();
}

export function triggerFindWithSelection(): void {
  const editor = getEditor();
  if (!editor) return;
  const selection = editor.getSelection();
  if (selection && !selection.isEmpty()) {
    const text = editor.getModel()?.getValueInRange(selection) ?? '';
    editor.getAction('actions.find')?.run();
    // Set the search term after the widget opens
    setTimeout(() => {
      const findInput = document.querySelector<HTMLInputElement>(
        '.monaco-editor .find-widget .input'
      );
      if (findInput) {
        findInput.value = text;
        findInput.dispatchEvent(new Event('input'));
      }
    }, 50);
  } else {
    editor.getAction('actions.find')?.run();
  }
}
