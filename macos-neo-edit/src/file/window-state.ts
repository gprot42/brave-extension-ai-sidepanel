import { getCurrentWindow } from '@tauri-apps/api/window';
import { LogicalPosition, LogicalSize } from '@tauri-apps/api/dpi';
import { settingsStore } from '../settings/settings-store';

const STORAGE_KEY = 'neo-edit-window-position';

interface WindowState {
  x: number;
  y: number;
  width: number;
  height: number;
  isMaximized: boolean;
}

function saveWindowState(state: WindowState): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch {
    // ignore
  }
}

function loadWindowState(): WindowState | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    // ignore
  }
  return null;
}

export async function restoreWindowPosition(): Promise<void> {
  if (!settingsStore.get().restoreWindowPosition) return;

  const state = loadWindowState();
  if (!state) return;

  const win = getCurrentWindow();

  try {
    if (state.isMaximized) {
      await win.maximize();
    } else {
      await win.setPosition(new LogicalPosition(state.x, state.y));
      await win.setSize(new LogicalSize(state.width, state.height));
    }
  } catch {
    // ignore — position may be offscreen on a different monitor setup
  }
}

export async function startWindowPositionTracking(): Promise<void> {
  const win = getCurrentWindow();

  async function captureState(): Promise<void> {
    if (!settingsStore.get().restoreWindowPosition) return;

    try {
      const isMaximized = await win.isMaximized();
      const pos = await win.outerPosition();
      const size = await win.outerSize();

      saveWindowState({
        x: pos.x,
        y: pos.y,
        width: size.width,
        height: size.height,
        isMaximized,
      });
    } catch {
      // ignore
    }
  }

  // Save on move and resize
  await win.onMoved(() => captureState());
  await win.onResized(() => captureState());

  // Save before close
  await win.onCloseRequested(async () => {
    await captureState();
  });

  // Save periodically as safety net
  setInterval(captureState, 5000);
}
