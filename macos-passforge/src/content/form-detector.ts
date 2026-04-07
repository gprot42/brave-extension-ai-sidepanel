import type { LoginFormInfo } from '../shared/types';

const USERNAME_SELECTORS = [
  'input[autocomplete="username"]',
  'input[autocomplete="email"]',
  'input[type="email"]',
  'input[type="text"][name*="user" i]',
  'input[type="text"][name*="login" i]',
  'input[type="text"][name*="email" i]',
  'input[type="text"][name*="session" i]',
  'input[type="text"][id*="user" i]',
  'input[type="text"][id*="login" i]',
  'input[type="text"][id*="email" i]',
  'input[type="text"][placeholder*="email" i]',
  'input[type="text"][placeholder*="user" i]',
  'input[type="text"][placeholder*="phone" i]',
  'input[type="text"][aria-label*="email" i]',
  'input[type="text"][aria-label*="user" i]',
  // Bare input (no type attribute) — common on LinkedIn, etc.
  'input:not([type])[name*="user" i]',
  'input:not([type])[name*="email" i]',
  'input:not([type])[name*="session" i]',
  'input:not([type])[name*="login" i]',
  'input:not([type])[id*="user" i]',
  'input:not([type])[id*="email" i]',
  'input:not([type])[id*="login" i]',
  'input:not([type])[autocomplete="username"]',
  'input:not([type])[autocomplete="email"]',
  'input:not([type])[placeholder*="email" i]',
  'input:not([type])[placeholder*="phone" i]',
];

function getUniqueSelector(el: Element): string {
  if (el.id) return `#${CSS.escape(el.id)}`;
  if (el.getAttribute('name')) {
    const name = el.getAttribute('name')!;
    const tag = el.tagName.toLowerCase();
    const type = el.getAttribute('type') || '';
    return `${tag}[name="${CSS.escape(name)}"]${type ? `[type="${type}"]` : ''}`;
  }

  // Fallback: build a path
  const parts: string[] = [];
  let current: Element | null = el;
  while (current && current !== document.body) {
    let selector = current.tagName.toLowerCase();
    if (current.id) {
      selector = `#${CSS.escape(current.id)}`;
      parts.unshift(selector);
      break;
    }
    const parent: Element | null = current.parentElement;
    if (parent) {
      const currentTag = current.tagName;
      const siblings = Array.from(parent.children).filter(
        (c: Element) => c.tagName === currentTag
      );
      if (siblings.length > 1) {
        const index = siblings.indexOf(current) + 1;
        selector += `:nth-of-type(${index})`;
      }
    }
    parts.unshift(selector);
    current = parent;
  }
  return parts.join(' > ');
}

function findUsernameField(passwordField: HTMLInputElement): HTMLInputElement | null {
  // Check within the same form
  const form = passwordField.closest('form');
  const searchRoot = form || passwordField.parentElement?.parentElement?.parentElement || document;

  for (const selector of USERNAME_SELECTORS) {
    const candidates = searchRoot.querySelectorAll<HTMLInputElement>(selector);
    for (const candidate of candidates) {
      if (isVisible(candidate) && candidate !== passwordField) {
        return candidate;
      }
    }
  }

  // Fallback: find any visible text/email input before the password field
  const allInputs = Array.from(searchRoot.querySelectorAll<HTMLInputElement>('input'));
  const pwIndex = allInputs.indexOf(passwordField);

  for (let i = pwIndex - 1; i >= 0; i--) {
    const input = allInputs[i];
    const type = (input.getAttribute('type') || '').toLowerCase();
    if (['text', 'email', ''].includes(type) && isVisible(input)) {
      return input;
    }
  }

  return null;
}

function isVisible(el: HTMLElement): boolean {
  if (el.offsetParent === null && el.style.position !== 'fixed') return false;
  const style = window.getComputedStyle(el);
  return style.display !== 'none' && style.visibility !== 'hidden' && style.opacity !== '0';
}

export function detectLoginForms(): LoginFormInfo[] {
  const passwordFields = document.querySelectorAll<HTMLInputElement>(
    'input[type="password"]'
  );

  const forms: LoginFormInfo[] = [];

  for (const pwField of passwordFields) {
    if (!isVisible(pwField)) continue;

    const usernameField = findUsernameField(pwField);
    const form = pwField.closest('form');

    forms.push({
      usernameField: usernameField
        ? { selector: getUniqueSelector(usernameField) }
        : null,
      passwordField: { selector: getUniqueSelector(pwField) },
      formSelector: form ? getUniqueSelector(form) : null,
    });
  }

  // If no password field found, look for standalone username/email fields
  // (handles multi-step logins like X/Twitter, Google, Microsoft)
  if (forms.length === 0) {
    const usernameField = findStandaloneUsernameField();
    if (usernameField) {
      forms.push({
        usernameField: { selector: getUniqueSelector(usernameField) },
        passwordField: { selector: '' },
        formSelector: usernameField.closest('form')
          ? getUniqueSelector(usernameField.closest('form')!)
          : null,
      });
    }
  }

  return forms;
}

function findStandaloneUsernameField(): HTMLInputElement | null {
  for (const selector of USERNAME_SELECTORS) {
    const candidates = document.querySelectorAll<HTMLInputElement>(selector);
    for (const candidate of candidates) {
      if (isVisible(candidate)) {
        return candidate;
      }
    }
  }
  return null;
}

export function fillCredentials(
  username: string,
  password: string,
  formInfo?: LoginFormInfo
): boolean {
  let pwField: HTMLInputElement | null = null;
  let userField: HTMLInputElement | null = null;

  if (formInfo) {
    if (formInfo.passwordField.selector) {
      pwField = document.querySelector<HTMLInputElement>(formInfo.passwordField.selector);
    }
    if (formInfo.usernameField) {
      userField = document.querySelector<HTMLInputElement>(formInfo.usernameField.selector);
    }
  }

  // Fallback: find first visible password field
  if (!pwField) {
    const passwordFields = document.querySelectorAll<HTMLInputElement>(
      'input[type="password"]'
    );
    for (const field of passwordFields) {
      if (isVisible(field)) {
        pwField = field;
        break;
      }
    }
  }

  // Fallback: find username field if not found yet
  if (!userField && !pwField) {
    userField = findStandaloneUsernameField();
  } else if (!userField && pwField) {
    userField = findUsernameField(pwField);
  }

  // Need at least one field to fill
  if (!pwField && !userField) return false;

  // Fill username
  if (userField && username) {
    setFieldValue(userField, username);
  }

  // Fill password (if the field exists on this step)
  if (pwField && password) {
    setFieldValue(pwField, password);
  }

  return true;
}

function setFieldValue(field: HTMLInputElement, value: string): void {
  // Focus the field first — required for many frameworks
  field.focus();
  field.dispatchEvent(new FocusEvent('focus', { bubbles: true }));
  field.dispatchEvent(new FocusEvent('focusin', { bubbles: true }));

  // Use native setter to bypass React/Angular controlled inputs
  const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
    HTMLInputElement.prototype,
    'value'
  )?.set;

  if (nativeInputValueSetter) {
    nativeInputValueSetter.call(field, value);
  } else {
    field.value = value;
  }

  // Dispatch events that frameworks listen to
  field.dispatchEvent(new Event('input', { bubbles: true }));
  field.dispatchEvent(new Event('change', { bubbles: true }));

  // React 16+ uses a custom event property — trigger it
  const reactEvent = new Event('input', { bubbles: true });
  Object.defineProperty(reactEvent, 'simulated', { value: true });
  field.dispatchEvent(reactEvent);

  // Blur after filling
  field.dispatchEvent(new FocusEvent('blur', { bubbles: true }));
  field.dispatchEvent(new FocusEvent('focusout', { bubbles: true }));
}
