import type { ExtensionSettings } from '../shared/types';

const NATIVE_HOST_NAME = 'org.keepassxc.keepassxc_browser';

interface KeePassXCMessage {
  action: string;
  [key: string]: unknown;
}

interface KeePassXCResponse {
  action?: string;
  success?: string;
  error?: string;
  entries?: Array<{
    login: string;
    password: string;
    name: string;
    uuid: string;
  }>;
  [key: string]: unknown;
}

let port: chrome.runtime.Port | null = null;
let connected = false;
let messageId = 0;
const pendingResponses = new Map<string, {
  resolve: (value: KeePassXCResponse) => void;
  reject: (reason: Error) => void;
}>();

function getNextId(): string {
  return String(++messageId);
}

export function isKeePassXCConnected(): boolean {
  return connected;
}

export async function connectKeePassXC(): Promise<void> {
  if (port) {
    port.disconnect();
  }

  return new Promise((resolve, reject) => {
    try {
      port = chrome.runtime.connectNative(NATIVE_HOST_NAME);

      port.onMessage.addListener((msg: KeePassXCResponse) => {
        if (msg.action === 'database-locked') {
          connected = false;
          return;
        }

        if (msg.action === 'database-unlocked') {
          connected = true;
          return;
        }

        // Route response to pending request
        const id = msg.action ?? '';
        const pending = pendingResponses.get(id);
        if (pending) {
          pendingResponses.delete(id);
          if (msg.error) {
            pending.reject(new Error(msg.error));
          } else {
            pending.resolve(msg);
          }
        }
      });

      port.onDisconnect.addListener(() => {
        connected = false;
        port = null;
        pendingResponses.forEach(({ reject }) =>
          reject(new Error('KeePassXC disconnected'))
        );
        pendingResponses.clear();
      });

      // Send initial handshake
      sendMessage({ action: 'change-public-keys' })
        .then(() => {
          connected = true;
          resolve();
        })
        .catch(reject);
    } catch (err) {
      reject(new Error('Failed to connect to KeePassXC. Is it running?'));
    }
  });
}

export function disconnectKeePassXC(): void {
  if (port) {
    port.disconnect();
    port = null;
  }
  connected = false;
  pendingResponses.clear();
}

function sendMessage(msg: KeePassXCMessage): Promise<KeePassXCResponse> {
  return new Promise((resolve, reject) => {
    if (!port) {
      reject(new Error('Not connected to KeePassXC'));
      return;
    }

    const id = getNextId();
    const fullMsg = { ...msg, nonce: id };

    pendingResponses.set(msg.action, { resolve, reject });

    setTimeout(() => {
      if (pendingResponses.has(msg.action)) {
        pendingResponses.delete(msg.action);
        reject(new Error('KeePassXC request timed out'));
      }
    }, 10000);

    port.postMessage(fullMsg);
  });
}

export async function getLoginsForUrl(url: string): Promise<Array<{
  uuid: string;
  title: string;
  username: string;
  password: string;
  url: string;
}>> {
  if (!connected || !port) {
    throw new Error('Not connected to KeePassXC');
  }

  const response = await sendMessage({
    action: 'get-logins',
    url,
  });

  if (!response.entries) return [];

  return response.entries.map((e) => ({
    uuid: e.uuid ?? '',
    title: e.name ?? '',
    username: e.login ?? '',
    password: e.password ?? '',
    url,
  }));
}
