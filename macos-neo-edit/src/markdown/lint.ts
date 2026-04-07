import * as monaco from 'monaco-editor';
import { getActiveTab } from '../tabs/tab-store';

let debounceTimer: ReturnType<typeof setTimeout> | null = null;

function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\w\s-]/g, '')
    .replace(/\s+/g, '-')
    .trim();
}

function runLint(model: monaco.editor.ITextModel): void {
  const markers: monaco.editor.IMarkerData[] = [];
  const content = model.getValue();
  const lines = content.split('\n');

  const headings: Array<{ text: string; slug: string; line: number }> = [];
  const headingSlugs = new Set<string>();
  let currentListMarker: string | null = null;
  let listStartLine = 0;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNumber = i + 1;

    // Check headings
    const headingMatch = line.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch) {
      const text = headingMatch[2].replace(/\s*#+\s*$/, '');
      const slug = slugify(text);
      headings.push({ text, slug, line: lineNumber });

      // Check for duplicate headings
      if (headingSlugs.has(slug)) {
        markers.push({
          severity: monaco.MarkerSeverity.Warning,
          message: `Duplicate heading: "${text}"`,
          startLineNumber: lineNumber,
          startColumn: 1,
          endLineNumber: lineNumber,
          endColumn: line.length + 1,
        });
      }
      headingSlugs.add(slug);
    }

    // Check list marker consistency
    const listMatch = line.match(/^(\s*)([-*+])\s/);
    if (listMatch) {
      const marker = listMatch[2];
      if (currentListMarker === null) {
        currentListMarker = marker;
        listStartLine = lineNumber;
      } else if (marker !== currentListMarker) {
        markers.push({
          severity: monaco.MarkerSeverity.Info,
          message: `Inconsistent list marker "${marker}" (expected "${currentListMarker}" from line ${listStartLine})`,
          startLineNumber: lineNumber,
          startColumn: listMatch[1].length + 1,
          endLineNumber: lineNumber,
          endColumn: listMatch[1].length + 2,
        });
      }
    } else if (line.trim() === '') {
      // Reset list marker tracking on empty lines
      currentListMarker = null;
    }

    // Trailing spaces (only flag lines with 1 trailing space — 2 spaces is intentional line break)
    if (line.length > 0 && line.endsWith(' ') && !line.endsWith('  ')) {
      markers.push({
        severity: monaco.MarkerSeverity.Info,
        message: 'Trailing space (use 2 spaces for a line break, or remove)',
        startLineNumber: lineNumber,
        startColumn: line.length,
        endLineNumber: lineNumber,
        endColumn: line.length + 1,
      });
    }
  }

  // Check for broken internal links
  const linkPattern = /\[([^\]]*)\]\(#([^)]+)\)/g;
  let match: RegExpExecArray | null;
  const lineOffsets: number[] = [];
  let offset = 0;
  for (const l of lines) {
    lineOffsets.push(offset);
    offset += l.length + 1;
  }

  while ((match = linkPattern.exec(content)) !== null) {
    const anchor = match[2];
    const targetExists = headings.some((h) => h.slug === anchor);
    if (!targetExists) {
      // Find line number
      const pos = match.index;
      let ln = 1;
      for (let i = 0; i < lineOffsets.length; i++) {
        if (lineOffsets[i] > pos) break;
        ln = i + 1;
      }
      const col = pos - lineOffsets[ln - 1] + 1;
      markers.push({
        severity: monaco.MarkerSeverity.Error,
        message: `Broken internal link: "#${anchor}" — no matching heading found`,
        startLineNumber: ln,
        startColumn: col,
        endLineNumber: ln,
        endColumn: col + match[0].length,
      });
    }
  }

  monaco.editor.setModelMarkers(model, 'markdown-lint', markers);
}

export function scheduleLint(): void {
  if (debounceTimer) clearTimeout(debounceTimer);

  const tab = getActiveTab();
  if (!tab || tab.language !== 'markdown') return;

  debounceTimer = setTimeout(() => {
    runLint(tab.model);
  }, 500);
}

export function clearLint(): void {
  const tab = getActiveTab();
  if (tab) {
    monaco.editor.setModelMarkers(tab.model, 'markdown-lint', []);
  }
}
