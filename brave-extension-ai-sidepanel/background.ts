import type { PlasmoMessaging } from "@plasmohq/messaging"

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
