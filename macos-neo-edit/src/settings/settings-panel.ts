import { settingsStore, type Settings } from './settings-store';

let isOpen = false;

export function openSettings(): void {
  if (isOpen) return;
  isOpen = true;

  const overlay = document.getElementById('settings-overlay')!;
  overlay.classList.remove('hidden');
  overlay.innerHTML = '';

  const settings = settingsStore.get();

  const panel = document.createElement('div');
  panel.className = 'settings-panel';

  panel.innerHTML = `
    <h2>Settings</h2>

    <div class="settings-section">
      <label>Theme</label>
      <select id="setting-theme">
        <option value="light" ${settings.theme === 'light' ? 'selected' : ''}>Light</option>
        <option value="tokyo-night" ${settings.theme === 'tokyo-night' ? 'selected' : ''}>Tokyo Night</option>
        <option value="dark" ${settings.theme === 'dark' ? 'selected' : ''}>Dark</option>
      </select>
    </div>

    <div class="settings-section">
      <label>Font Size</label>
      <input type="number" id="setting-font-size" min="8" max="48" value="${settings.fontSize}" />
    </div>

    <div class="settings-section">
      <label>Word Wrap Column</label>
      <div class="wrap-options">
        <button class="wrap-btn ${settings.wordWrapColumn === 70 ? 'active' : ''}" data-col="70">70</button>
        <button class="wrap-btn ${settings.wordWrapColumn === 75 ? 'active' : ''}" data-col="75">75</button>
        <button class="wrap-btn ${settings.wordWrapColumn === 80 ? 'active' : ''}" data-col="80">80</button>
        <button class="wrap-btn ${![70, 75, 80].includes(settings.wordWrapColumn) ? 'active' : ''}" data-col="custom">Custom</button>
        <input type="number" class="custom-wrap-input" id="setting-custom-wrap" min="20" max="200" value="${settings.wordWrapColumn}" style="display: ${![70, 75, 80].includes(settings.wordWrapColumn) ? 'block' : 'none'}" />
      </div>
    </div>

    <div class="settings-section">
      <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
        <input type="checkbox" id="setting-restore-window" ${settings.restoreWindowPosition ? 'checked' : ''} style="width: auto; margin: 0;" />
        Restore window position on startup
      </label>
    </div>
  `;

  overlay.appendChild(panel);

  // Theme
  panel.querySelector('#setting-theme')!.addEventListener('change', (e) => {
    const value = (e.target as HTMLSelectElement).value as Settings['theme'];
    settingsStore.update({ theme: value });
  });

  // Font size
  panel.querySelector('#setting-font-size')!.addEventListener('input', (e) => {
    const value = parseInt((e.target as HTMLInputElement).value, 10);
    if (value >= 8 && value <= 48) {
      settingsStore.update({ fontSize: value });
    }
  });

  // Wrap column buttons
  const wrapBtns = panel.querySelectorAll('.wrap-btn');
  const customInput = panel.querySelector('#setting-custom-wrap') as HTMLInputElement;

  wrapBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      wrapBtns.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      const col = btn.getAttribute('data-col')!;
      if (col === 'custom') {
        customInput.style.display = 'block';
        customInput.focus();
      } else {
        customInput.style.display = 'none';
        settingsStore.update({ wordWrapColumn: parseInt(col, 10), wordWrap: 'wordWrapColumn' });
      }
    });
  });

  customInput.addEventListener('input', () => {
    const val = parseInt(customInput.value, 10);
    if (val >= 20 && val <= 200) {
      settingsStore.update({ wordWrapColumn: val, wordWrap: 'wordWrapColumn' });
    }
  });

  // Restore window position
  panel.querySelector('#setting-restore-window')!.addEventListener('change', (e) => {
    settingsStore.update({ restoreWindowPosition: (e.target as HTMLInputElement).checked });
  });

  // Close on overlay click
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      closeSettings();
    }
  });

  // Close on Escape
  const escHandler = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      closeSettings();
      document.removeEventListener('keydown', escHandler);
    }
  };
  document.addEventListener('keydown', escHandler);
}

export function closeSettings(): void {
  isOpen = false;
  const overlay = document.getElementById('settings-overlay')!;
  overlay.classList.add('hidden');
  overlay.innerHTML = '';
}

export function isSettingsOpen(): boolean {
  return isOpen;
}
