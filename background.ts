import type { PlasmoMessaging } from "@plasmohq/messaging"

// Allow users to open the side panel by clicking on the action toolbar icon
chrome.sidePanel.setPanelBehavior({ openPanelOnActionIconClick: true }).catch((error) => console.error(error));

const handler: PlasmoMessaging.MessageHandler = async (req: any, res: any) => {
  const { action, tabId } = req.body || {}

  if (action === "openSidePanel" && tabId) {
    try {
      await chrome.sidePanel.open({ tabId: tabId })
      res.send({ success: true })
    } catch (err: any) {
      res.send({ success: false, error: err.message })
    }
  } else {
    res.send({ success: false, error: "Invalid request" })
  }
}

export default handler
