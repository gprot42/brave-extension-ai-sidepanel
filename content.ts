import type { PlasmoCSConfig } from "plasmo"

export const config: PlasmoCSConfig = {
  matches: ["https://docs.google.com/document/*"],
  run_at: "document_idle"
}


// Fix type issues in content script (NodeJS.Timeout vs number)

let lastContext: any = null
let observer: MutationObserver | null = null
let debounceTimer: NodeJS.Timeout | number | null = null

const extractText = (): string => {
  const selectors = [
    '.kix-lineview-content', 
    '.kix-paragraphrenderer', 
    '[role="presentation"] .kix-lineview',
    'div[role="textbox"]'
  ]
  
  let text = ''
  for (const sel of selectors) {
    const els = document.querySelectorAll(sel)
    els.forEach((el) => {
      if (el.textContent) text += el.textContent + '\n'
    })
    if (text.length > 100) break
  }
  return text.trim() || document.body.innerText.substring(0, 8000)
}

const extractComments = (): any[] => {
  const comments: any[] = []
  const commentEls = document.querySelectorAll('.docos-comment, .docos-thread, [data-comment-id]')
  
  commentEls.forEach((el, i) => {
    comments.push({
      id: el.getAttribute('data-comment-id') || `c${i}`,
      author: (el.querySelector('.docos-author, .user-name, [data-tooltip]') as HTMLElement)?.innerText?.trim() || 'Unknown',
      text: el.textContent?.trim().replace(/\s+/g, ' ').substring(0, 200) || '',
      resolved: el.classList.contains('docos-resolved') || false,
      timestamp: new Date().toISOString()
    })
  })
  return comments
}

const sendContext = () => {
  const docText = extractText()
  const comments = extractComments()
  
  const contextPayload = {
    documentText: docText.substring(0, 30000),
    comments,
    url: location.href,
    title: document.title,
    timestamp: Date.now()
  }
  
  if (JSON.stringify(contextPayload) !== JSON.stringify(lastContext)) {
    lastContext = contextPayload
    chrome.runtime.sendMessage({
      action: "documentContext",
      context: contextPayload
    }).catch(() => {})
  }
}

const debouncedSend = () => {
  if (debounceTimer) clearTimeout(debounceTimer as NodeJS.Timeout)
  debounceTimer = setTimeout(sendContext, 800)
}

const startObserver = () => {
  if (observer) return
  
  observer = new MutationObserver(debouncedSend)
  observer.observe(document.body, { 
    childList: true, 
    subtree: true, 
    characterData: true,
    attributes: false
  })
  
  window.addEventListener('focus', debouncedSend)
  document.addEventListener('selectionchange', debouncedSend)
  
  // Initial extraction
  setTimeout(sendContext, 1200)
  
  console.log('%c[Gemini Sidepanel] Content script ready — watching for docs changes', 'color:#10b981;font-weight:500')
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', startObserver)
} else {
  startObserver()
}

// Allow manual refresh from popup/sidepanel
(window as any).refreshGeminiContext = sendContext
