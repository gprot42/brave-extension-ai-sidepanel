import React, { useState, useEffect, useRef } from "react"
import type { DocContext, GeminiModel } from "./utils/gemini"
import * as GeminiUtils from "./utils/gemini"

const Sidepanel = () => {
  const [messages, setMessages] = useState<Array<{role: string, content: string}>>([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [selectedModel, setSelectedModel] = useState<GeminiModel>('flash')
  const [context, setContext] = useState<DocContext | null>(null)
  const [showSettings, setShowSettings] = useState(false)
  
  const chatEndRef = useRef<HTMLDivElement>(null)
  const currentStreamRef = useRef<string>('')

  // Load API key
  useEffect(() => {
    chrome.storage.sync.get(['geminiApiKey', 'preferredModel'], (result) => {
      if (result.geminiApiKey) setApiKey(result.geminiApiKey)
      if (result.preferredModel) setSelectedModel(result.preferredModel)
    })
  }, [])

  // Listen for context from content script
  useEffect(() => {
    const listener = (msg: any) => {
      if (msg.action === "documentContext") {
        setContext(msg.context)
        setMessages(prev => [...prev, {
          role: "system",
          content: `Context loaded from: ${msg.context.title} (${msg.context.comments.length} comments)`
        }])
      }
    }
    chrome.runtime.onMessage.addListener(listener)
    return () => chrome.runtime.onMessage.removeListener(listener)
  }, [])

  const saveApiKey = (key: string) => {
    chrome.storage.sync.set({ geminiApiKey: key })
    setApiKey(key)
    setShowSettings(false)
  }

  const refreshContext = () => {
    chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
      if (tabs[0]?.id) {
        chrome.tabs.sendMessage(tabs[0].id, { action: "refreshContext" })
      }
    })
  }

  const sendMessage = async () => {
    if (!input.trim() || !apiKey || isLoading || !context) return

    const userMsg = input.trim()
    setMessages(prev => [...prev, { role: "user", content: userMsg }])
    setInput('')
    setIsLoading(true)
    
    const fullPrompt = GeminiUtils.buildPrompt(context, userMsg)
    const modelId = GeminiUtils.getModelId(selectedModel)

    currentStreamRef.current = ''

    try {
      await GeminiUtils.streamGemini(
        modelId, 
        fullPrompt, 
        apiKey,
        (chunk) => {
          currentStreamRef.current += chunk
          setMessages(prev => {
            const last = prev[prev.length - 1]
            if (last?.role === 'assistant') {
              return [...prev.slice(0, -1), { role: 'assistant', content: currentStreamRef.current }]
            }
            return [...prev, { role: 'assistant', content: chunk }]
          })
        }
      )
    } catch (error: any) {
      setMessages(prev => [...prev, { 
        role: "assistant", 
        content: `Error: ${error.message || 'Failed to get response from Gemini'}` 
      }])
    } finally {
      setIsLoading(false)
      currentStreamRef.current = ''
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages])

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-white">
      {/* Header */}
      <div className="bg-zinc-900 border-b border-zinc-800 p-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-6 h-6 bg-gradient-to-br from-blue-500 to-purple-600 rounded flex items-center justify-center text-xs font-bold">G</div>
          <div>
            <div className="font-semibold text-sm">Gemini Docs</div>
            <div className="text-[10px] text-zinc-500">3.1 models • Live context</div>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          <select 
            value={selectedModel}
            onChange={(e) => {
              const m = e.target.value as GeminiModel
              setSelectedModel(m)
              chrome.storage.sync.set({ preferredModel: m })
            }}
            className="bg-zinc-800 text-xs border border-zinc-700 rounded px-2 py-1"
          >
            <option value="flash">3.1 Flash</option>
            <option value="flashLite">3.1 Flash Lite</option>
            <option value="pro">3.1 Pro</option>
          </select>
          
          <button
            onClick={() => setShowSettings(!showSettings)}
            className="p-1.5 hover:bg-zinc-800 rounded"
            title="Settings"
          >
            ⚙
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-auto p-4 space-y-4 text-sm">
        {!context && (
          <div className="text-center py-8 text-zinc-400">
            Open a Google Doc and click <span className="font-medium">Refresh Context</span>
          </div>
        )}
        
        {messages.map((msg, i) => (
          <div key={i} className={`flex ${msg.role === 'user' ? 'justify-end' : ''}`}>
            <div className={`max-w-[85%] rounded-2xl px-4 py-3 ${
              msg.role === 'user' 
                ? 'bg-blue-600 text-white' 
                : 'bg-zinc-800 text-zinc-100'
            }`}>
              <div className="whitespace-pre-wrap">{msg.content}</div>
            </div>
          </div>
        ))}
        
        {isLoading && (
          <div className="flex items-center gap-2 text-zinc-400 text-sm pl-2">
            <span className="animate-pulse">thinking</span>
            <span className="animate-[bounce_1.4s_infinite]">.</span>
          </div>
        )}
        
        <div ref={chatEndRef} />
      </div>

      {/* Input area */}
      <div className="p-3 border-t border-zinc-800 bg-zinc-900">
        <div className="flex gap-2 mb-2">
          <button 
            onClick={refreshContext}
            className="text-xs px-3 py-1 bg-zinc-800 hover:bg-zinc-700 rounded border border-zinc-700 flex-1"
          >
            🔄 Refresh Context
          </button>
          
          {context && (
            <div className="text-[10px] px-3 py-1 bg-emerald-900/50 text-emerald-300 rounded self-center whitespace-nowrap">
              ~{GeminiUtils.estimateTokens(context.documentText)} tokens
            </div>
          )}
        </div>

        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={context ? "Ask about the document..." : "Load document context first"}
            disabled={!context || isLoading}
            className="flex-1 bg-zinc-800 border border-zinc-700 rounded-xl px-4 py-3 text-sm resize-none h-12 focus:outline-none focus:border-blue-500"
            rows={1}
          />
          <button
            onClick={sendMessage}
            disabled={!input.trim() || !apiKey || isLoading || !context}
            className="bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 px-5 rounded-xl transition-colors flex items-center"
          >
            ↑
          </button>
        </div>
      </div>

      {/* API Key Modal */}
      {showSettings && (
        <div className="absolute inset-0 bg-black/80 flex items-center justify-center z-50">
          <div className="bg-zinc-900 rounded-3xl p-6 w-[90%] max-w-md">
            <h3 className="text-lg font-medium mb-4">Gemini API Key</h3>
            <p className="text-xs text-zinc-400 mb-4">Get free key at <a href="https://aistudio.google.com/app/apikey" target="_blank" className="underline">Google AI Studio</a></p>
            
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="AIza..."
              className="w-full bg-black border border-zinc-700 rounded-xl px-4 py-3 text-sm mb-4 font-mono"
            />
            
            <div className="flex gap-3">
              <button 
                onClick={() => setShowSettings(false)}
                className="flex-1 py-3 text-sm border border-zinc-700 rounded-2xl"
              >
                Cancel
              </button>
              <button 
                onClick={() => saveApiKey(apiKey)}
                className="flex-1 py-3 bg-white text-black text-sm rounded-2xl font-medium"
              >
                Save Key
              </button>
            </div>
            
            <p className="text-[10px] text-center mt-6 text-zinc-500">Key is stored locally with chrome.storage.sync</p>
          </div>
        </div>
      )}
    </div>
  )
}

export default Sidepanel
