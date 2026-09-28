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
        `Hello ${currentUser?.username || 'Architect'}! I am your **HLA Studio AI Assistant**.\n\n` +
        `The uploaded document and active workspace are my authoritative ground truth. ` +
        `I can help you inspect source datasets, analyze business rules, diagnose execution logs, ` +
        `and explain generic architecture patterns.\n\n` +
        `How can I assist you today?`,
      timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
      context_used: false,
    },
  ])
  const [inputMessage, setInputMessage] = useState('')
  const [loading, setLoading] = useState(false)
  const [copiedIndex, setCopiedIndex] = useState(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [showSettings, setShowSettings] = useState(false)

  // AI Provider Status
  const [aiStatus, setAiStatus] = useState({
    enabled: true,
    online: false,
    model: 'qwen3',
    model_available: false,
    ready: false,
    status: 'STARTING',
    active_provider: 'ollama',
    is_cloud: false,
    privacy_notice: 'Prompts and HLA data remain strictly local on your machine.',
    error: null,
    checking: true,
  })

  // Provider Settings State
  const [settingsForm, setSettingsForm] = useState({
    active_provider: 'ollama',
    ollama_model: 'qwen3:latest',
    ollama_base_url: 'http://127.0.0.1:11434',
    api_provider_type: 'openai',
    api_model: 'gpt-4o-mini',
    api_key: '',
    api_base_url: '',
    has_api_key: false,
  })

  const [testingConnection, setTestingConnection] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [savingSettings, setSavingSettings] = useState(false)
  const [saveSuccessMsg, setSaveSuccessMsg] = useState('')

  const messagesEndRef = useRef(null)
  const textareaRef = useRef(null)

  // Fetch status and config
  const checkStatus = async () => {
    try {
      const res = await api.get('/api/ai/status')
      const data = res.data || {}
      setAiStatus({
        enabled: data.enabled !== false,
        online: Boolean(data.online),
        model: data.model || 'qwen3',
        model_available: Boolean(data.model_available),
        ready: Boolean(data.ready),
        status: data.status || (data.ready ? 'READY' : 'OFFLINE'),
        active_provider: data.active_provider || 'ollama',
        is_cloud: Boolean(data.is_cloud),
        privacy_notice: data.privacy_notice || '',
        error: data.error || null,
        checking: false,
      })
      return data.status
    } catch (err) {
      setAiStatus((prev) => ({
        ...prev,
        online: false,
        ready: false,
        status: 'OFFLINE',
        error: 'AI service is unreachable.',
        checking: false,
      }))
      return 'OFFLINE'
    }
  }

  const loadConfig = async () => {
    try {
      const res = await api.get('/api/ai/config')
      const cfg = res.data || {}
      setSettingsForm({
        active_provider: cfg.active_provider || 'ollama',
        ollama_model: cfg.ollama?.model || 'qwen3:latest',
        ollama_base_url: cfg.ollama?.base_url || 'http://127.0.0.1:11434',
        api_provider_type: cfg.api?.provider_type || 'openai',
        api_model: cfg.api?.model || 'gpt-4o-mini',
        api_key: '',
        api_base_url: cfg.api?.base_url || '',
        has_api_key: Boolean(cfg.api?.has_api_key),
      })
    } catch (err) {
      console.warn('Failed to load AI configuration', err)
    }
  }

  useEffect(() => {
    if (!isOpen) return

    if (textareaRef.current) {
      textareaRef.current.focus()
    }

    checkStatus()
    loadConfig()

    let pollCount = 0
    const maxPolls = 30
    const intervalId = setInterval(async () => {
      pollCount += 1
      const currentStatus = await checkStatus()
      if (currentStatus === 'READY' || pollCount >= maxPolls) {
        clearInterval(intervalId)
      }
    }, 2500)

    return () => clearInterval(intervalId)
  }, [isOpen])

  // Scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Status badge display
  const getStatusDisplay = () => {
    const isCloud = aiStatus.is_cloud
    const model = aiStatus.model || 'qwen3'
    const status = aiStatus.status

    if (isCloud) {
      if (aiStatus.ready) {
        return {
          badgeClass: 'online cloud',
          label: `☁️ Cloud API — ${model} Ready`,
        }
      }
      return {
        badgeClass: 'offline',
        label: `☁️ API Provider — ${status}`,
      }
    }

    switch (status) {
      case 'STARTING':
        return { badgeClass: 'starting', label: 'Starting local Ollama…' }
      case 'OFFLINE':
        return { badgeClass: 'offline', label: 'Local Ollama Offline' }
      case 'ONLINE':
        return { badgeClass: 'starting', label: `Ollama Online — Checking ${model}…` }
      case 'MODEL_MISSING':
        return { badgeClass: 'offline', label: `Ollama Online — ${model} not installed` }
      case 'PULLING':
        return { badgeClass: 'pulling', label: `Downloading ${model}…` }
      case 'READY':
        return { badgeClass: 'online', label: `🟢 Local Ollama — ${model} Ready` }
      default:
        return { badgeClass: 'offline', label: 'AI Offline' }
    }
  }

  // Handle Test Connection
  const handleTestConnection = async () => {
    setTestingConnection(true)
    setTestResult(null)
    try {
      const payload = {
        provider_type: settingsForm.active_provider,
        model: settingsForm.active_provider === 'ollama' ? settingsForm.ollama_model : settingsForm.api_model,
        base_url: settingsForm.active_provider === 'ollama' ? settingsForm.ollama_base_url : settingsForm.api_base_url,
        api_key: settingsForm.api_key || undefined,
      }
      const res = await api.post('/api/ai/test', payload)
      setTestResult({
        success: true,
        message: `Connected successfully to ${payload.model} (${res.data?.status || 'READY'})`,
      })
    } catch (err) {
      setTestResult({
        success: false,
        message: err.response?.data?.error || 'Connection failed. Please verify provider settings and network access.',
      })
    } finally {
      setTestingConnection(false)
    }
  }

  // Handle Save Settings
  const handleSaveSettings = async () => {
    setSavingSettings(true)
    setSaveSuccessMsg('')
    try {
      const payload = {
        active_provider: settingsForm.active_provider,
        ollama: {
          model: settingsForm.ollama_model,
          base_url: settingsForm.ollama_base_url,
        },
        api: {
          provider_type: settingsForm.api_provider_type,
          model: settingsForm.api_model,
          base_url: settingsForm.api_base_url,
          api_key: settingsForm.api_key,
        },
      }
      await api.post('/api/ai/config', payload)
      setSaveSuccessMsg('AI Provider configuration saved successfully!')
      await checkStatus()
      await loadConfig()
      setTimeout(() => setSaveSuccessMsg(''), 3000)
    } catch (err) {
      setErrorMsg(err.response?.data?.error || 'Failed to save configuration.')
    } finally {
      setSavingSettings(false)
    }
  }

  // Handle Send Message
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

    const updatedMessages = [...messages, userMsg]
    setMessages(updatedMessages)
    setLoading(true)

    try {
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
            intent: res.data.intent,
            provider: res.data.provider,
            model: res.data.model,
            is_cloud: res.data.is_cloud,
            timestamp: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
          },
        ])
      } else {
        setErrorMsg(res.data?.error || 'Failed to receive a response from AI.')
      }
    } catch (err) {
      const serverErr =
        err.response?.data?.error ||
        (err.response?.status === 429
          ? 'Rate limit exceeded. Please wait a moment.'
          : aiStatus.is_cloud
          ? 'API connection failed. Check the API key and provider settings.'
          : 'Local Ollama is unavailable. Start Ollama or select an API provider.')
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
        content: `Session chat history cleared. Document-driven ground truth is active!`,
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

  // Generic Document-Driven Suggestions
  const promptPills = activeDoc
    ? [
        `Summarize ${activeDoc.original_name || 'uploaded document'}`,
        'What source tables are defined?',
        'Show business and reconciliation rules',
        'Why did execution fail?',
      ]
    : [
        'Explain HLA Studio capabilities',
        'Summarize this workspace',
        'What are HLA generic target principles?',
        'How does reconciliation work?',
      ]

  if (!isOpen) return null

  const statusDisplay = getStatusDisplay()

  return (
    <div className="hla-ai-overlay" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <aside className="hla-ai-drawer" aria-label="HLA AI Assistant Drawer">
        {/* ── Drawer Header ── */}
        <div className="ai-drawer-header">
          <div className="ai-header-brand">
            <div className="ai-beacon-avatar">
              <span className="ai-beacon-sparkle">✨</span>
              <span className={`ai-beacon-dot ${statusDisplay.badgeClass}`} />
            </div>
            <div className="ai-title-group">
              <div className="ai-title-row">
                <h3>HLA AI Assistant</h3>
                <span className={`ai-provider-badge ${aiStatus.is_cloud ? 'cloud' : 'local'}`}>
                  {aiStatus.is_cloud ? 'Cloud API' : 'Local Ollama'}
                </span>
                <span className="ai-model-tag" title="Active Model">
                  {aiStatus.model}
                </span>
              </div>
              <span className="ai-status-sub">{statusDisplay.label}</span>
            </div>
          </div>

          <div className="ai-header-actions">
            <button
              className={`btn-ai-header-action ${showSettings ? 'active' : ''}`}
              onClick={() => setShowSettings(!showSettings)}
              title="Configure AI Provider & Models"
              aria-label="AI Settings"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <circle cx="12" cy="12" r="3" />
                <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
              </svg>
            </button>
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
              title="Close Assistant"
              aria-label="Close Assistant"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
        </div>

        {/* ── Privacy & Cloud Notice Banner ── */}
        {aiStatus.is_cloud ? (
          <div className="ai-privacy-notice cloud">
            <span>☁️ External Provider Active: AI requests are processed by the configured external model.</span>
          </div>
        ) : (
          <div className="ai-privacy-notice local">
            <span>🔒 Local-First Mode: Prompts and HLA metadata remain completely local on your machine.</span>
          </div>
        )}

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
              <span className="context-label">Source Document:</span>
              <span className="context-value">{activeDoc.original_name}</span>
            </div>
          )}
        </div>

        {/* ── Provider Settings Modal Panel (Collapsible) ── */}
        {showSettings && (
          <div className="ai-settings-panel">
            <div className="ai-settings-header">
              <h4>⚙️ AI Provider Settings</h4>
              <button className="btn-close-settings" onClick={() => setShowSettings(false)}>✕</button>
            </div>

            <div className="settings-field">
              <label className="field-label">AI Provider:</label>
              <div className="provider-toggle-group">
                <button
                  type="button"
                  className={`btn-provider-toggle ${settingsForm.active_provider === 'ollama' ? 'selected' : ''}`}
                  onClick={() => setSettingsForm({ ...settingsForm, active_provider: 'ollama' })}
                >
                  🟢 Local Ollama (Default)
                </button>
                <button
                  type="button"
                  className={`btn-provider-toggle ${settingsForm.active_provider === 'api' ? 'selected' : ''}`}
                  onClick={() => setSettingsForm({ ...settingsForm, active_provider: 'api' })}
                >
                  ☁️ API Provider (Cloud)
                </button>
              </div>
            </div>

            {settingsForm.active_provider === 'ollama' ? (
              <div className="provider-sub-form">
                <div className="settings-field">
                  <label className="field-label">Model Name:</label>
                  <input
                    type="text"
                    className="ai-settings-input"
                    value={settingsForm.ollama_model}
                    onChange={(e) => setSettingsForm({ ...settingsForm, ollama_model: e.target.value })}
                    placeholder="qwen3:latest"
                  />
                  <span className="field-hint">Default is qwen3. Requires no external API keys.</span>
                </div>
                <div className="settings-field">
                  <label className="field-label">Ollama Host URL:</label>
                  <input
                    type="text"
                    className="ai-settings-input"
                    value={settingsForm.ollama_base_url}
                    onChange={(e) => setSettingsForm({ ...settingsForm, ollama_base_url: e.target.value })}
                    placeholder="http://127.0.0.1:11434"
                  />
                </div>
              </div>
            ) : (
              <div className="provider-sub-form">
                <div className="settings-field">
                  <label className="field-label">Cloud Provider Type:</label>
                  <select
                    className="ai-settings-select"
                    value={settingsForm.api_provider_type}
                    onChange={(e) => setSettingsForm({ ...settingsForm, api_provider_type: e.target.value })}
                  >
                    <option value="openai">OpenAI (GPT-4o, GPT-4o-mini)</option>
                    <option value="anthropic">Anthropic (Claude 3.5 Sonnet)</option>
                    <option value="groq">Groq (Llama 3.3 70B)</option>
                    <option value="custom">Custom / OpenAI-Compatible</option>
                  </select>
                </div>
                <div className="settings-field">
                  <label className="field-label">Model Identifier:</label>
                  <input
                    type="text"
                    className="ai-settings-input"
                    value={settingsForm.api_model}
                    onChange={(e) => setSettingsForm({ ...settingsForm, api_model: e.target.value })}
                    placeholder="e.g. gpt-4o-mini, claude-3-5-sonnet-20241022"
                  />
                </div>
                <div className="settings-field">
                  <label className="field-label">
                    API Key: {settingsForm.has_api_key && <span className="key-configured-tag">✓ Configured</span>}
                  </label>
                  <input
                    type="password"
                    className="ai-settings-input"
                    value={settingsForm.api_key}
                    onChange={(e) => setSettingsForm({ ...settingsForm, api_key: e.target.value })}
                    placeholder={settingsForm.has_api_key ? '•••••••••••••••• (Leave blank to keep)' : 'Enter your API key'}
                  />
                  <span className="field-hint">Stored encrypted on backend. Never exposed to browser.</span>
                </div>
                <div className="settings-field">
                  <label className="field-label">Custom Endpoint URL (Optional):</label>
                  <input
                    type="text"
                    className="ai-settings-input"
                    value={settingsForm.api_base_url}
                    onChange={(e) => setSettingsForm({ ...settingsForm, api_base_url: e.target.value })}
                    placeholder="https://api.openai.com/v1"
                  />
                </div>
              </div>
            )}

            {testResult && (
              <div className={`test-feedback ${testResult.success ? 'success' : 'failure'}`}>
                {testResult.success ? '✓' : '⚠️'} {testResult.message}
              </div>
            )}

            {saveSuccessMsg && (
              <div className="test-feedback success">✓ {saveSuccessMsg}</div>
            )}

            <div className="settings-action-row">
              <button
                type="button"
                className="btn-test-conn"
                onClick={handleTestConnection}
                disabled={testingConnection}
              >
                {testingConnection ? 'Testing…' : 'Test Connection'}
              </button>
              <button
                type="button"
                className="btn-save-conn"
                onClick={handleSaveSettings}
                disabled={savingSettings}
              >
                {savingSettings ? 'Saving…' : 'Save Settings'}
              </button>
            </div>
          </div>
        )}

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
                    {msg.intent && (
                      <span className="intent-tag" title={`Parsed Intent: ${msg.intent}`}>
                        🎯 {msg.intent}
                      </span>
                    )}
                    {msg.context_used && (
                      <span className="grounded-tag" title="Grounded with extracted document metadata">
                        📄 Document Grounded
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

          {/* Thinking Spinner */}
          {loading && (
            <div className="ai-message-wrapper assistant">
              <div className="msg-avatar assistant">
                <span>AI</span>
              </div>
              <div className="ai-message-bubble loading-bubble">
                <div className="ai-thinking-indicator">
                  <div className="ai-dot-pulse" />
                  <span>
                    Consulting {aiStatus.is_cloud ? `cloud ${aiStatus.model}` : `local ${aiStatus.model}`} & analyzing document metadata…
                  </span>
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

        {/* ── Quick Prompt Pills ── */}
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
              placeholder="Ask about source tables, business rules, null values, or target architecture..."
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
            <span className="zero-trust-indicator">🔒 Generic Document Grounding</span>
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

    const paragraphs = part.split('\n\n')
    return (
      <div key={index} className="ai-text-block">
        {paragraphs.map((p, pIdx) => {
          const trimmed = p.trim()
          if (!trimmed) return null

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
  const boldParts = str.split(/(\*\*.*?\*\*)/g)
  return boldParts.map((bPart, bIdx) => {
    if (bPart.startsWith('**') && bPart.endsWith('**')) {
      return <strong key={bIdx}>{bPart.slice(2, -2)}</strong>
    }
    const codeParts = bPart.split(/(`.*?`)/g)
    return codeParts.map((cPart, cIdx) => {
      if (cPart.startsWith('`') && cPart.endsWith('`')) {
        return <code key={cIdx} className="ai-inline-code">{cPart.slice(1, -1)}</code>
      }
      return cPart
    })
  })
}
