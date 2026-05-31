// Background service worker: open the side panel when the toolbar icon is clicked.
//
// NOTE: We intentionally do NOT call
// chrome.sidePanel.setPanelBehavior({ openPanelOnActionIconClick: true })
// because that suppresses the action.onClicked event. Some Chromium-based
// browsers (e.g. Brave) do not reliably honor openPanelOnActionIconClick,
// so we open the panel explicitly from the click handler instead. The
// onClicked callback is a valid user gesture, which sidePanel.open() requires.

chrome.action.onClicked.addListener(async (tab) => {
  try {
    if (tab.windowId != null) {
      await chrome.sidePanel.open({ windowId: tab.windowId })
    } else if (tab.id != null) {
      await chrome.sidePanel.open({ tabId: tab.id })
    }
  } catch (err) {
    console.error("Failed to open side panel:", err)
  }
})
