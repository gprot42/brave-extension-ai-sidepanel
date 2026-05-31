# AI Panel — Gemini Side Panel for Google Docs

A Manifest V3 browser extension (Brave / Chrome) that adds an AI side panel to
Google Docs. It reads the active document's text **and comments**, then lets you
ask a Gemini model questions with the full document as context.

## Features

- **Side panel UI** that opens from the toolbar icon (click to toggle open/close).
- **Document context extraction** — pulls the document body and comments,
  including a fallback to the Google Docs `?format=txt` export endpoint for
  canvas-rendered documents.
- **Model selector** with multiple Gemini models:
  - Gemini 3.1 Flash Lite (default)
  - Gemini 3.1 Pro
  - Gemini 3 Flash
  - Gemini 3.5 Flash
- **Streaming responses** in a chat-style interface.
- **Theme support** — system / light / dark (Tokyo Night).
- **Optional extraction diagnostics** (off by default) for troubleshooting.
- **API key stored locally** in `chrome.storage` — never committed or sent
  anywhere except the Gemini API.

## Permissions

| Permission | Why |
|------------|-----|
| `sidePanel` | Render the panel |
| `storage` | Persist the API key and settings |
| `activeTab` / `scripting` | Read the active Google Doc |
| `host_permissions: docs.google.com, drive.google.com` | Access document content |

## Project layout

This repository contains the **source** for the extension. The packaged
extension is produced into `build/` (which is gitignored).

```
manifest.json     Plasmo manifest overrides (permissions, hosts)
package.json      Build scripts and the extension displayName
background.ts     Service worker — opens the side panel on icon click
content.ts        Content script for document/comment extraction
sidepanel.tsx     Side panel UI (React)
sidepanel.html    Side panel host page
utils/gemini.ts   Gemini model map, prompt building, token estimation
```

## Build

Requires Node.js and a package manager (npm/pnpm).

```bash
npm install
npm run build      # outputs build/chrome-mv3-prod
```

Useful scripts:

```bash
npm run dev        # Plasmo dev build with hot reload
npm run typecheck  # tsc --noEmit
npm run lint       # eslint
```

## Load in Brave / Chrome

1. Build the extension (`npm run build`).
2. Open `brave://extensions/` (or `chrome://extensions/`).
3. Enable **Developer mode**.
4. Click **Load unpacked** and select `build/chrome-mv3-prod`.
5. Open a Google Doc and click the extension's toolbar icon to open the panel.

## Configuration

Open the panel's settings (gear icon) and paste a Gemini API key from
[Google AI Studio](https://aistudio.google.com/). The key is stored only in
`chrome.storage` on your machine.

## Privacy

- Document text and comments are sent **only** to the Gemini API when you submit
  a prompt.
- The API key never leaves your browser except as the Gemini API request header.
- No secrets are stored in this repository; `.env*`, `secrets.*`, `keys.*`, and
  the `build/` output are all gitignored.
