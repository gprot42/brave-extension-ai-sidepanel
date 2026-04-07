/// <reference types="vite/client" />

declare const __APP_VERSION__: string;

interface Window {
  MonacoEnvironment?: {
    getWorker(_: unknown, label: string): Worker;
  };
}
