import { useState, useRef, useEffect } from 'react';

interface Message {
  role: 'user' | 'assistant' | 'error';
  content: string;
  dataSummary?: Record<string, number>;
}

interface Props {
  ollamaUrl: string;
  model: string;
  days: number;
  provider: 'ollama' | 'lmstudio';
}

export default function AIAnalysis({ ollamaUrl, model, days, provider }: Props) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [prompt, setPrompt] = useState('');
  const [loading, setLoading] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo(0, scrollRef.current.scrollHeight);
  }, [messages]);

  useEffect(() => {
    if (messages.length > 0) setExpanded(true);
  }, [messages.length]);

  const send = async () => {
    const text = prompt.trim();
    if (!text || loading) return;
    setPrompt('');
    setMessages((m) => [...m, { role: 'user', content: text }]);
    setExpanded(true);
    setLoading(true);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 300_000); // 5 min timeout
    try {
      const res = await fetch('/api/ai-analysis', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt: text, days, model, ollama_url: ollamaUrl, provider }),
        signal: controller.signal,
      });
      clearTimeout(timeout);
      if (!res.ok) {
        const err = await res.json().catch(() => null);
        const detail = err?.detail || `Server error ${res.status}`;
        setMessages((m) => [...m, { role: 'error', content: detail }]);
      } else {
        const data = await res.json();
        setMessages((m) => [
          ...m,
          { role: 'assistant', content: data.answer, dataSummary: data.data_summary },
        ]);
      }
    } catch (e: unknown) {
      clearTimeout(timeout);
      const msg = e instanceof DOMException && e.name === 'AbortError'
        ? 'Request timed out (5 min). The model may be too slow.'
        : 'Cannot reach server. Is the backend running?';
      setMessages((m) => [...m, { role: 'error', content: msg }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-gray-900 px-4 py-2">
      {/* Chat history — shown when expanded */}
      {expanded && messages.length > 0 && (
        <div className="mb-2">
          <div className="flex items-center justify-between mb-1">
            <span className="text-[10px] text-gray-500 uppercase tracking-wide font-semibold">AI Health Analysis</span>
            <button
              onClick={() => setExpanded(false)}
              className="text-[10px] text-gray-600 hover:text-gray-400"
            >
              Collapse
            </button>
          </div>
          <div ref={scrollRef} className="max-h-[250px] overflow-auto space-y-2">
            {messages.map((m, i) => (
              <div
                key={i}
                className={`text-xs rounded-lg px-3 py-2 max-w-[90%] ${
                  m.role === 'user'
                    ? 'bg-blue-600/20 text-blue-200 ml-auto'
                    : m.role === 'error'
                    ? 'bg-red-900/30 text-red-300'
                    : 'bg-gray-800 text-gray-300'
                }`}
              >
                <div className="whitespace-pre-wrap">{m.content}</div>
                {m.dataSummary && (
                  <div className="mt-1 text-[10px] text-gray-500">
                    Data: {m.dataSummary.hr_readings} HR, {m.dataSummary.spo2_readings} SpO2,{' '}
                    {m.dataSummary.sleep_sessions} sleep, {m.dataSummary.stress_readings} stress,{' '}
                    {m.dataSummary.hrv_readings} HRV, {m.dataSummary.activity_days} activity days
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div className="text-xs text-gray-500 animate-pulse px-3 py-2">Analyzing...</div>
            )}
          </div>
        </div>
      )}

      {/* Prompt bar — always visible */}
      <div className="flex items-center gap-2">
        <div className="flex items-center gap-1.5 flex-1">
          <span className="text-xs text-gray-300 whitespace-nowrap font-medium">
            {model} &middot; {days}d
          </span>
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="Ask about your health data..."
            rows={1}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-xs text-gray-200 resize-none focus:outline-none focus:border-blue-500"
          />
        </div>
        <button
          onClick={send}
          disabled={loading || !prompt.trim()}
          className="bg-blue-600 hover:bg-blue-500 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded-lg"
        >
          Send
        </button>
        {messages.length > 0 && !expanded && (
          <button
            onClick={() => setExpanded(true)}
            className="text-[10px] text-gray-500 hover:text-gray-400 whitespace-nowrap"
          >
            Show chat
          </button>
        )}
      </div>
      <p className="text-[9px] text-gray-400 mt-1">
        Not medical advice. Consult a healthcare professional. Use at your own risk.
      </p>
    </div>
  );
}
