# PassForge

A Brave/Chrome browser extension that reads KeePass `.kdbx` password databases directly in the browser. No desktop app required — or optionally connect to KeePassXC via native messaging.

## Features

- **Import .kdbx databases** — select your KeePass file directly from the extension popup
- **Master password + key file unlock** — supports `.key` and `.keyx` key files
- **Smart autofill** — detects login forms and fills credentials with one click
- **Domain-aware search** — automatically shows matching entries for the current site
- **Full-text search** — search across titles, usernames, URLs, and notes
- **Copy to clipboard** — one-click copy with auto-clear after a configurable timeout
- **Auto-lock** — locks the database after idle timeout or when the browser locks
- **KeePassXC mode** — optionally connect to the KeePassXC desktop app via native messaging
- **Keyboard shortcut** — `Cmd+Shift+P` (macOS) / `Ctrl+Shift+P` (Windows/Linux) to open the popup

## Prerequisites

- [Node.js](https://nodejs.org/) v18+
- [Brave](https://brave.com/) or any Chromium-based browser (Chrome, Edge, etc.)

## Installation

### Build from source

```bash
git clone https://github.com/dazdaz/macos-passforge.git
cd macos-passforge
npm install
npm run build
```

### Load the extension

1. Open `brave://extensions` (or `chrome://extensions`)
2. Enable **Developer mode** (toggle in the top-right corner)
3. Click **Load unpacked**
4. Select the `dist/` folder from this project

The PassForge icon will appear in your browser toolbar.

## Usage

### 1. Import your database

1. Click the PassForge icon in the toolbar
2. Click **"Click to select .kdbx file"** and choose your KeePass database
3. Optionally select a key file (`.key` / `.keyx`)
4. Click **Import Database**

Your encrypted database is stored locally in the browser's extension storage. It is never sent anywhere.

### 2. Unlock

1. Enter your master password
2. Click **Unlock**

The database stays unlocked in memory until the auto-lock timeout triggers (default: 5 minutes) or you lock it manually.

### 3. Browse and search entries

- When you visit a website, the popup automatically filters entries matching the current domain
- Use the search bar to find any entry by title, username, URL, or notes
- Use arrow keys + Enter for keyboard navigation

### 4. Autofill credentials

- Click the **autofill icon** (arrows) on any entry to fill the login form on the current page
- Or copy the username/password individually using the copy buttons

### 5. Settings

Click the gear icon in the popup header to configure:

| Setting | Options | Default |
|---------|---------|---------|
| Mode | Standalone / KeePassXC | Standalone |
| Auto-lock timeout | 1, 5, 10, 15, 30 min, or Never | 5 minutes |
| Clipboard clear | 10, 15, 30, 60 sec, or Never | 15 seconds |

### KeePassXC mode (optional)

If you prefer to use KeePassXC as the backend instead of importing a `.kdbx` file directly:

1. Install [KeePassXC](https://keepassxc.org/) and enable browser integration in its settings
2. Open PassForge **Settings** and switch mode to **KeePassXC**
3. Click **Connect** — KeePassXC will prompt you to approve the connection
4. Once connected, entries are fetched from KeePassXC for each site you visit

## Development

```bash
# Watch mode — rebuilds on file changes
npm run dev

# Type-check + production build
npm run build

# Run tests
npm test
```

### Project structure

```
├── manifest.json                  # MV3 extension manifest
├── popup.html                     # Popup entry HTML
├── src/
│   ├── background/
│   │   ├── service-worker.ts      # Message router, badge updates
│   │   ├── kdbx-manager.ts        # Import/unlock/search via kdbxweb
│   │   ├── auto-lock.ts           # Idle detection + timeout
│   │   └── native-messaging.ts    # KeePassXC bridge
│   ├── popup/
│   │   ├── App.tsx                # Main popup app (React)
│   │   ├── components/
│   │   │   ├── ImportDb.tsx       # Database file picker
│   │   │   ├── UnlockForm.tsx     # Master password entry
│   │   │   ├── EntryList.tsx      # Searchable entry list
│   │   │   ├── EntryItem.tsx      # Single entry with actions
│   │   │   └── Settings.tsx       # Extension settings
│   │   └── hooks/
│   │       ├── useAuth.ts
│   │       └── useEntries.ts
│   ├── content/
│   │   ├── content-script.ts      # Form detection + autofill listener
│   │   └── form-detector.ts       # Login form heuristics
│   └── shared/
│       ├── types.ts               # Shared TypeScript types
│       ├── messages.ts            # Message protocol definitions
│       └── crypto-utils.ts        # Clipboard + domain matching utils
├── native-messaging/
│   └── passforge.json             # Native messaging host manifest
└── dist/                          # Built extension (load this in browser)
```

## Security

- The decrypted database is held **in memory only** — never written to disk or extension storage
- Passwords use kdbxweb's `ProtectedValue` (XOR-encrypted in memory)
- Clipboard auto-clears after a configurable timeout
- Auto-lock on idle, browser lock, or extension suspend
- No telemetry, no external network requests
- Strict Content Security Policy (`script-src 'self'`)

## Tech stack

- **Manifest V3** — modern Chrome/Brave extension format
- **[kdbxweb](https://github.com/keeweb/kdbxweb)** — KeePass .kdbx parser with WebCrypto
- **React 18** + **TypeScript** + **Tailwind CSS** — popup UI
- **Vite** — build tooling
- **Vitest** — unit testing

## License

MIT
