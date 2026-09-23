import { useEffect, useRef, useState } from 'react'
import Markdown from 'react-markdown'
import { clearHistory, fetchHistory, isAuthError, sendChat } from '../api'
import { BookIcon, GlobeIcon, SendIcon, SparkIcon } from './Icons'

type Msg = {
  id: number
  role: 'user' | 'bot'
  text: string
  tools?: string[]
  error?: boolean
}

const GREETING =
  "Hi! I'm your Yale SOM course assistant. Ask me about courses, instructors, or when something meets — I'll search the catalog, and the web when I need to."

const SUGGESTIONS = [
  'What finance courses meet on Tuesdays?',
  'Who teaches Corporate Finance?',
  'Any AI or machine learning courses?',
  "What's Uri Simonsohn's background?",
]

const TOOL_LABEL: Record<string, string> = {
  search_courses: 'course catalog',
  web_search: 'web search',
}

function ToolChips({ tools }: { tools: string[] }) {
  if (!tools.length) return null
  return (
    <div className="tools">
      <span className="tools__label">used</span>
      {tools.map((t) => (
        <span
          key={t}
          className={`tool-chip${t === 'web_search' ? ' tool-chip--web' : ''}`}
        >
          {t === 'web_search' ? <GlobeIcon /> : <BookIcon />}
          {TOOL_LABEL[t] ?? t}
        </span>
      ))}
    </div>
  )
}

type Props = {
  /** Called when the backend rejects our token, so the app can sign out. */
  onAuthLost: () => void
}

export default function ChatPanel({ onAuthLost }: Props) {
  const [messages, setMessages] = useState<Msg[]>([])
  const [loadingHistory, setLoadingHistory] = useState(true)
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)
  const taRef = useRef<HTMLTextAreaElement>(null)
  // Locally-added messages use negative ids so they can never collide with the
  // row ids that come back from the database.
  const nextLocalId = useRef(-1)

  // Pull this user's saved conversation on mount.
  useEffect(() => {
    const ctrl = new AbortController()
    fetchHistory(ctrl.signal)
      .then((rows) => {
        setMessages(
          rows.map((r) => ({
            id: r.id,
            role: r.role === 'user' ? 'user' : 'bot',
            text: r.content,
            tools: r.tools_used,
          })),
        )
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return
        if (isAuthError(err)) onAuthLost()
        // Any other failure just leaves the panel empty; the greeting still shows.
      })
      .finally(() => {
        if (!ctrl.signal.aborted) setLoadingHistory(false)
      })
    return () => ctrl.abort()
  }, [onAuthLost])

  useEffect(() => {
    logRef.current?.scrollTo({ top: logRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages, busy])

  // Grow the textarea with its content, up to the CSS max-height.
  useEffect(() => {
    const ta = taRef.current
    if (!ta) return
    ta.style.height = 'auto'
    ta.style.height = `${Math.min(ta.scrollHeight, 132)}px`
  }, [draft])

  async function submit(text: string) {
    const message = text.trim()
    if (!message || busy) return

    setMessages((m) => [...m, { id: nextLocalId.current--, role: 'user', text: message }])
    setDraft('')
    setBusy(true)

    try {
      const res = await sendChat(message)
      setMessages((m) => [
        ...m,
        {
          id: nextLocalId.current--,
          role: 'bot',
          text: res.reply || '(empty reply)',
          tools: res.tools_used ?? [],
        },
      ])
    } catch (err) {
      if (isAuthError(err)) {
        onAuthLost()
        return
      }
      setMessages((m) => [
        ...m,
        {
          id: nextLocalId.current--,
          role: 'bot',
          error: true,
          text: `Could not reach the agent — ${
            err instanceof Error ? err.message : String(err)
          }. Is the backend running?`,
        },
      ])
    } finally {
      setBusy(false)
    }
  }

  async function onClear() {
    if (busy || !messages.length) return
    if (!window.confirm('Delete your saved chat history? This cannot be undone.')) {
      return
    }
    try {
      await clearHistory()
      setMessages([])
    } catch (err) {
      if (isAuthError(err)) onAuthLost()
    }
  }

  const empty = !loadingHistory && messages.length === 0

  return (
    <aside className="chat">
      <div className="chat__head">
        <SparkIcon size={22} />
        <div>
          <h2>Course assistant</h2>
          <p>catalog + web search</p>
        </div>
        <span className="masthead__spacer" />
        {messages.length > 0 && (
          <button className="chat__clear" onClick={onClear} disabled={busy}>
            Clear
          </button>
        )}
      </div>

      <div className="chat__log scroll-thin" ref={logRef} aria-live="polite">
        {loadingHistory ? (
          <div className="msg msg--bot">
            <div className="bubble">
              <span className="dots" role="status" aria-label="Loading history">
                <i />
                <i />
                <i />
              </span>
            </div>
          </div>
        ) : (
          <>
            {empty && (
              <div className="msg msg--bot">
                <div className="bubble">
                  <Markdown>{GREETING}</Markdown>
                </div>
              </div>
            )}

            {messages.map((m) => (
              <div
                key={m.id}
                className={`msg msg--${m.role}${m.error ? ' msg--error' : ''}`}
              >
                <div className="bubble">
                  {m.role === 'bot' && !m.error ? (
                    <Markdown>{m.text}</Markdown>
                  ) : (
                    m.text
                  )}
                </div>
                {m.tools && <ToolChips tools={m.tools} />}
              </div>
            ))}
          </>
        )}

        {busy && (
          <div className="msg msg--bot">
            <div className="bubble">
              <span className="dots" role="status" aria-label="Thinking">
                <i />
                <i />
                <i />
              </span>
            </div>
          </div>
        )}
      </div>

      {empty && (
        <div className="chat__suggestions">
          {SUGGESTIONS.map((s) => (
            <button
              key={s}
              className="suggestion"
              disabled={busy}
              onClick={() => submit(s)}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      <form
        className="chat__form"
        onSubmit={(e) => {
          e.preventDefault()
          submit(draft)
        }}
      >
        <textarea
          ref={taRef}
          className="chat__input scroll-thin"
          rows={1}
          placeholder="Ask about a course, an instructor, a time slot…"
          value={draft}
          disabled={busy}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit(draft)
            }
          }}
        />
        <button
          className="send"
          type="submit"
          disabled={busy || !draft.trim()}
          aria-label="Send"
        >
          <SendIcon />
        </button>
      </form>
      <p className="hint">Enter to send · Shift+Enter for a new line · saved to your account</p>
    </aside>
  )
}
