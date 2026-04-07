import * as monaco from 'monaco-editor';
import { getEditor } from '../editor/editor-manager';
import { getActiveTab } from '../tabs/tab-store';

// Top ~100 emoji shortcodes
const emojiMap: Record<string, string> = {
  smile: '\u{1F604}', laugh: '\u{1F606}', wink: '\u{1F609}', blush: '\u{1F60A}',
  heart_eyes: '\u{1F60D}', kiss: '\u{1F618}', thinking: '\u{1F914}', neutral: '\u{1F610}',
  expressionless: '\u{1F611}', rolling_eyes: '\u{1F644}', grimacing: '\u{1F62C}',
  sob: '\u{1F62D}', joy: '\u{1F602}', skull: '\u{1F480}', thumbsup: '\u{1F44D}',
  thumbsdown: '\u{1F44E}', clap: '\u{1F44F}', wave: '\u{1F44B}', raised_hands: '\u{1F64C}',
  pray: '\u{1F64F}', muscle: '\u{1F4AA}', fire: '\u{1F525}', heart: '\u2764\uFE0F',
  broken_heart: '\u{1F494}', star: '\u2B50', sparkles: '\u2728', zap: '\u26A1',
  sun: '\u2600\uFE0F', moon: '\u{1F319}', cloud: '\u2601\uFE0F', rain: '\u{1F327}\uFE0F',
  snow: '\u2744\uFE0F', rainbow: '\u{1F308}', rocket: '\u{1F680}', airplane: '\u2708\uFE0F',
  tada: '\u{1F389}', balloon: '\u{1F388}', gift: '\u{1F381}', trophy: '\u{1F3C6}',
  medal: '\u{1F3C5}', crown: '\u{1F451}', gem: '\u{1F48E}', money: '\u{1F4B0}',
  bulb: '\u{1F4A1}', book: '\u{1F4D6}', memo: '\u{1F4DD}', pencil: '\u270F\uFE0F',
  pin: '\u{1F4CC}', link: '\u{1F517}', lock: '\u{1F512}', unlock: '\u{1F513}',
  key: '\u{1F511}', hammer: '\u{1F528}', wrench: '\u{1F527}', gear: '\u2699\uFE0F',
  bug: '\u{1F41B}', check: '\u2705', x: '\u274C', warning: '\u26A0\uFE0F',
  info: '\u2139\uFE0F', question: '\u2753', exclamation: '\u2757', plus: '\u2795',
  minus: '\u2796', arrow_right: '\u27A1\uFE0F', arrow_left: '\u2B05\uFE0F',
  arrow_up: '\u2B06\uFE0F', arrow_down: '\u2B07\uFE0F', eyes: '\u{1F440}',
  brain: '\u{1F9E0}', robot: '\u{1F916}', ghost: '\u{1F47B}', alien: '\u{1F47D}',
  poop: '\u{1F4A9}', cat: '\u{1F431}', dog: '\u{1F436}', unicorn: '\u{1F984}',
  pizza: '\u{1F355}', coffee: '\u2615', beer: '\u{1F37A}', wine: '\u{1F377}',
  apple: '\u{1F34E}', avocado: '\u{1F951}', earth: '\u{1F30D}', usa: '\u{1F1FA}\u{1F1F8}',
  one: '1\uFE0F\u20E3', two: '2\uFE0F\u20E3', three: '3\uFE0F\u20E3',
  hundred: '\u{1F4AF}', ok: '\u{1F44C}', peace: '\u270C\uFE0F',
  point_up: '\u261D\uFE0F', point_down: '\u{1F447}',
};

let completionDisposable: monaco.IDisposable | null = null;

export function registerContentAssist(): void {
  // Emoji completion provider
  completionDisposable?.dispose();
  completionDisposable = monaco.languages.registerCompletionItemProvider('markdown', {
    triggerCharacters: [':'],
    provideCompletionItems(model, position) {
      const textBefore = model.getValueInRange({
        startLineNumber: position.lineNumber,
        startColumn: Math.max(1, position.column - 30),
        endLineNumber: position.lineNumber,
        endColumn: position.column,
      });

      const colonMatch = textBefore.match(/:(\w*)$/);
      if (!colonMatch) return { suggestions: [] };

      const prefix = colonMatch[1].toLowerCase();
      const startCol = position.column - colonMatch[0].length;

      const range = {
        startLineNumber: position.lineNumber,
        startColumn: startCol,
        endLineNumber: position.lineNumber,
        endColumn: position.column,
      };

      const suggestions: monaco.languages.CompletionItem[] = [];
      for (const [name, emoji] of Object.entries(emojiMap)) {
        if (name.startsWith(prefix) || prefix === '') {
          suggestions.push({
            label: `:${name}: ${emoji}`,
            kind: monaco.languages.CompletionItemKind.Text,
            insertText: emoji,
            range,
            detail: `Emoji: ${emoji}`,
            sortText: name,
          });
        }
      }

      return { suggestions };
    },
  });

  // Paste URL on selection
  setupPasteUrlHandler();
}

function setupPasteUrlHandler(): void {
  document.addEventListener('paste', (e) => {
    const tab = getActiveTab();
    if (!tab || tab.language !== 'markdown') return;

    const editor = getEditor();
    if (!editor) return;

    const selection = editor.getSelection();
    if (!selection || selection.isEmpty()) return;

    const clipboardText = e.clipboardData?.getData('text/plain')?.trim();
    if (!clipboardText) return;

    // Check if pasted content is a URL
    const urlPattern = /^https?:\/\/\S+$/;
    if (!urlPattern.test(clipboardText)) return;

    e.preventDefault();

    const model = editor.getModel();
    if (!model) return;

    const selectedText = model.getValueInRange(selection);
    editor.executeEdits('md-paste-url', [{
      range: selection,
      text: `[${selectedText}](${clipboardText})`,
    }]);
  });
}

export function disposeContentAssist(): void {
  completionDisposable?.dispose();
  completionDisposable = null;
}
