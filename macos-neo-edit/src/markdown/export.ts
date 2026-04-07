import { save } from '@tauri-apps/plugin-dialog';
import { writeTextFile } from '@tauri-apps/plugin-fs';
import { getPreviewHTMLForExport } from './preview';
import { getActiveTab } from '../tabs/tab-store';

export async function exportToHTML(): Promise<void> {
  const tab = getActiveTab();
  if (!tab || tab.language !== 'markdown') return;

  const html = getPreviewHTMLForExport();
  if (!html) return;

  const defaultName = tab.title.replace(/\.md$/i, '.html');
  const filePath = await save({
    defaultPath: defaultName,
    filters: [{ name: 'HTML Files', extensions: ['html'] }],
  });

  if (!filePath) return;

  try {
    await writeTextFile(filePath, html);
  } catch (err) {
    console.error('Failed to export HTML:', err);
  }
}

export function exportToPDF(): void {
  const tab = getActiveTab();
  if (!tab || tab.language !== 'markdown') return;

  const html = getPreviewHTMLForExport();
  if (!html) return;

  // Create a hidden iframe, write the content, then print it
  const iframe = document.createElement('iframe');
  iframe.style.position = 'fixed';
  iframe.style.left = '-9999px';
  iframe.style.width = '800px';
  iframe.style.height = '600px';
  document.body.appendChild(iframe);

  const doc = iframe.contentDocument;
  if (doc) {
    doc.open();
    doc.write(html);
    doc.close();

    // Wait for content to render before printing
    setTimeout(() => {
      iframe.contentWindow?.print();
      // Clean up after print dialog closes
      setTimeout(() => {
        document.body.removeChild(iframe);
      }, 1000);
    }, 250);
  }
}
