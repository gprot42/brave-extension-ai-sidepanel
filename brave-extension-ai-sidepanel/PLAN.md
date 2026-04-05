Plan to Build: Gemini Side Panel Extension for Google Workspaces (as a Brave/Chrome Extension)
This is a complete, actionable roadmap to build a Manifest V3 Brave/Chrome extension that:

Opens a clean side panel from the right side of the browser window when enabled on Google Docs (and optionally Sheets/Slides).
Automatically reads the main document text + all comments (including replies, authors, resolved status).
Lets the user choose a Gemini model (Gemini Flash 3, Gemini 3.1 Flash Lite, Gemini 3.1 Pro — or whatever the exact IDs are when you build it).
Sends the context + user prompt to the chosen Gemini model via the official Gemini REST API and displays the response in a chat-like interface.

The extension works only on Google Workspaces pages (docs.google.com, etc.) for security and performance.
1. Architecture Overview

Browser Side Panel (chrome.sidePanel API) → Your custom UI (HTML/CSS/JS).
Content Script (injected into Google Docs) → Extracts text + comments from the live DOM.
Background Service Worker → Handles messaging, API key storage, and model routing.
Options Page (optional) → For API key management.
Communication → chrome.runtime.sendMessage / chrome.runtime.connect (ports for real-time chat).
Gemini Integration → Direct fetch to https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent (or streaming with streamGenerateContent).

Why this stack?

Side Panel API is native, persistent, and opens from the right exactly as requested.
DOM extraction is the simplest and most reliable client-side method (Google Docs DOM is complex but well-documented by the community).
No server required; everything runs locally in the browser.

2. Prerequisites

Brave browser (or Chrome) with developer mode enabled (brave://extensions/).
API key from Google AI Studio — free tier works for Flash models.
Basic knowledge of HTML/CSS/JS + Manifest V3.
(Recommended) Use Vite + TypeScript or the Plasmo framework for faster development and hot-reload.

3. Step-by-Step Build Plan
Step 3.1: Create the Project Skeleton

Create folder: gemini-workspace-sidepanel
Inside it:
manifest.json
sidepanel.html + sidepanel.js + sidepanel.css
content.js (or content.ts)
background.js
options.html (for API key)
icons/ folder (16, 32, 48, 128 px)

(Optional but recommended) Initialize with Vite or Plasmo for modern tooling.

Step 3.2: Configure manifest.json (Manifest V3)
JSON{
  "manifest_version": 3,
  "name": "Gemini Workspace Side Panel",
  "version": "1.0",
  "description": "Gemini AI side panel for Google Docs with document + comment context",
  "permissions": ["sidePanel", "storage", "activeTab"],
  "host_permissions": ["https://docs.google.com/*", "https://drive.google.com/*"],
  "background": { "service_worker": "background.js" },
  "side_panel": {
    "default_path": "sidepanel.html"
  },
  "action": {
    "default_popup": "",  // We use side panel instead
    "default_title": "Open Gemini Side Panel"
  },
  "content_scripts": [
    {
      "matches": ["https://docs.google.com/document/*"],
      "js": ["content.js"],
      "run_at": "document_idle"
    }
  ],
  "icons": { ... }
}
Step 3.3: Implement the Side Panel UI (sidepanel.html + JS)

Modern chat interface (like Gemini itself).
Top bar: Model selector dropdown (gemini-flash-3, gemini-3.1-flash-lite, gemini-3.1-pro — map these to real model IDs).
“Enable / Refresh Context” button.
Chat window (messages + Gemini responses).
Prompt textarea + Send button.
Settings gear for API key input (saved to chrome.storage.sync).

Use chrome.runtime.sendMessage to request current document context from the content script when the panel opens or the user clicks “Refresh”.
Step 3.4: Content Script – Extract Main Text + Comments (content.js)
Google Docs DOM is dynamic, so:

Use MutationObserver on .kix-appview-editor (or .kix-lineview / .doc-lineview containers).
Collect main text: traverse visible .kix-paragraph or .kix-lineview elements and .innerText.
Collect comments: query the comments pane (classes like .docos-comment, .docos-thread, etc.) — extract author, text, resolved status, highlighted text.
Debounce updates (every 800ms or on selectionchange + mutations).
Send data via chrome.runtime.sendMessage({ action: "getDocumentContext" }).

Pro tip: Many community extensions already do this successfully (search “google docs content script extract text” for up-to-date selectors). The DOM changes occasionally, so make the extraction functions easy to update.
Step 3.5: Background Service Worker (background.js)

Listen for side panel open (or action click).
On action icon click:JavaScriptchrome.sidePanel.open({ tabId: tab.id });
Forward messages between side panel and content script.
(Optional) Add context-menu item “Ask Gemini about selection”.

Step 3.6: Gemini API Integration (in sidepanel.js or a shared utils file)

Store API key securely in chrome.storage.
Example call:JavaScriptasync function callGemini(model, promptWithContext) {
  const key = (await chrome.storage.sync.get("geminiApiKey")).geminiApiKey;
  const response = await fetch(
    `https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent?key=${key}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        contents: [{ parts: [{ text: promptWithContext }] }]
      })
    }
  );
  // Parse and display (add streaming support later for better UX)
}
Construct prompt:
"You are a helpful assistant. Here is the full Google Doc text:\n\n${mainText}\n\nComments:\n${commentsList}\n\nUser question: ${userPrompt}"

Step 3.7: Enable / Open Flow

User installs extension → clicks the toolbar icon.
If on a Google Doc, chrome.sidePanel.open() triggers.
Side panel loads → immediately asks content script for context.
User selects model → types prompt → gets AI response with full document awareness.

Step 3.8: Advanced / Polish Features (Phase 2)

Streaming responses (use streamGenerateContent).
Chat history (multi-turn conversation with same context).
Support for Sheets/Slides (different content script logic).
“Smart context” toggle (only send selected text + nearby comments).
Error handling & nice UI (loading spinners, model rate-limit messages).
Optional: OAuth route using Google Docs + Drive APIs (more reliable but requires Google Cloud project + chrome.identity scopes).

Step 3.9: Testing & Debugging

Load unpacked in Brave (brave://extensions/ → Load unpacked).
Open a Google Doc.
Click extension icon → side panel should appear on the right.
Test text extraction, comment parsing, and Gemini calls.
Use console logs + chrome.runtime message inspector.

Step 3.10: Packaging & Distribution

Zip the folder (or use web-ext build if using web-ext).
Load in Brave/Chrome for personal use.
(Optional) Publish to Chrome Web Store (Brave users can install from there).

4. Potential Challenges & Mitigations





























ChallengeSolutionGoogle Docs DOM changesMake extraction modular; add fallback polling + community-maintained selectorsAPI key securityStored only in chrome.storage.sync; never hard-codedRate limits / costLet user choose cheaper Flash models; add usage counterSide panel vs native feelStyle it to match Google’s Material 3 design systemMultiple tabsUse tab-specific side panel options
5. Estimated Effort

MVP: 8–12 hours (basic side panel + text extraction + Gemini calls).
Polished version: 20–30 hours (streaming, nice UI, error handling, Sheets support).

Would you like me to:

Generate the full starter code repository structure right now?
Provide the exact current DOM selectors for text + comments (updated for 2026)?
Or start with a GitHub-ready template?

Just say the word and I’ll deliver the next piece! This extension will feel like the official Gemini side panel but fully customizable and powered by the model of your choice.
