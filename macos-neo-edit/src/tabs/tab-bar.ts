import {
  getTabs,
  getActiveId,
  setActive,
  removeTab,
  addTab,
} from './tab-store';
import { setEditorModel, getEditor } from '../editor/editor-manager';
import { openSettings } from '../settings/settings-panel';

export function renderTabBar(): void {
  const container = document.getElementById('tab-bar')!;
  container.innerHTML = '';

  const tabs = getTabs();
  const activeId = getActiveId();

  for (const tab of tabs) {
    const el = document.createElement('div');
    el.className = `tab${tab.id === activeId ? ' active' : ''}${tab.isDirty ? ' dirty' : ''}`;
    el.dataset.id = tab.id;

    const titleSpan = document.createElement('span');
    titleSpan.textContent = tab.title;

    const dirtyDot = document.createElement('span');
    dirtyDot.className = 'dirty-dot';

    const closeBtn = document.createElement('span');
    closeBtn.className = 'close-btn';
    closeBtn.textContent = '\u00d7';
    closeBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      removeTab(tab.id);
      const active = getTabs().length > 0 ? getTabs().find((t) => t.id === getActiveId()) : null;
      setEditorModel(active?.model ?? null);
    });

    el.appendChild(dirtyDot);
    el.appendChild(titleSpan);
    el.appendChild(closeBtn);

    el.addEventListener('click', () => {
      setActive(tab.id);
      const t = getTabs().find((t) => t.id === tab.id);
      if (t) setEditorModel(t.model);
    });

    el.addEventListener('auxclick', (e) => {
      if (e.button === 1) {
        removeTab(tab.id);
        const active = getTabs().length > 0 ? getTabs().find((t) => t.id === getActiveId()) : null;
        setEditorModel(active?.model ?? null);
      }
    });

    container.appendChild(el);
  }

  // New tab button
  const newBtn = document.createElement('div');
  newBtn.className = 'tab-new-btn';
  newBtn.textContent = '+';
  newBtn.title = 'New Tab';
  newBtn.addEventListener('click', () => {
    const tab = addTab();
    setEditorModel(tab.model);
    getEditor()?.focus();
  });
  container.appendChild(newBtn);

  // Settings button
  const settingsBtn = document.createElement('div');
  settingsBtn.className = 'tab-settings-btn';
  settingsBtn.innerHTML = '&#9881;';
  settingsBtn.title = 'Settings';
  settingsBtn.addEventListener('click', () => {
    openSettings();
  });
  container.appendChild(settingsBtn);
}
