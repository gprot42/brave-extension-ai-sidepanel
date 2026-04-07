# Joplin Notebook Encryption Plugin

🔐 Add notebook-level encryption to Joplin to protect your sensitive notes with password-based encryption.

## Features

- **Notebook-Level Encryption** - Encrypt entire notebooks with unique passwords
- **AES-256-GCM Encryption** - Military-grade authenticated encryption
- **Password Caching** - Cache passwords for a configurable duration (default 10 minutes)
- **Transparent Encryption** - Notes decrypt/encrypt automatically when opened/saved
- **Sync Compatible** - Encrypted content syncs across all your devices
- **Context Menu Integration** - Easy access through right-click menus

## Installation

### From Joplin Plugin Repository (Recommended)

1. Open Joplin
2. Go to **Tools → Options → Plugins**
3. Search for "Notebook Encryption"
4. Click **Install**
5. Restart Joplin

### Manual Installation

1. Download the latest release `.jpl` file
2. In Joplin, go to **Tools → Options → Plugins**
3. Click on the gear icon and select **Install from file**
4. Select the downloaded `.jpl` file
5. Restart Joplin

## Usage

### Enable Encryption for a Notebook

1. Right-click on a notebook in the sidebar
2. Select **"Enable Encryption for Notebook"**
3. Enter and confirm a strong password
4. Click **"Enable Encryption"**

All existing notes in the notebook will be encrypted, and any new notes you create will be encrypted automatically.

### Access Encrypted Notes

1. Click on a note in an encrypted notebook
2. If the password is not cached, you'll be prompted to enter it
3. Enter the correct password
4. The note content will be decrypted and displayed

The password is cached for 10 minutes by default (configurable in settings).

### Disable Encryption

1. Right-click on an encrypted notebook
2. Select **"Disable Encryption for Notebook"**
3. Enter the notebook password
4. Click **"Disable"**

All notes will be decrypted and stored in plain text.

### Change Password

1. Right-click on an encrypted notebook
2. Select **"Change Notebook Password"**
3. Enter your current password
4. Enter and confirm your new password
5. Click **"Change Password"**

### Lock a Notebook

To immediately clear the cached password:

1. Right-click on an encrypted notebook
2. Select **"Lock Notebook"**

You'll need to enter the password again to access notes.

## Settings

Access settings via **Tools → Options → Notebook Encryption**

| Setting | Default | Description |
|---------|---------|-------------|
| Password cache timeout | 10 min | Duration to keep passwords in memory |
| Show lock indicator | Yes | Display 🔒 icon on encrypted notebooks |
| Clear cache on lock | Yes | Clear passwords when computer locks |
| Require password after sync | No | Re-prompt after synchronization |

## Security

### Encryption Details

- **Algorithm**: AES-256-GCM (Authenticated Encryption)
- **Key Derivation**: PBKDF2 with SHA-256 (100,000 iterations)
- **Salt**: 16 bytes, randomly generated per notebook
- **IV**: 12 bytes, randomly generated per encryption

### Security Features

- Passwords are **never** stored to disk
- Passwords are kept in memory only during the cache window
- PBKDF2 with high iterations protects against brute force
- GCM mode provides authentication (detects tampering)
- Random IV prevents pattern analysis

### Limitations

- **Note titles** remain visible (only body is encrypted)
- **Search** will not find text inside encrypted notes
- **Attachments/resources** are not encrypted by this plugin
- If you **forget your password**, notes **cannot be recovered**

## Troubleshooting

### "Incorrect password" error
- Make sure Caps Lock is off
- Try typing the password in a text editor first to verify
- If you've forgotten the password, there is no recovery option

### Notes not decrypting after sync
- Re-enter the password when prompted
- Check that the same encryption settings are used on all devices

### Plugin not appearing
- Restart Joplin after installation
- Check **Tools → Options → Plugins** to verify it's enabled

## Development

### Building from Source

```bash
# Clone the repository
git clone https://github.com/your-repo/joplin-notebook-encryption
cd joplin-notebook-encryption

# Install dependencies
npm install

# Build the plugin
npm run dist
```

### Testing

```bash
npm test
```

### Project Structure

```
src/
├── index.ts                 # Plugin entry point
├── settings.ts              # Plugin settings registration
├── commands.ts              # Commands and context menus
├── types.ts                 # TypeScript type definitions
├── services/
│   ├── encryptionService.ts # AES-256-GCM encryption
│   ├── passwordCache.ts     # In-memory password cache
│   └── notebookConfigService.ts # Notebook config management
├── handlers/
│   └── noteHandler.ts       # Note encryption/decryption
└── ui/
    └── dialogs/
        └── passwordDialog.ts # Password prompt dialogs
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Acknowledgments

- Built for [Joplin](https://joplinapp.org/) - the open source note taking app
- Uses Web Crypto API for cryptographic operations

---

**⚠️ Important**: Always keep a backup of your notes. If you forget your encryption password, there is no way to recover the encrypted notes.