// Gemini API utilities with streaming support and token estimation
// Models updated for 2026 (Gemini 3.1 series)

export const GEMINI_MODELS = {
  flash: 'gemini-3.1-flash',
  flashLite: 'gemini-3.1-flash-lite',
  pro: 'gemini-3.1-pro'
} as const

export type GeminiModel = keyof typeof GEMINI_MODELS

export const getModelId = (key: GeminiModel): string => GEMINI_MODELS[key]

export interface DocContext {
  documentText: string
  comments: Array<{
    id: string
    author: string
    text: string
    resolved: boolean
    timestamp: string
  }>
  url: string
  title: string
  timestamp: number
}

export const estimateTokens = (text: string): number => {
  // Rough estimate: 4 chars per token (conservative)
  return Math.ceil(text.length / 3.5)
}

export const buildPrompt = (context: DocContext, userPrompt: string): string => {
  const commentsSummary = context.comments.length 
    ? context.comments.map(c => 
        `[${c.author}]: ${c.text} ${c.resolved ? '(resolved)' : ''}`
      ).join('\n')
    : 'No comments.'

  return `You are a helpful assistant for Google Docs.

**Document Title:** ${context.title}
**URL:** ${context.url}

**DOCUMENT TEXT:**
${context.documentText}

**COMMENTS:**
${commentsSummary}

**USER QUESTION:**
${userPrompt}

Provide concise, actionable response. Reference specific parts of document/comments when relevant. Use markdown.
`
}

// Streaming fetch to Gemini API
export const streamGemini = async (
  modelId: string, 
  prompt: string, 
  apiKey: string,
  onChunk: (chunk: any) => void
): Promise<void> => {
  const url = `https://generativelanguage.googleapis.com/v1beta/models/${modelId}:streamGenerateContent?alt=sse&key=${apiKey}`

  const response = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents: [{
        parts: [{ text: prompt }]
      }],
      generationConfig: {
        temperature: 0.7,
        maxOutputTokens: 4096
      }
    })
  })

  if (!response.ok) {
    const err = await response.text()
    throw new Error(`Gemini API error: ${response.status} - ${err}`)
  }

  const reader = response.body?.getReader()
  if (!reader) throw new Error('No response body')

  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const json = JSON.parse(line.slice(6))
          const text = json.candidates?.[0]?.content?.parts?.[0]?.text || ''
          if (text) onChunk(text)
        } catch (e) {
          // Ignore parse errors for incomplete chunks
        }
      }
    }
  }
}
