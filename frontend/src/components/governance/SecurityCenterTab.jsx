import React, { useState, useEffect } from 'react'
import axios from 'axios'

export default function SecurityCenterTab({ onNotify }) {
  const [summary, setSummary] = useState(null)
  const [execOverview, setExecOverview] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    fetchSecurityData()
  }, [])

  const fetchSecurityData = async () => {
    setLoading(true)
    try {
      const [secRes, execRes] = await Promise.all([
        axios.get('/api/governance/security-center/summary'),
        axios.get('/api/governance/executive-overview')
      ])
      setSummary(secRes.data)
      setExecOverview(execRes.data)
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to fetch security posture summary.', 'error')
    } finally {
      setLoading(false)
    }
  }

  const getStatusClass = (status) => {
    const s = (status || '').toLowerCase()
    if (s === 'connected' || s === 'configured') return 'status-connected'
    if (s === 'connection_failed' || s === 'failed') return 'status-failed'
    return 'status-not_configured'
  }

  if (loading && !summary) {
    return (
      <div className="gov-tab-content" style={{ textAlign: 'center', padding: '4rem', color: '#64748b' }}>
        Introspecting platform security posture and governance telemetry…
      </div>
    )
  }

  const kpis = summary?.kpis || {}
  const auth = summary?.authentication || {}
  const rbac = summary?.rbac || {}
  const db = summary?.database || {}
  const ollama = summary?.ollama || {}
  const smtp = summary?.smtp || {}
  const audit = summary?.audit || {}
  const execMetrics = execOverview?.metrics || {}

  return (
    <div className="gov-tab-content">
      {/* Title & Refresh Control */}
      <div className="gov-controls-bar">
        <div>
          <h3 style={{ margin: 0, fontSize: '1rem', color: '#f8fafc' }}>
            Executive Security &amp; Governance Center
          </h3>
          <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.8rem', color: '#94a3b8' }}>
            Real-time platform health, zero-trust RBAC telemetry, and executive governance indicators.
          </p>
        </div>

        <button className="btn-gov-secondary" onClick={fetchSecurityData} disabled={loading}>
          <span>🔄</span> Refresh Status
        </button>
      </div>

      {/* Security KPIs Banner */}
      <div className="kpis-banner">
        <div className="kpi-widget">
          <span className="kpi-label">Active Users</span>
          <span className="kpi-val" style={{ fontSize: '1.5rem', fontWeight: 700, color: '#34d399' }}>
            {kpis.active_accounts ?? '—'}
          </span>
          <span style={{ fontSize: '0.72rem', color: '#64748b' }}>of {kpis.total_accounts || 0} total</span>
        </div>

        <div className="kpi-widget">
          <span className="kpi-label">Locked Accounts</span>
          <span className="kpi-val" style={{ fontSize: '1.5rem', fontWeight: 700, color: kpis.locked_accounts > 0 ? '#f87171' : '#f8fafc' }}>
            {kpis.locked_accounts ?? '0'}
          </span>
          <span style={{ fontSize: '0.72rem', color: '#64748b' }}>brute-force lock</span>
        </div>

        <div className="kpi-widget">
          <span className="kpi-label">MFA Adoption</span>
          <span className="kpi-val" style={{ fontSize: '1.5rem', fontWeight: 700, color: '#38bdf8' }}>
            {kpis.mfa_adoption_pct ?? '0'}%
          </span>
          <span style={{ fontSize: '0.72rem', color: '#64748b' }}>user enrollment</span>
        </div>

        <div className="kpi-widget">
          <span className="kpi-label">Failed Logins (24h)</span>
          <span className="kpi-val" style={{ fontSize: '1.5rem', fontWeight: 700, color: kpis.failed_logins_24h > 0 ? '#fbbf24' : '#f8fafc' }}>
            {kpis.failed_logins_24h ?? '0'}
          </span>
          <span style={{ fontSize: '0.72rem', color: '#64748b' }}>monitored attempts</span>
        </div>

        <div className="kpi-widget">
          <span className="kpi-label">Control Pass Rate</span>
          <span className="kpi-val" style={{ fontSize: '1.5rem', fontWeight: 700, color: '#a855f7' }}>
            {execMetrics.control_pass_rate != null ? `${execMetrics.control_pass_rate}%` : 'N/A'}
          </span>
          <span style={{ fontSize: '0.72rem', color: '#64748b' }}>{execMetrics.total_executions || 0} evaluated</span>
        </div>
      </div>

      {/* Core Health Cards Grid */}
      <div className="sec-cards-grid">
        {/* Authentication Card */}
        <div className="sec-card">
          <div className="sec-card-header">
            <span className="sec-card-title">🔐 Authentication</span>
            <span className="sec-status-pill status-connected">ACTIVE</span>
          </div>
          <div className="sec-card-body">
            <div className="sec-stat-row">
              <span className="sec-stat-label">Mechanism:</span>
              <span className="sec-stat-val">{auth.token_type || 'JWT HS256'}</span>
            </div>
            <div className="sec-stat-row">
              <span className="sec-stat-label">Access Lifetime:</span>
              <span className="sec-stat-val">{auth.access_token_lifetime}</span>
            </div>
            <div className="sec-stat-row">
              <span className="sec-stat-label">Refresh Token:</span>
              <span className="sec-stat-val">{auth.refresh_token_lifetime}</span>
            </div>
            <div className="sec-stat-row">
              <span className="sec-stat-label">Force Logout:</span>
              <span className="sec-stat-val" style={{ color: '#34d399' }}>✓ Enabled (token_version)</span>
            </div>
          </div>
        </div>

        {/* RBAC Card */}
        <div className="sec-card">
          <div className="sec-card-header">
            <span className="sec-card-title">🛡️ Fine-Grained RBAC</span>
            <span className="sec-status-pill status-connected">ENFORCED</span>
          </div>
          <div className="sec-card-body">
            <div className="sec-stat-row">
              <span className="sec-stat-label">Standard Roles:</span>
              <span className="sec-stat-val">3 (Admin, Architect, Viewer)</span>
            </div>
            <div className="sec-stat-row">
              <span className="sec-stat-label">Custom Roles:</span>
              <span className="sec-stat-val" style={{ color: '#38bdf8' }}>{rbac.custom_roles} active</span>
            </div>
            <div className="sec-stat-row">
              <span className="sec-stat-label">Enterprise Permissions:</span>
              <span className="sec-stat-val">{rbac.standard_permissions} across 8 domains</span>
            </div>
            <div className="sec-stat-row">
              <span className="sec-stat-label">Matrix Configurable:</span>
              <span className="sec-stat-val">✓ Runtime Sync</span>
            </div>
          </div>
        </div>

        {/* Database Card */}
        <div className="sec-card">
          <div className="sec-card-header">
            <span className="sec-card-title">🗄️ PostgreSQL Database</span>
            <span className={`sec-status-pill ${getStatusClass(db.status)}`}>
              {db.status || 'UNKNOWN'}
            </span>
          </div>
          <div className="sec-card-body">
            <div className="sec-stat-row">
              <span className="sec-stat-label">Engine:</span>
              <span className="sec-stat-val">{db.type}</span>
            </div>
            <div className="sec-stat-row">
              <span className="sec-stat-label">Connection Latency:</span>
              <span className="sec-stat-val">{db.latency_ms ? `${db.latency_ms} ms` : '—'}</span>
            </div>
            <div className="sec-stat-row">
              <span className="sec-stat-label">Schema Migrations:</span>
              <span className="sec-stat-val" style={{ color: '#34d399' }}>✓ Runtime Synchronized</span>
            </div>
          </div>
        </div>

        {/* Ollama AI Card */}
        <div className="sec-card">
          <div className="sec-card-header">
            <span className="sec-card-title">🤖 Local Ollama LLM</span>
            <span className={`sec-status-pill ${getStatusClass(ollama.status)}`}>
              {ollama.status || 'UNKNOWN'}
            </span>
          </div>
          <div className="sec-card-body">
            <div className="sec-stat-row">
              <span className="sec-stat-label">Configured Model:</span>
              <span className="sec-stat-val" style={{ color: '#38bdf8' }}>{ollama.configured_model}</span>
            </div>
            <div className="sec-stat-row">
              <span className="sec-stat-label">Service Latency:</span>
              <span className="sec-stat-val">{ollama.latency_ms ? `${ollama.latency_ms} ms` : '—'}</span>
            </div>
            <div className="sec-stat-row">
              <span className="sec-stat-label">Direct DB Access:</span>
              <span className="sec-stat-val" style={{ color: '#34d399' }}>🛡️ Prohibited (Backend Isolated)</span>
            </div>
          </div>
        </div>

        {/* SMTP Card */}
        <div className="sec-card">
          <div className="sec-card-header">
            <span className="sec-card-title">📧 Email Alerting Engine</span>
            <span className={`sec-status-pill ${getStatusClass(smtp.status)}`}>
              {smtp.status || 'UNKNOWN'}
            </span>
          </div>
          <div className="sec-card-body">
            <div className="sec-stat-row">
              <span className="sec-stat-label">Host Configured:</span>
              <span className="sec-stat-val">{smtp.host_configured ? 'Configured' : 'Not Configured'}</span>
            </div>
            <div className="sec-stat-row">
              <span className="sec-stat-label">Transport Security:</span>
              <span className="sec-stat-val">{smtp.security?.toUpperCase() || 'STARTTLS'}</span>
            </div>
            <p style={{ fontSize: '0.72rem', color: '#64748b', margin: '0.2rem 0 0 0' }}>
              {smtp.delivery_guarantee}
            </p>
          </div>
        </div>

        {/* Audit Center Card */}
        <div className="sec-card">
          <div className="sec-card-header">
            <span className="sec-card-title">📜 Immutable Audit Center</span>
            <span className="sec-status-pill status-connected">ACTIVE</span>
          </div>
          <div className="sec-card-body">
            <div className="sec-stat-row">
              <span className="sec-stat-label">Append-Only Immutability:</span>
              <span className="sec-stat-val" style={{ color: '#34d399' }}>✓ Enforced via ORM</span>
            </div>
            <div className="sec-stat-row">
              <span className="sec-stat-label">Total Audit Events:</span>
              <span className="sec-stat-val">{audit.total_events || 0} events</span>
            </div>
            <div className="sec-stat-row">
              <span className="sec-stat-label">24h Event Volume:</span>
              <span className="sec-stat-val" style={{ color: '#38bdf8' }}>{audit.events_last_24h || 0}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Executive Overview Foundation */}
      <div className="sec-card" style={{ marginTop: '0.5rem' }}>
        <div className="sec-card-header">
          <span className="sec-card-title">📊 Executive Governance Overview (Real Telemetry)</span>
          <span style={{ fontSize: '0.76rem', color: '#94a3b8' }}>Live PostgreSQL Stats</span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '0.75rem', padding: '0.5rem 0' }}>
          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '0.75rem', borderRadius: 8 }}>
            <span style={{ fontSize: '0.72rem', color: '#94a3b8', textTransform: 'uppercase' }}>Workspaces / Projects</span>
            <div style={{ fontSize: '1.35rem', fontWeight: 700, color: '#f8fafc' }}>{execMetrics.projects_count || 0}</div>
          </div>

          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '0.75rem', borderRadius: 8 }}>
            <span style={{ fontSize: '0.72rem', color: '#94a3b8', textTransform: 'uppercase' }}>HLA Document Specs</span>
            <div style={{ fontSize: '1.35rem', fontWeight: 700, color: '#f8fafc' }}>{execMetrics.hla_documents_count || 0}</div>
          </div>

          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '0.75rem', borderRadius: 8 }}>
            <span style={{ fontSize: '0.72rem', color: '#94a3b8', textTransform: 'uppercase' }}>Active Controls</span>
            <div style={{ fontSize: '1.35rem', fontWeight: 700, color: '#f8fafc' }}>{execMetrics.controls_count || 0}</div>
          </div>

          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '0.75rem', borderRadius: 8 }}>
            <span style={{ fontSize: '0.72rem', color: '#94a3b8', textTransform: 'uppercase' }}>Open Exceptions</span>
            <div style={{ fontSize: '1.35rem', fontWeight: 700, color: '#f87171' }}>{execMetrics.open_exceptions_count || 0}</div>
          </div>
        </div>

        {/* Recent Governance Timeline Preview */}
        {execOverview?.recent_governance_activity && execOverview.recent_governance_activity.length > 0 && (
          <div style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '0.75rem' }}>
            <span style={{ fontSize: '0.78rem', fontWeight: 600, color: '#94a3b8', display: 'block', marginBottom: '0.5rem' }}>
              Recent Platform Governance Events
            </span>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem' }}>
              {execOverview.recent_governance_activity.slice(0, 4).map((g) => (
                <div
                  key={g.id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    fontSize: '0.76rem',
                    padding: '0.35rem 0.6rem',
                    background: 'rgba(255,255,255,0.02)',
                    borderRadius: 6
                  }}
                >
                  <span style={{ color: '#cbd5e1' }}>
                    <strong style={{ color: '#38bdf8' }}>{g.username}</strong> performed <code style={{ color: '#fbbf24' }}>{g.action}</code> on {g.resource_type}
                  </span>
                  <span style={{ color: '#64748b' }}>{new Date(g.timestamp).toLocaleTimeString()}</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
