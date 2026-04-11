import * as monaco from 'monaco-editor';
import TurndownService from 'turndown';

let td: TurndownService | null = null;

function getTurndown(): TurndownService {
  if (td) return td;
  td = new TurndownService({
    headingStyle: 'atx',
    codeBlockStyle: 'fenced',
    bulletListMarker: '-',
    hr: '---',
    strongDelimiter: '**',
    emDelimiter: '*',
  });

  // Preserve fenced code blocks from <pre><code>
  td.addRule('fencedCodeBlock', {
    filter(node) {
      return (
        node.nodeName === 'PRE' &&
        node.firstChild !== null &&
        node.firstChild.nodeName === 'CODE'
      );
    },
    replacement(_content, node) {
      const codeEl = (node as HTMLElement).querySelector('code');
      const lang = (codeEl?.className ?? '').replace(/language-/, '').trim();
      const code = codeEl?.textContent ?? '';
      return `\n\`\`\`${lang}\n${code}\n\`\`\`\n`;
    },
  });

  // Strikethrough
  td.addRule('strikethrough', {
    filter: ['del', 's'],
    replacement: (content) => `~~${content}~~`,
  });

  return td;
}

/** Convert HTML string to Markdown, cleaning up excess blank lines. */
function htmlToMarkdown(html: string): string {
  const md = getTurndown().turndown(html);
  // Collapse 3+ consecutive blank lines to 2
  return md.replace(/\n{3,}/g, '\n\n').trim();
}

/** Read the HTML flavour from the clipboard (falls back to plain text). */
async function readClipboardAsMarkdown(): Promise<string | null> {
  try {
    // Prefer the Clipboard API (async, works in Tauri WebView)
    if (navigator.clipboard && navigator.clipboard.read) {
      const items = await navigator.clipboard.read();
      for (const item of items) {
        if (item.types.includes('text/html')) {
          const blob = await item.getType('text/html');
          const html = await blob.text();
          return htmlToMarkdown(html);
        }
        if (item.types.includes('text/plain')) {
          const blob = await item.getType('text/plain');
          return blob.text();
        }
      }
    }
  } catch {
    // Clipboard API blocked — fall back to plain text read via execCommand (see caller)
  }
  return null;
}

let disposable: monaco.IDisposable | null = null;

export function registerPasteWithFormatting(editor: monaco.editor.IStandaloneCodeEditor): void {
  disposable?.dispose();

  // Cmd+Shift+V — Paste with Formatting
  disposable = editor.addAction({
    id: 'neo-paste-with-formatting',
    label: 'Paste with Formatting',
    keybindings: [
      monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyV,
    ],
    contextMenuGroupId: '9_cutcopypaste',
    contextMenuOrder: 3,
    run: async () => {
      const markdown = await readClipboardAsMarkdown();
      if (!markdown) return;

      const model = editor.getModel();
      if (!model) return;
      const selection = editor.getSelection() ?? new monaco.Selection(1, 1, 1, 1);

      editor.executeEdits('paste-with-formatting', [{
        range: selection,
        text: markdown,
        forceMoveMarkers: true,
      }]);

      // Move cursor to end of inserted text
      const lines = markdown.split('\n');
      const endLine = selection.startLineNumber + lines.length - 1;
      const endCol = lines.length === 1
        ? selection.startColumn + markdown.length
        : lines[lines.length - 1].length + 1;
      editor.setPosition({ lineNumber: endLine, column: endCol });
      editor.focus();
    },
  });
}

export function disposePasteWithFormatting(): void {
  disposable?.dispose();
  disposable = null;
}
