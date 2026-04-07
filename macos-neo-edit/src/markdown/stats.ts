import { getActiveTab } from '../tabs/tab-store';

function stripMarkdown(text: string): string {
  return text
    // Remove fenced code blocks
    .replace(/```[\s\S]*?```/g, '')
    // Remove inline code
    .replace(/`[^`]+`/g, '')
    // Remove images
    .replace(/!\[.*?\]\(.*?\)/g, '')
    // Remove links, keep text
    .replace(/\[([^\]]*)\]\(.*?\)/g, '$1')
    // Remove headings markers
    .replace(/^#{1,6}\s/gm, '')
    // Remove bold/italic markers
    .replace(/[*_]{1,3}/g, '')
    // Remove strikethrough
    .replace(/~~(.*?)~~/g, '$1')
    // Remove blockquote markers
    .replace(/^>\s/gm, '')
    // Remove horizontal rules
    .replace(/^[-*_]{3,}\s*$/gm, '')
    // Remove HTML tags
    .replace(/<[^>]+>/g, '')
    // Collapse whitespace
    .replace(/\s+/g, ' ')
    .trim();
}

export function getWordCount(): number {
  const tab = getActiveTab();
  if (!tab || tab.language !== 'markdown') return 0;

  const plain = stripMarkdown(tab.model.getValue());
  if (!plain) return 0;

  return plain.split(/\s+/).filter((w) => w.length > 0).length;
}

export function getReadingTime(): string {
  const words = getWordCount();
  if (words === 0) return '0 min';
  const minutes = Math.ceil(words / 200);
  return `${minutes} min read`;
}

export function getCharCount(): number {
  const tab = getActiveTab();
  if (!tab) return 0;
  return tab.model.getValue().length;
}
