import React, { useState, useEffect, useRef } from 'react'
import api from '../services/api'
import { copyToClipboard } from '../utils/clipboard'
import './HlaAiAssistant.css'

export default function HlaAiAssistant({
  isOpen,
  onClose,
  activeProject,
  activeDoc,
  currentUser,
}) {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        `Hello ${currentUser?.username || 'Architect'}! I am your **HLA Studio AI Assistant**, powered by local Ollama.\n\n` +
        `I can help you inspect controls, analyze execution logs, review R1–R15 rules, and explain enterprise reconciliation architectures.\n\n` +
        `How can I assist you today?`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      context_used: false,
    },
  ])
  const [inputMessage, setInputMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [aiStatus, setAiStatus] = useState({ available: false, model: 'qwen3', checking: true })
  const [copiedIndex, setCopiedIndex] = useState(null)
  const [errorMsg, setErrorMsg] = useState('')
  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)

  // Fetch local Ollama engine status on mount or when opened
  useEffect(() => {
    if (isOpen) {
      checkStatus()
      if (textareaRef.current) {
        textareaRef.current.focus()
      }
    }
  }, [isOpen])

  // Scroll to bottom on new message
  useEffect(() => {
    if (isOpen) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, loading, isOpen])

  const checkStatus = async () => {
    try {
      setAiStatus((prev) => ({ ...prev, checking: true }))
      const res = await api.get('/api/ai/status')
      setAiStatus({
        available: res.data.available,
        model: res.data.model || 'qwen3',
        error: res.data.error,
        checking: false,
      })
    } catch (err) {
      setAiStatus({
        available: false,
        model: 'qwen3',
        error: 'Ollama service is unreachable.',
        checking: false,
      })
    }
  }

  const handleSendMessage = async (textToSend = null) => {
    const query = (textToSend || inputMessage).trim()
    if (!query || loading) return

    setErrorMsg('')
    setInputMessage('')

    const userMsg = {
      role: 'user',
      content: query,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    }

    // Append user message immediately
    const updatedMessages = [...messages, userMsg]
    setMessages(updatedMessages)
    setLoading(true)

    try {
      // Build lightweight conversation history for the backend (last 6 items)
      const historyPayload = updatedMessages.slice(-6).map((m) => ({
        role: m.role,
        content: m.content,
      }))

      const res = await api.post('/api/ai/chat', {
        message: query,
        project_id: activeProject?.id || null,
        document_id: activeDoc?.id || null,
        history: historyPayload,
      })

      if (res.data && res.data.success) {
        setMessages((prev) => [
          ...prev,
          {
            role: 'assistant',
            content: res.data.response,
            context_used: Boolean(res.data.context_used),
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ])
      } else {
        setErrorMsg(res.data.error || 'Failed to receive a response from AI.')
      }
    } catch (err) {
      const serverErr =
        err.response?.data?.error ||
        (err.response?.status === 429
          ? 'Rate limit exceeded. Please wait a moment.'
          : 'AI service is currently unavailable. Please try again later.')
      setErrorMsg(serverErr)
    } finally {
      setLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendMessage()
    }
  }

  const handleClearChat = () => {
    setMessages([
      {
        role: 'assistant',
        content: `Session chat history cleared. Ready for your questions!`,
        timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        context_used: false,
      },
    ])
    setErrorMsg('')
  }

  const handleCopyText = async (text, idx) => {
    const success = await copyToClipboard(text)
    if (success) {
      setCopiedIndex(idx)
      setTimeout(() => setCopiedIndex(null), 2000)
    }
  }

  // Quick Prompt Pills
  const promptPills = [
    'Explain what HLA Studio does',
    'Explain Control 6',
    'Why did Control 6 fail?',
    'Summarize this project\'s controls',
  ]

  if (!isOpen) return null

  return (
    <div className="hla-ai-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="hla-ai-drawer" aria-label="HLA AI Assistant Drawer">
        {/* ── Drawer Header ── */}
        <div className="ai-drawer-header">
          <div className="ai-header-brand">
            <div className="ai-beacon-avatar">
              <span className="ai-beacon-sparkle">✨</span>
              <span className={`ai-beacon-dot ${aiStatus.available ? 'online' : 'offline'}`} />
            </div>
            <div className="ai-title-group">
              <div className="ai-title-row">
                <h3>HLA AI Assistant</h3>
                <span className="ai-model-tag" title="Configured local model">
                  {aiStatus.model}
                </span>
              </div>
              <span className="ai-status-sub">
                {aiStatus.checking
                  ? 'Checking local Ollama…'
                  : aiStatus.available
                  ? '● Local Ollama Connected'
                  : '○ Ollama Offline / Model Not Ready'}
              </span>
            </div>
          </div>

          <div className="ai-header-actions">
            <button
              className="btn-ai-header-action"
              onClick={handleClearChat}
              title="Reset conversation"
              aria-label="Clear chat"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <polyline points="3 6 5 6 21 6" />
                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
              </svg>
            </button>
            <button
              className="btn-ai-header-close"
              onClick={onClose}
              title="Close Assistant (Esc)"
              aria-label="Close Assistant"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </div>

        {/* ── Active Context Ribbon ── */}
        <div className="ai-context-ribbon">
          <div className="context-item">
            <span className="context-label">Role:</span>
            <span className={`role-badge ${currentUser?.role?.toLowerCase() || 'viewer'}`}>
              {currentUser?.role || 'Viewer'}
            </span>
          </div>
          {activeProject && (
            <div className="context-item" title={activeProject.name}>
              <span className="context-label">Workspace:</span>
              <span className="context-value">{activeProject.name}</span>
            </div>
          )}
          {activeDoc && (
            <div className="context-item" title={activeDoc.original_name}>
              <span className="context-label">Document:</span>
              <span className="context-value">{activeDoc.original_name}</span>
            </div>
          )}
        </div>

        {/* ── Message Stream ── */}
        <div className="ai-message-stream">
          {messages.map((msg, idx) => (
            <div key={idx} className={`ai-message-wrapper ${msg.role}`}>
              {msg.role === 'assistant' && (
                <div className="msg-avatar assistant">
                  <span>AI</span>
                </div>
              )}

              <div className="ai-message-bubble">
                <div className="msg-bubble-header">
                  <span className="msg-author">
                    {msg.role === 'assistant' ? 'HLA Copilot' : currentUser?.username || 'You'}
                  </span>
                  <div className="msg-header-right">
                    {msg.context_used && (
                      <span className="grounded-tag" title="Grounded with authorized PostgreSQL HLA data">
                        🎯 HLA Grounded
                      </span>
                    )}
                    <span className="msg-time">{msg.timestamp}</span>
                  </div>
                </div>

                <div className="msg-bubble-content">
                  {renderFormattedMarkdown(msg.content)}
                </div>

                {msg.role === 'assistant' && (
                  <div className="msg-bubble-actions">
                    <button
                      className="btn-msg-copy"
                      onClick={() => handleCopyText(msg.content, idx)}
                      title="Copy response"
                    >
                      {copiedIndex === idx ? '✓ Copied' : '📋 Copy'}
                    </button>
                  </div>
                )}
              </div>

              {msg.role === 'user' && (
                <div className="msg-avatar user">
                  <span>{(currentUser?.username || 'U').substring(0, 2).toUpperCase()}</span>
                </div>
              )}
            </div>
          ))}

          {/* Thinking / Spinner Indicator */}
          {loading && (
            <div className="ai-message-wrapper assistant">
              <div className="msg-avatar assistant">
                <span>AI</span>
              </div>
              <div className="ai-message-bubble loading-bubble">
                <div className="ai-thinking-indicator">
                  <div className="ai-dot-pulse" />
                  <span>Consulting local {aiStatus.model} & querying authorized records…</span>
                </div>
              </div>
            </div>
          )}

          {/* Error Banner */}
          {errorMsg && (
            <div className="ai-error-banner">
              <span className="error-icon">⚠️</span>
              <div className="error-text">
                <p>{errorMsg}</p>
                <button className="btn-error-retry" onClick={() => handleSendMessage()}>
                  Retry
                </button>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {/* ── Quick Prompt Chips ── */}
        <div className="ai-quick-prompts">
          <span className="quick-prompts-label">Suggestions:</span>
          <div className="quick-prompts-list">
            {promptPills.map((pill, i) => (
              <button
                key={i}
                className="btn-prompt-chip"
                onClick={() => handleSendMessage(pill)}
                disabled={loading}
              >
                {pill}
              </button>
            ))}
          </div>
        </div>

        {/* ── Message Input Bar ── */}
        <div className="ai-input-container">
          <div className="ai-input-wrap">
            <textarea
              ref={textareaRef}
              className="ai-textarea"
              placeholder="Ask about Control 6, execution status, architecture, or reconciliation rules..."
              value={inputMessage}
              onChange={(e) => setInputMessage(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={2}
              disabled={loading}
            />
            <button
              className="btn-ai-send"
              onClick={() => handleSendMessage()}
              disabled={loading || !inputMessage.trim()}
              title="Send question (Enter)"
              aria-label="Send message"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
          <div className="ai-input-footer">
            <span>Enter to send • Shift + Enter for new line</span>
            <span className="zero-trust-indicator">🔒 Zero-Trust RBAC Enforced</span>
          </div>
        </div>
      </aside>
    </div>
  )
}

/**
 * Lightweight helper to format markdown headers, code blocks, lists, and bold text.
 */
function renderFormattedMarkdown(text) {
  if (!text) return null

  // Split text by markdown code blocks (```...```)
  const parts = text.split(/(```[\s\S]*?```)/g)

  return parts.map((part, index) => {
    if (part.startsWith('```') && part.endsWith('```')) {
      const lines = part.slice(3, -3).trim().split('\n')
      const firstLine = lines[0].trim()
      const isLang = /^[a-zA-Z0-9_-]+$/.test(firstLine)
      const lang = isLang ? firstLine : ''
      const code = isLang ? lines.slice(1).join('\n') : lines.join('\n')

      return (
        <div key={index} className="ai-code-block-wrap">
          {lang && <div className="ai-code-lang">{lang}</div>}
          <pre className="ai-code-block">
            <code>{code}</code>
          </pre>
        </div>
      )
    }

    // Normal text lines
    const paragraphs = part.split('\n\n')
    return (
      <div key={index} className="ai-text-block">
        {paragraphs.map((p, pIdx) => {
          const trimmed = p.trim()
          if (!trimmed) return null

          // Bullet list
          if (trimmed.includes('\n• ') || trimmed.startsWith('• ') || trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
            const listItems = trimmed.split(/\n(?=[•\-\*]\s|\d+\.\s)/)
            return (
              <ul key={pIdx} className="ai-bullet-list">
                {listItems.map((li, liIdx) => (
                  <li key={liIdx}>
                    {renderInlineStyles(li.replace(/^[•\-\*]\s+|\d+\.\s+/, ''))}
                  </li>
                ))}
              </ul>
            )
          }

          // Headers
          if (trimmed.startsWith('### ')) {
            return <h4 key={pIdx} className="ai-md-h4">{renderInlineStyles(trimmed.replace(/^###\s+/, ''))}</h4>
          }
          if (trimmed.startsWith('## ')) {
            return <h3 key={pIdx} className="ai-md-h3">{renderInlineStyles(trimmed.replace(/^##\s+/, ''))}</h3>
          }
          if (trimmed.startsWith('# ')) {
            return <h2 key={pIdx} className="ai-md-h2">{renderInlineStyles(trimmed.replace(/^#\s+/, ''))}</h2>
          }

          return (
            <p key={pIdx} className="ai-md-p">
              {renderInlineStyles(trimmed)}
            </p>
          )
        })}
      </div>
    )
  })
}

function renderInlineStyles(str) {
  if (!str) return ''
  // Process bold: **text**
  const boldParts = str.split(/(\*\*.*?\*\*)/g)
  return boldParts.map((bPart, bIdx) => {
    if (bPart.startsWith('**') && bPart.endsWith('**')) {
      return <strong key={bIdx}>{bPart.slice(2, -2)}</strong>
    }
    // Inline code: `text`
    const codeParts = bPart.split(/(`.*?`)/g)
    return codeParts.map((cPart, cIdx) => {
      if (cPart.startsWith('`') && cPart.endsWith('`')) {
        return <code key={cIdx} className="ai-inline-code">{cPart.slice(1, -1)}</code>
      }
      return cPart
    })
  })
}
