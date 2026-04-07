import './styles/themes.css';
import './styles/main.css';
import './styles/markdown.css';
import { initEditor, setEditorTheme, updateEditorOptions, setEditorModel, getEditor } from './editor/editor-manager';
import { renderTabBar } from './tabs/tab-bar';
import { onTabsChange, addTab, getActiveTab, setTabLanguage } from './tabs/tab-store';
import { settingsStore } from './settings/settings-store';
import { openSettings } from './settings/settings-panel';
import { newFile, openFile, saveFile, saveFileAs, closeTab, closeAllFiles } from './file/file-ops';
import { triggerFind, triggerReplace } from './search/search-bar';
import { availableLanguages } from './editor/languages';
import { initPreview, togglePreview, showPreviewIfMarkdown, isPreviewVisible, getPreviewHTMLForExport } from './markdown/preview';
import { registerFormattingActions, renderFormattingToolbar, showToolbarIfMarkdown } from './markdown/formatting';
import { registerListActions } from './markdown/lists';
import { registerTableActions } from './markdown/tables';
import { initOutline, toggleOutline, showOutlineIfMarkdown, isOutlineVisible, getBreadcrumb } from './markdown/outline';
import { exportToHTML, exportToPDF } from './markdown/export';
import { getWordCount, getReadingTime } from './markdown/stats';
import { scheduleLint, clearLint } from './markdown/lint';
import { registerContentAssist } from './markdown/content-assist';
import { restoreSession, startSessionAutoSave } from './file/session-recovery';
import { restoreWindowPosition, startWindowPositionTracking } from './file/window-state';

// Print current file
function printCurrentFile(): void {
  const tab = getActiveTab();
  if (!tab) return;

  let printContent: string;

  if (tab.language === 'markdown') {
    printContent = getPreviewHTMLForExport();
  } else {
    const content = tab.model.getValue()
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
    printContent = `<!DOCTYPE html><html><head><style>
      body { font-family: 'SF Mono', Menlo, monospace; font-size: 12px; line-height: 1.5; padding: 24px; white-space: pre-wrap; word-wrap: break-word; }
    </style></head><body><pre>${content}</pre></body></html>`;
  }

  // Temporarily replace main document body for printing, then restore
  const appEl = document.getElementById('app')!;
  const settingsEl = document.getElementById('settings-overlay')!;
  const originalDisplay = appEl.style.display;
  const originalSettingsDisplay = settingsEl.style.display;

  // Create print container
  const printContainer = document.createElement('div');
  printContainer.id = 'print-container';
  printContainer.innerHTML = printContent;
  printContainer.style.cssText = 'position:fixed;top:0;left:0;right:0;bottom:0;z-index:9999;background:#fff;overflow:auto;';

  // Add print-only styles
  const printStyle = document.createElement('style');
  printStyle.id = 'print-style';
  printStyle.textContent = `
    @media print {
      #app, #settings-overlay { display: none !important; }
      #print-container { position: static !important; z-index: auto !important; }
    }
    @media screen {
      #print-container { display: none !important; }
    }
  `;

  document.head.appendChild(printStyle);
  document.body.appendChild(printContainer);

  window.print();

  // Cleanup after print dialog closes
  setTimeout(() => {
    printContainer.remove();
    printStyle.remove();
  }, 500);
}

// Apply initial theme
const initialSettings = settingsStore.get();
document.documentElement.setAttribute('data-theme', initialSettings.theme);

// Initialize Monaco editor
const editorContainer = document.getElementById('editor-container')!;
const editor = initEditor(editorContainer);

// Initialize Markdown modules
initPreview();
initOutline();
registerFormattingActions();
registerListActions();
registerTableActions();
registerContentAssist();
renderFormattingToolbar();

// Restore previous session or create an initial tab
const restored = restoreSession();
if (!restored) {
  const initialTab = addTab();
  setEditorModel(initialTab.model);
}
editor.focus();

// Start auto-saving session state
startSessionAutoSave();

// Restore window position and start tracking
restoreWindowPosition();
startWindowPositionTracking();

// Re-render tabs on change
onTabsChange(() => {
  renderTabBar();
  updateMarkdownUI();
  updateStatusBar();
});

// Initial render
renderTabBar();

// Settings change handler
settingsStore.onChange((settings) => {
  document.documentElement.setAttribute('data-theme', settings.theme);
  setEditorTheme(settings.theme);
  updateEditorOptions({
    fontSize: settings.fontSize,
    wordWrap: settings.wordWrap as 'off' | 'on' | 'wordWrapColumn' | 'bounded',
    wordWrapColumn: settings.wordWrapColumn,
  });
});

// Markdown UI visibility — show/hide toolbar, preview, outline on tab switch
function updateMarkdownUI(): void {
  showToolbarIfMarkdown();
  showPreviewIfMarkdown();
  showOutlineIfMarkdown();

  const tab = getActiveTab();
  if (tab?.language === 'markdown') {
    scheduleLint();
  } else {
    clearLint();
  }
}

// Lint on content change
editor.onDidChangeModelContent(() => {
  const tab = getActiveTab();
  if (tab?.language === 'markdown') {
    scheduleLint();
  }
});

// Status bar
function updateStatusBar(): void {
  const statusBar = document.getElementById('status-bar')!;
  const tab = getActiveTab();

  if (!tab) {
    statusBar.innerHTML = '<span class="status-item">No file open</span>';
    return;
  }

  const pos = editor.getPosition();
  const line = pos?.lineNumber ?? 1;
  const col = pos?.column ?? 1;
  const isMd = tab.language === 'markdown';

  let mdParts = '';
  if (isMd) {
    const words = getWordCount();
    const readTime = getReadingTime();
    const breadcrumb = getBreadcrumb();

    mdParts += `<span class="status-item status-words">${words} words, ${readTime}</span>`;
    if (breadcrumb) {
      mdParts += `<span class="status-item status-breadcrumb" title="${breadcrumb}">${breadcrumb}</span>`;
    }
    mdParts += `<span class="status-item status-preview-btn" id="status-preview-toggle">${isPreviewVisible() ? 'Hide Preview' : 'Show Preview'}</span>`;
    mdParts += `<span class="status-item status-preview-btn" id="status-outline-toggle">${isOutlineVisible() ? 'Hide Outline' : 'Show Outline'}</span>`;
  }

  statusBar.innerHTML = `
    <span class="status-item">Ln ${line}, Col ${col}</span>
    <span class="status-item">UTF-8</span>
    ${mdParts}
    <div class="status-right">
      <span class="status-item language-picker" id="lang-picker">${tab.language}</span>
    </div>
  `;

  // Event listeners
  document.getElementById('lang-picker')?.addEventListener('click', () => {
    toggleLanguageDropdown();
  });

  document.getElementById('status-preview-toggle')?.addEventListener('click', () => {
    togglePreview();
    updateStatusBar();
  });

  document.getElementById('status-outline-toggle')?.addEventListener('click', () => {
    toggleOutline();
    updateStatusBar();
  });
}

editor.onDidChangeCursorPosition(() => {
  updateStatusBar();
});

updateStatusBar();

// Language dropdown
let langDropdownVisible = false;

function toggleLanguageDropdown(): void {
  let dropdown = document.querySelector('.lang-dropdown');
  if (langDropdownVisible && dropdown) {
    dropdown.remove();
    langDropdownVisible = false;
    return;
  }

  const tab = getActiveTab();
  if (!tab) return;

  dropdown = document.createElement('div');
  dropdown.className = 'lang-dropdown';

  for (const lang of availableLanguages) {
    const item = document.createElement('div');
    item.className = `lang-item${tab.language === lang ? ' active' : ''}`;
    item.textContent = lang;
    item.addEventListener('click', () => {
      setTabLanguage(tab.id, lang);
      dropdown!.remove();
      langDropdownVisible = false;
      updateMarkdownUI();
      updateStatusBar();
    });
    dropdown.appendChild(item);
  }

  document.body.appendChild(dropdown);
  langDropdownVisible = true;

  const closeDropdown = (e: MouseEvent) => {
    if (!dropdown!.contains(e.target as Node)) {
      dropdown!.remove();
      langDropdownVisible = false;
      document.removeEventListener('click', closeDropdown);
    }
  };
  setTimeout(() => document.addEventListener('click', closeDropdown), 0);
}

// Menu actions from Tauri native menu
(window as any).__menuAction = (action: string) => {
  switch (action) {
    case 'new_file':
    case 'new_tab':
      newFile();
      break;
    case 'open_file':
      openFile();
      break;
    case 'save':
      saveFile();
      break;
    case 'save_as':
      saveFileAs();
      break;
    case 'close_tab':
      closeTab();
      break;
    case 'close_all':
      closeAllFiles();
      break;
    case 'print':
      printCurrentFile();
      break;
    case 'settings':
      openSettings();
      break;
    case 'find':
      triggerFind();
      break;
    case 'replace':
      triggerReplace();
      break;
    case 'toggle_preview':
      togglePreview();
      updateStatusBar();
      break;
    case 'toggle_outline':
      toggleOutline();
      updateStatusBar();
      break;
    case 'insert_table':
      editor.getAction('md.insert-table')?.run();
      break;
    case 'export_html':
      exportToHTML();
      break;
    case 'export_pdf':
      exportToPDF();
      break;
  }
};

// Window title update
onTabsChange(() => {
  const tab = getActiveTab();
  const title = tab
    ? `${tab.title}${tab.isDirty ? ' - Modified' : ''} - Neo Edit v${__APP_VERSION__}`
    : `Neo Edit v${__APP_VERSION__}`;
  document.title = title;
});
