import React, { useState, useEffect } from 'react'
import api from '../services/api'
import './SMTPSettingsModal.css'

export default function SMTPSettingsModal({ onClose, currentUser, defaultEmail }) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const fallbackEmail = defaultEmail || currentUser?.email || 'ganesh.raman@analytixhub.ai'
  const [testEmail, setTestEmail] = useState(fallbackEmail)
  const [testResult, setTestResult] = useState(null)
  const [statusMessage, setStatusMessage] = useState(null)
  const [showPassword, setShowPassword] = useState(false)
  const [showCustomSMTP, setShowCustomSMTP] = useState(false)

  const [formData, setFormData] = useState({
    host: '',
    port: 587,
    user: '',
    password: '',
    security: 'starttls',
    from_email: '',
    has_password: false,
    is_configured: false
  })

  // Load existing configuration
  useEffect(() => {
    const fetchSettings = async () => {
      setLoading(true)
      try {
        const res = await api.get('/api/settings/smtp')
        const data = res.data || {}
        setFormData((prev) => ({
          ...prev,
          ...data,
          password: ''
        }))
        if (data.from_email && !testEmail) {
          setTestEmail(data.from_email)
        } else if (fallbackEmail) {
          setTestEmail(fallbackEmail)
        }
        if (data.host && data.host !== 'localhost') {
          setShowCustomSMTP(true)
        }
      } catch (err) {
        console.error('Could not fetch settings:', err)
      } finally {
        setLoading(false)
      }
    }
    fetchSettings()
  }, [fallbackEmail])

  // Save Custom SMTP Settings (Optional)
  const handleSaveCustomSMTP = async (e) => {
    e?.preventDefault()
    setSaving(true)
    setStatusMessage(null)
    try {
      const payload = {
        host: formData.host.trim(),
        port: Number(formData.port),
        user: formData.user.trim(),
        security: formData.security,
        from_email: formData.from_email.trim()
      }
      if (formData.password) {
        payload.password = formData.password
      }
      const res = await api.post('/api/settings/smtp', payload)
      setFormData((prev) => ({
        ...prev,
        ...res.data.config,
        password: ''
      }))
      setStatusMessage({ type: 'success', text: '✓ Custom SMTP configuration saved successfully.' })
    } catch (err) {
      setStatusMessage({
        type: 'error',
        text: err.response?.data?.error || 'Failed to save custom SMTP configuration.'
      })
    } finally {
      setSaving(false)
    }
  }

  // Clear Custom SMTP to revert to Zero-Config Auto Engine
  const handleResetToAuto = async () => {
    setSaving(true)
    setStatusMessage(null)
    try {
      await api.post('/api/settings/smtp', {
        host: '',
        port: 587,
        user: '',
        password: '',
        security: 'starttls',
        from_email: ''
      })
      setFormData({
        host: '',
        port: 587,
        user: '',
        password: '',
        security: 'starttls',
        from_email: '',
        has_password: false,
        is_configured: false
      })
      setShowCustomSMTP(false)
      setStatusMessage({ type: 'success', text: '✓ Reverted to Zero-Config Auto-Dispatch Engine. No SMTP setup required!' })
    } catch (err) {
      setStatusMessage({ type: 'error', text: 'Failed to reset SMTP settings.' })
    } finally {
      setSaving(false)
    }
  }

  // Test Email Dispatch (Works with just email!)
  const handleSendTestEmail = async () => {
    if (!testEmail || !testEmail.includes('@')) {
      alert('Please enter a valid recipient email address (e.g. name@domain.com).')
      return
    }

    setTesting(true)
    setTestResult(null)
    try {
      const payload = {
        target_email: testEmail.trim()
      }
      // Only attach smtp_config if user explicitly configured a custom host
      if (formData.host && formData.host.trim() && showCustomSMTP) {
        payload.smtp_config = {
          host: formData.host.trim(),
          port: Number(formData.port),
          user: formData.user.trim(),
          password: formData.password || undefined,
          security: formData.security,
          from_email: formData.from_email.trim()
        }
      }

      const res = await api.post('/api/settings/smtp/test', payload)
      setTestResult({
        success: true,
        message: res.data.message || `✓ Test email alert successfully triggered and dispatched to ${testEmail}!`,
        delivery_mode: res.data.delivery_mode,
        preview: res.data.preview
      })
    } catch (err) {
      setTestResult({
        success: false,
        message: err.response?.data?.message || err.response?.data?.error || err.message
      })
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="modal-backdrop">
      <div className="modal-dialog glass-card email-center-dialog">
        <div className="modal-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '1.6rem' }}>📧</span>
            <div>
              <h3 style={{ margin: 0, fontSize: '1.45rem', fontWeight: 800, color: '#ffffff' }}>
                Automated Email Alerts & Test Center
              </h3>
              <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.96rem', color: 'var(--text-muted)' }}>
                Failure alerts are automatically triggered to your email. No complex server setup required!
              </p>
            </div>
          </div>
          <button className="btn-close" onClick={onClose} style={{ fontSize: '1.25rem' }}>✕</button>
        </div>

        {loading ? (
          <div style={{ padding: '3.5rem', textAlign: 'center', color: 'var(--cyan-400)', fontSize: '1.05rem' }}>
            Loading email alert status…
          </div>
        ) : (
          <div className="email-center-body">
            {statusMessage && (
              <div className={`email-alert-box ${statusMessage.type}`}>
                {statusMessage.text}
              </div>
            )}

            {/* ── Section 1: Zero-Config Direct Test Email Dispatch ── */}
            <div className="email-direct-card">
              <div className="email-direct-header">
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span style={{ fontSize: '1.35rem' }}>⚡</span>
                  <label className="email-main-label">
                    Enter Email Address to Trigger Test Mail:
                  </label>
                </div>
                <span className="email-mode-badge">
                  {formData.host && showCustomSMTP ? 'Custom SMTP Active' : 'Zero-Config Direct Delivery'}
                </span>
              </div>

              <p className="email-direct-hint">
                Just enter your email address below and click <strong>Send Test Email</strong>. The alerting engine will immediately construct and dispatch the failure notification.
              </p>

              <div className="email-test-action-row">
                <input
                  type="email"
                  value={testEmail}
                  onChange={(e) => setTestEmail(e.target.value)}
                  placeholder="Enter email e.g. ganesh.raman@analytixhub.ai"
                  className="form-control email-big-input"
                />
                <button
                  type="button"
                  className="btn-send-test-email"
                  onClick={handleSendTestEmail}
                  disabled={testing}
                >
                  {testing ? (
                    <>
                      <span className="spinner-inline" />
                      <span>Dispatching…</span>
                    </>
                  ) : (
                    <span>✉️ Send Test Email</span>
                  )}
                </button>
              </div>

              {testResult && (
                <div className={`test-feedback-box ${testResult.success ? 'success' : 'error'}`}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontWeight: 700, fontSize: '1.05rem' }}>
                    <span>{testResult.success ? '✓' : '✕'}</span>
                    <span>{testResult.message}</span>
                  </div>
                  {testResult.delivery_mode && (
                    <div style={{ marginTop: '0.35rem', fontSize: '0.94rem', color: '#cbd5e1' }}>
                      Delivery Mode: <strong>{testResult.delivery_mode}</strong>
                    </div>
                  )}
                  {testResult.preview && (
                    <div className="email-preview-card">
                      <div className="preview-row">
                        <strong>Subject:</strong> <span>{testResult.preview.subject}</span>
                      </div>
                      <div className="preview-row">
                        <strong>Recipient:</strong> <span>{testResult.preview.to}</span>
                      </div>
                      <div className="preview-row">
                        <strong>Timestamp:</strong> <span>{testResult.preview.sent_at}</span>
                      </div>
                      <pre className="preview-body">{testResult.preview.body_text}</pre>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* ── Section 2: Instructions on Schedule Alerts ── */}
            <div className="email-guide-box">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.35rem' }}>
                <span style={{ fontSize: '1.25rem' }}>🔔</span>
                <strong style={{ color: '#ffffff', fontSize: '1.02rem' }}>
                  How Automated Failure Alerts Work on Scheduled Runs:
                </strong>
              </div>
              <ul className="email-guide-list">
                <li>
                  When creating or editing a schedule in the <strong>Control Scheduler</strong>, simply enter recipient emails in the <strong>"Alert Recipient Emails"</strong> field.
                </li>
                <li>
                  If the control fails, or if upstream database tables have not arrived on time, an alert email is <strong>automatically triggered</strong> to all designated emails with full table audit diagnostics.
                </li>
                <li>
                  <strong>No SMTP setup is required!</strong> Everyone can simply enter their email address and alerts are dispatched.
                </li>
              </ul>
            </div>

            {/* ── Section 3: Collapsible Advanced Custom SMTP (Optional for Enterprises) ── */}
            <div className="advanced-smtp-section">
              <button
                type="button"
                className="btn-toggle-advanced"
                onClick={() => setShowCustomSMTP(!showCustomSMTP)}
              >
                <span>{showCustomSMTP ? '▼' : '▶'}</span>
                <span>⚙️ Optional: Connect Custom Corporate SMTP Server (For Enterprise Networks)</span>
              </button>

              {showCustomSMTP && (
                <form onSubmit={handleSaveCustomSMTP} className="advanced-smtp-form">
                  <p style={{ margin: '0 0 0.85rem 0', fontSize: '0.94rem', color: '#94a3b8' }}>
                    If your enterprise requires routing emails through a specific corporate mail relay, enter your server details below. Otherwise, you can leave this blank.
                  </p>

                  <div style={{ display: 'flex', gap: '0.5rem', marginBottom: '1rem', alignItems: 'center' }}>
                    <span style={{ fontSize: '0.88rem', color: '#94a3b8' }}>Quick Presets:</span>
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ padding: '0.25rem 0.65rem', fontSize: '0.84rem' }}
                      onClick={() => setFormData((prev) => ({
                        ...prev,
                        host: 'smtp.gmail.com',
                        port: 587,
                        security: 'starttls'
                      }))}
                    >
                      Gmail (587 STARTTLS)
                    </button>
                    <button
                      type="button"
                      className="btn-secondary"
                      style={{ padding: '0.25rem 0.65rem', fontSize: '0.84rem' }}
                      onClick={() => setFormData((prev) => ({
                        ...prev,
                        host: 'smtp.office365.com',
                        port: 587,
                        security: 'starttls'
                      }))}
                    >
                      Outlook / Office 365 (587)
                    </button>
                  </div>

                  <div className="form-row-2col">
                    <div className="form-group">
                      <label className="form-field-label">SMTP Server Host</label>
                      <input
                        type="text"
                        value={formData.host}
                        onChange={(e) => setFormData({ ...formData, host: e.target.value })}
                        placeholder="e.g. smtp.office365.com or smtp.gmail.com"
                        className="form-control"
                      />
                    </div>
                    <div className="form-group">
                      <label className="form-field-label">Port</label>
                      <input
                        type="number"
                        value={formData.port}
                        onChange={(e) => setFormData({ ...formData, port: e.target.value })}
                        placeholder="587 or 465"
                        className="form-control"
                      />
                    </div>
                  </div>

                  <div className="form-row-2col">
                    <div className="form-group">
                      <label className="form-field-label">Security</label>
                      <select
                        value={formData.security}
                        onChange={(e) => setFormData({ ...formData, security: e.target.value })}
                        className="form-control"
                      >
                        <option value="starttls">STARTTLS (Port 587 - Standard)</option>
                        <option value="ssl">SSL / TLS (Port 465 - Direct)</option>
                        <option value="none">None (Plaintext Relay)</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label className="form-field-label">Sender Email (From)</label>
                      <input
                        type="email"
                        value={formData.from_email}
                        onChange={(e) => setFormData({ ...formData, from_email: e.target.value })}
                        placeholder="alerts@yourdomain.com"
                        className="form-control"
                      />
                    </div>
                  </div>

                  <div className="form-row-2col">
                    <div className="form-group">
                      <label className="form-field-label">SMTP Username</label>
                      <input
                        type="text"
                        value={formData.user}
                        onChange={(e) => setFormData({ ...formData, user: e.target.value })}
                        placeholder="user@domain.com"
                        className="form-control"
                      />
                    </div>
                    <div className="form-group">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <label className="form-field-label">
                          Password {formData.has_password && <span style={{ color: '#34d399' }}>(Saved ✓)</span>}
                        </label>
                        <button
                          type="button"
                          style={{ background: 'none', border: 'none', color: '#38bdf8', fontSize: '0.88rem', cursor: 'pointer' }}
                          onClick={() => setShowPassword(!showPassword)}
                        >
                          {showPassword ? 'Hide' : 'Show'}
                        </button>
                      </div>
                      <input
                        type={showPassword ? 'text' : 'password'}
                        value={formData.password}
                        onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                        placeholder={formData.has_password ? 'Leave empty to keep saved' : 'Enter password'}
                        className="form-control"
                      />
                    </div>
                  </div>

                  <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'flex-end', marginTop: '0.85rem' }}>
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={handleResetToAuto}
                      disabled={saving}
                      style={{ fontSize: '0.94rem' }}
                    >
                      Clear & Use Auto-Engine
                    </button>
                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={saving}
                      style={{ fontSize: '0.96rem' }}
                    >
                      {saving ? 'Saving...' : 'Save Custom SMTP'}
                    </button>
                  </div>
                </form>
              )}
            </div>

            <div className="modal-footer" style={{ marginTop: '1.25rem', paddingTop: '1rem' }}>
              <button
                type="button"
                className="btn-primary"
                onClick={onClose}
                style={{ fontSize: '1rem', padding: '0.65rem 1.6rem' }}
              >
                Done
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
