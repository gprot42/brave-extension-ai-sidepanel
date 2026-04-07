import { detectLoginForms, fillCredentials } from './form-detector';
import type { ContentMessage } from '../shared/messages';
import type { Credentials } from '../shared/types';

// Listen for messages from the service worker
chrome.runtime.onMessage.addListener(
  (message: ContentMessage, _sender, sendResponse) => {
    switch (message.type) {
      case 'FILL_CREDENTIALS': {
        const { username, password } = message.credentials as Credentials;
        const forms = detectLoginForms();
        const filled = fillCredentials(username, password, forms[0]);

        // Only respond if we found fields to fill.
        // With all_frames: true, multiple frames receive this message.
        // By only responding on success, the iframe with the actual
        // login form gets to report its result to the service worker.
        if (filled) {
          sendResponse({ success: true });
        } else {
          // Still respond, but use a short delay so frames with forms
          // get a chance to respond first
          setTimeout(() => sendResponse({ success: false }), 500);
        }
        break;
      }

      case 'DETECT_FORMS': {
        const forms = detectLoginForms();
        sendResponse({ forms });
        break;
      }

      case 'GET_FORM_INFO': {
        const forms = detectLoginForms();
        sendResponse({ forms, url: window.location.href });
        break;
      }
    }
    return true;
  }
);

// Notify background about forms on page load
function notifyFormsDetected(): void {
  const forms = detectLoginForms();
  if (forms.length > 0) {
    chrome.runtime.sendMessage({
      type: 'FORMS_DETECTED',
      forms,
    }).catch(() => {
      // Extension context may be invalidated
    });
  }
}

// Initial detection (with delay for SPAs that render async)
setTimeout(notifyFormsDetected, 500);

// Debounced observer — avoids firing on every micro DOM change
let debounceTimer: ReturnType<typeof setTimeout> | null = null;
function debouncedNotify() {
  if (debounceTimer) clearTimeout(debounceTimer);
  debounceTimer = setTimeout(notifyFormsDetected, 300);
}

// Observe DOM changes for SPA navigation
const observer = new MutationObserver(debouncedNotify);

observer.observe(document.body, {
  childList: true,
  subtree: true,
});

// Also detect on URL changes (pushState/popState)
let lastUrl = location.href;
const urlObserver = new MutationObserver(() => {
  if (location.href !== lastUrl) {
    lastUrl = location.href;
    setTimeout(notifyFormsDetected, 800);
  }
});

urlObserver.observe(document, { subtree: true, childList: true });
