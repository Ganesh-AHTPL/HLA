import React, { useState, useEffect } from 'react'
import api from '../services/api'
import { scheduleFormSchema } from '../schemas/scheduleSchema'
import SMTPSettingsModal from './SMTPSettingsModal'
import './ControlScheduler.css'

export default function ControlScheduler({ projectId, projectDocs = [], currentUser }) {
  const isViewer = currentUser?.role?.toLowerCase() === 'viewer'
  const [activeTab, setActiveTab] = useState('schedules') // 'schedules' | 'history'
  const [schedules, setSchedules] = useState([])
  const [history, setHistory] = useState([])
  const [loading, setLoading] = useState(true)
  const [runningScheduleId, setRunningScheduleId] = useState(null)
  const [selectedRunLog, setSelectedRunLog] = useState(null)
  const [statusFilter, setStatusFilter] = useState('ALL')

  // SMTP Settings Modal State
  const [showSMTPModal, setShowSMTPModal] = useState(false)

  // Manual Control Run Modal State
  const [showManualRunModal, setShowManualRunModal] = useState(false)
  const [manualRunData, setManualRunData] = useState({
    document_id: projectDocs[0]?.id || '',
    environment: 'dev',
    hostname: 'localhost'
  })
  const [triggeringManualRun, setTriggeringManualRun] = useState(false)

  // Modal State
  const [showModal, setShowModal] = useState(false)
  const [editingSchedule, setEditingSchedule] = useState(null)
  const [formData, setFormData] = useState({
    document_id: projectDocs[0]?.id || '',
    name: '',
    environment: 'dev',
    schedule_type: 'daily',
    run_time: '02:00',
    days_of_week: 'mon,tue,wed,thu,fri',
    day_of_month: '1',
    interval_minutes: 60,
    cron_expression: '0 2 * * *',
    timezone: 'UTC',
    hostname: 'localhost',
    notification_emails: '',
    notify_on_failure: true
  })
  const [testingAlert, setTestingAlert] = useState(false)
  const [modalError, setModalError] = useState(null)
  const [savingSchedule, setSavingSchedule] = useState(false)
  const [smtpConfig, setSmtpConfig] = useState({ is_configured: false, host: '' })

  // Fetch Schedules & History
  const fetchSchedulesAndHistory = async () => {
    if (!projectId) return
    setLoading(true)
    try {
      const [schedRes, histRes, smtpRes] = await Promise.all([
        api.get(`/api/projects/${projectId}/schedules`),
        api.get(`/api/projects/${projectId}/schedules/history`),
        api.get('/api/settings/smtp').catch(() => ({ data: { is_configured: false } }))
      ])
      setSchedules(schedRes.data || [])
      setHistory(histRes.data || [])
      if (smtpRes?.data) {
        setSmtpConfig(smtpRes.data)
      }
    } catch (err) {
      console.error('Failed to load scheduler data:', err)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchSchedulesAndHistory()
    const interval = setInterval(fetchSchedulesAndHistory, 15000)
    return () => clearInterval(interval)
  }, [projectId])

  // Open Create Modal
  const handleOpenCreate = () => {
    setEditingSchedule(null)
    const firstDoc = projectDocs[0]
    const co = firstDoc?.analysis?.control_overview || {}
    const ctrlNum = co?.identification?.control_number || (co?.control_digits ? `Control-${co.control_digits}` : 'HLA Pipeline')
    setFormData({
      document_id: firstDoc?.id || '',
      name: `${ctrlNum} Automated Run`,
      environment: 'dev',
      schedule_type: 'daily',
      run_time: '02:00',
      days_of_week: 'mon,tue,wed,thu,fri',
      day_of_month: '1',
      interval_minutes: 60,
      cron_expression: '0 2 * * *',
      timezone: 'UTC',
      hostname: 'localhost',
      notification_emails: '',
      notify_on_failure: true
    })
    setModalError(null)
    setShowModal(true)
  }

  // Open Edit Modal
  const handleOpenEdit = (sched) => {
    setEditingSchedule(sched)
    setFormData({
      document_id: sched.document_id,
      name: sched.name,
      environment: sched.environment || 'dev',
      schedule_type: sched.schedule_type || 'daily',
      run_time: sched.run_time || '02:00',
      days_of_week: sched.days_of_week || 'mon,tue,wed,thu,fri',
      day_of_month: String(sched.day_of_month || '1'),
      interval_minutes: sched.interval_minutes || 60,
      cron_expression: sched.cron_expression || '0 2 * * *',
      timezone: sched.timezone || 'UTC',
      hostname: sched.hostname || 'localhost',
      notification_emails: sched.notification_emails || '',
      notify_on_failure: sched.notify_on_failure !== false
    })
    setModalError(null)
    setShowModal(true)
  }

  // Trigger on-demand test email failure alert
  const handleTestEmailAlert = async () => {
    const targetEmail = window.prompt(
      'Enter recipient email to receive an automated test failure alert (leave empty for workspace default recipients):',
      currentUser?.email || ''
    )
    if (targetEmail === null) return // user pressed cancel

    setTestingAlert(true)
    try {
      const res = await api.post(`/api/projects/${projectId}/schedules/test-email-alert`, {
        recipient_emails: targetEmail.trim()
      })
      alert(`✓ Test Email Failure Alert Dispatched!\nStatus: ${res.data?.status}\nRecipients: ${res.data?.recipients?.join(', ')}`)
      fetchSchedulesAndHistory()
    } catch (err) {
      alert(`Failed to dispatch test email alert: ${err.response?.data?.error || err.message}`)
    } finally {
      setTestingAlert(false)
    }
  }

  // Save Schedule (Create or Update with Zod Validation)
  const handleSaveSchedule = async (e) => {
    e.preventDefault()
    setModalError(null)

    // Zod Schema Validation
    const validation = scheduleFormSchema.safeParse({
      ...formData,
      document_id: Number(formData.document_id),
      interval_minutes: Number(formData.interval_minutes || 60)
    })
    if (!validation.success) {
      const firstIssue = validation.error.issues[0]?.message || 'Invalid form input'
      setModalError(`Validation error: ${firstIssue}`)
      return
    }

    setSavingSchedule(true)
    try {
      if (editingSchedule) {
        await api.put(`/api/projects/${projectId}/schedules/${editingSchedule.id}`, formData)
      } else {
        await api.post(`/api/projects/${projectId}/schedules`, formData)
      }
      setShowModal(false)
      fetchSchedulesAndHistory()
    } catch (err) {
      setModalError(err.response?.data?.error || 'Failed to save schedule.')
    } finally {
      setSavingSchedule(false)
    }
  }

  // Toggle Active/Paused
  const handleToggle = async (schedId) => {
    try {
      await api.post(`/api/projects/${projectId}/schedules/${schedId}/toggle`)
      fetchSchedulesAndHistory()
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to toggle schedule.')
    }
  }

  // Delete Schedule
  const handleDelete = async (schedId, schedName) => {
    if (!window.confirm(`Are you sure you want to delete schedule "${schedName}"?`)) return
    try {
      await api.delete(`/api/projects/${projectId}/schedules/${schedId}`)
      fetchSchedulesAndHistory()
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to delete schedule.')
    }
  }

  // Run Now
  const handleRunNow = async (schedId) => {
    setRunningScheduleId(schedId)
    try {
      const res = await api.post(`/api/projects/${projectId}/schedules/${schedId}/run`)
      await fetchSchedulesAndHistory()
      // Open execution log viewer for the freshly triggered run
      setSelectedRunLog(res.data)
    } catch (err) {
      alert(err.response?.data?.error || 'Control execution failed.')
    } finally {
      setRunningScheduleId(null)
    }
  }

  // Trigger on-demand manual control run
  const handleTriggerManualRun = async (e) => {
    e.preventDefault()
    if (!manualRunData.document_id) {
      alert('Please select an HLA Document to run.')
      return
    }
    if (!manualRunData.hostname?.trim()) {
      alert('Hostname is required. The scheduler works only when hostname is provided.')
      return
    }
    setTriggeringManualRun(true)
    try {
      const res = await api.post(`/api/projects/${projectId}/documents/${manualRunData.document_id}/run-control`, {
        environment: manualRunData.environment,
        hostname: manualRunData.hostname.trim()
      })
      setShowManualRunModal(false)
      await fetchSchedulesAndHistory()
      setSelectedRunLog(res.data)
    } catch (err) {
      alert(err.response?.data?.error || 'Control execution failed.')
    } finally {
      setTriggeringManualRun(false)
    }
  }

  // KPI Calculations
  const activeSchedulesCount = schedules.filter((s) => s.is_active).length
  const lastRun = history[0] || null
  const nextScheduledRun = schedules
    .filter((s) => s.is_active && s.next_run_at)
    .sort((a, b) => new Date(a.next_run_at) - new Date(b.next_run_at))[0]

  // Filtered History
  const filteredHistory = history.filter((r) => {
    if (statusFilter === 'ALL') return true
    return r.status === statusFilter
  })

  // Format Helper
  const formatDateTime = (iso) => {
    if (!iso) return 'Never'
    try {
      const d = new Date(iso)
      return `${d.toLocaleDateString()} ${d.toLocaleTimeString()}`
    } catch {
      return String(iso)
    }
  }

  const getStatusBadgeClass = (status) => {
    switch (status?.toUpperCase()) {
      case 'SUCCESS':
        return 'pill-status pill-success'
      case 'BLOCKED':
        return 'pill-status pill-blocked'
      case 'FAILED':
        return 'pill-status pill-failed'
      case 'RUNNING':
        return 'pill-status pill-running'
      default:
        return 'pill-status'
    }
  }

  const primaryAlertEmail =
    schedules.find((s) => s.notification_emails)?.notification_emails?.split(',')[0]?.trim() ||
    currentUser?.email ||
    'ganeshcllg@gmail.com'

  const getScheduleTypeLabel = (sched) => {
    if (sched.schedule_type === 'daily') return `Daily at ${sched.run_time} (${sched.timezone})`
    if (sched.schedule_type === 'hourly') return `Hourly at :${sched.run_time?.split(':')[1] || '00'}`
    if (sched.schedule_type === 'weekly') return `Weekly (${sched.days_of_week}) at ${sched.run_time} (${sched.timezone})`
    if (sched.schedule_type === 'monthly') return `Monthly (${sched.day_of_month === 'last' ? 'Last day' : `Day ${sched.day_of_month || '1'}`}) at ${sched.run_time} (${sched.timezone})`
    if (sched.schedule_type === 'interval') return `Every ${sched.interval_minutes} mins`
    if (sched.schedule_type === 'custom_cron') return `Cron: ${sched.cron_expression}`
    return 'Custom'
  }

  return (
    <div className="control-scheduler-container">
      {/* ── Top Overview Banner ── */}
      <div className="scheduler-header-card glass-card">
        <div className="header-info-wrap">
          <div className="header-icon-box">
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </div>
          <div>
            <h2 className="scheduler-title">Workspace Control Scheduler</h2>
            <p className="scheduler-subtitle">
              Automate and monitor scheduled reconciliation runs, schema verification, and pipeline quality gates.
            </p>
          </div>
        </div>

        {!isViewer && (
          <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center', flexWrap: 'wrap' }}>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setShowSMTPModal(true)}
              title="Open Email Notification & Test Center"
              style={{ fontSize: '0.98rem', padding: '0.65rem 1.15rem', display: 'flex', alignItems: 'center', gap: '0.45rem' }}
            >
              <span>📧</span>
              <span>Email Alerts & Test</span>
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => {
                setManualRunData({
                  document_id: projectDocs[0]?.id || '',
                  environment: 'dev',
                  hostname: 'localhost'
                })
                setShowManualRunModal(true)
              }}
              title="Trigger immediate on-demand manual execution of a control pipeline"
              style={{ fontSize: '0.98rem', padding: '0.65rem 1.15rem', display: 'flex', alignItems: 'center', gap: '0.45rem', borderColor: 'rgba(14, 165, 233, 0.4)' }}
            >
              <span>⚡</span>
              <span>Run Control Manually</span>
            </button>
            <button className="btn-primary btn-new-schedule" onClick={handleOpenCreate} style={{ fontSize: '1rem', padding: '0.65rem 1.35rem' }}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              <span>Schedule New Control</span>
            </button>
          </div>
        )}
      </div>

      {/* ── KPI Stat Strip ── */}
      <div className="scheduler-kpi-grid">
        <div className="kpi-card glass-card">
          <span className="kpi-label">Active Automated Schedules</span>
          <div className="kpi-val-row">
            <span className="kpi-val text-cyan">{activeSchedulesCount}</span>
            <span className="kpi-subval">/ {schedules.length} total</span>
          </div>
        </div>

        <div className="kpi-card glass-card">
          <span className="kpi-label">Next Scheduled Run</span>
          <div className="kpi-val-row">
            <span className="kpi-val text-emerald" style={{ fontSize: '1.05rem', fontFamily: 'var(--font-mono)' }}>
              {nextScheduledRun ? formatDateTime(nextScheduledRun.next_run_at) : 'None Scheduled'}
            </span>
          </div>
          <span className="kpi-subval">
            {nextScheduledRun ? `${nextScheduledRun.control_number} (${nextScheduledRun.timezone})` : 'Create a schedule to activate'}
          </span>
        </div>

        <div className="kpi-card glass-card">
          <span className="kpi-label">Last Execution Status</span>
          <div className="kpi-val-row">
            {lastRun ? (
              <span className={getStatusBadgeClass(lastRun.status)}>
                {lastRun.status}
              </span>
            ) : (
              <span className="kpi-subval">No runs recorded</span>
            )}
            {lastRun && (
              <span className="kpi-subval">
                {lastRun.duration_seconds ? `${lastRun.duration_seconds}s` : ''}
              </span>
            )}
          </div>
          <span className="kpi-subval">
            {lastRun ? `${lastRun.control_number} • ${formatDateTime(lastRun.started_at)}` : 'Ready for first run'}
          </span>
        </div>

        <div className="kpi-card glass-card">
          <span className="kpi-label">Total Execution Runs</span>
          <div className="kpi-val-row">
            <span className="kpi-val text-purple">{history.length}</span>
            <span className="kpi-subval">Audit Records</span>
          </div>
        </div>
      </div>

      {/* ── Sub-navigation Tabs ── */}
      <div className="scheduler-subtabs-wrap">
        <div className="subtabs-bar">
          <button
            className={`subtab-btn ${activeTab === 'schedules' ? 'active' : ''}`}
            onClick={() => setActiveTab('schedules')}
          >
            <span>⏰ Configured Schedules ({schedules.length})</span>
          </button>
          <button
            className={`subtab-btn ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => setActiveTab('history')}
          >
            <span>📜 Execution History & Audit Logs ({history.length})</span>
          </button>
        </div>
      </div>

      {/* ── TAB 1: Configured Schedules ── */}
      {activeTab === 'schedules' && (
        <div className="schedules-view-wrap">
          {schedules.length === 0 ? (
            <div className="glass-card empty-schedules-card">
              <div className="empty-icon-wrap">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
              </div>
              <h3>No Control Schedules Configured</h3>
              <p>Automate your control runs at specific daily hours, intervals, or custom cron expressions.</p>
              {!isViewer && (
                <button className="btn-primary" onClick={handleOpenCreate}>
                  + Create First Schedule
                </button>
              )}
            </div>
          ) : (
            <div className="schedules-grid">
              {schedules.map((sched) => (
                <div key={sched.id} className={`schedule-item-card glass-card ${sched.is_active ? 'active-border' : 'paused-border'}`}>
                  {/* Card Top Row: Identification, Doc, and Primary Controls */}
                  <div className="card-top-row">
                    <div className="card-title-group">
                      <span className="ctrl-badge">{sched.control_number}</span>
                      <span className={`env-pill env-${sched.environment}`}>{sched.environment.toUpperCase()}</span>
                      <h3 className="sched-name" title={sched.name}>{sched.name}</h3>
                      {sched.document_name && (
                        <span className="sched-doc-pill" title={`Linked Document: ${sched.document_name}`}>
                          📄 {sched.document_name}
                        </span>
                      )}
                    </div>

                    <div className="card-top-actions">
                      <span className="hostname-tag" title="Execution Hostname">
                        {sched.hostname ? (
                          <span>🖥️ {sched.hostname}</span>
                        ) : (
                          <span style={{ color: '#f87171' }}>⚠️ Missing Hostname</span>
                        )}
                      </span>

                      {!isViewer ? (
                        <button
                          className={`btn-toggle-switch ${sched.is_active ? 'switch-on' : 'switch-off'}`}
                          onClick={() => handleToggle(sched.id)}
                          title={sched.is_active ? 'Pause Schedule' : 'Activate Schedule'}
                        >
                          <span className="switch-dot" />
                          <span className="switch-text">{sched.is_active ? 'Active' : 'Paused'}</span>
                        </button>
                      ) : (
                        <span className={`status-pill ${sched.is_active ? 'connected' : 'warning'}`}>
                          {sched.is_active ? 'Active' : 'Paused'}
                        </span>
                      )}

                      {!isViewer && (
                        <div className="card-btn-group">
                          <button
                            className="btn-run-now"
                            disabled={runningScheduleId === sched.id}
                            onClick={() => handleRunNow(sched.id)}
                            title="Trigger immediate execution pipeline for this control"
                          >
                            {runningScheduleId === sched.id ? (
                              <>
                                <span className="spinner-inline" />
                                <span>Running...</span>
                              </>
                            ) : (
                              <span>▶ Run Now</span>
                            )}
                          </button>
                          <button className="btn-icon-action" onClick={() => handleOpenEdit(sched)} title="Edit Schedule">
                            ✏️ Edit
                          </button>
                          <button className="btn-icon-action btn-del" onClick={() => handleDelete(sched.id, sched.name)} title="Delete Schedule">
                            🗑️
                          </button>
                        </div>
                      )}
                    </div>
                  </div>

                  {/* Card Metadata Strip: 4 Dedicated Spacious Columns */}
                  <div className="sched-meta-strip">
                    <div className="meta-box">
                      <span className="meta-label">Frequency & Schedule</span>
                      <span className="meta-val" title={getScheduleTypeLabel(sched)}>
                        📅 {getScheduleTypeLabel(sched)}
                      </span>
                    </div>

                    <div className="meta-box">
                      <span className="meta-label">Next Execution</span>
                      <span className="meta-val text-emerald">
                        ⏱️ {sched.is_active ? formatDateTime(sched.next_run_at) : 'Paused'}
                      </span>
                    </div>

                    <div className="meta-box">
                      <span className="meta-label">Last Execution Status</span>
                      <div className="meta-val-row">
                        {sched.last_run_status ? (
                          <span className={getStatusBadgeClass(sched.last_run_status)}>
                            {sched.last_run_status}
                          </span>
                        ) : (
                          <span className="text-muted" style={{ fontSize: '0.88rem' }}>Never run</span>
                        )}
                      </div>
                    </div>

                    <div className="meta-box">
                      <span className="meta-label">Failure Alert Notification</span>
                      <div className="meta-val" title={sched.notification_emails || 'Workspace Admins & Creator'}>
                        {sched.notify_on_failure !== false ? (
                          <span style={{ color: '#34d399', display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                            🔔 {sched.notification_emails ? sched.notification_emails : 'Active (Admins)'}
                          </span>
                        ) : (
                          <span style={{ color: '#94a3b8' }}>🔕 Disabled</span>
                        )}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── TAB 2: Execution History & Audit Logs ── */}
      {activeTab === 'history' && (
        <div className="history-view-wrap glass-card">
          <div className="history-filter-bar">
            <span style={{ fontSize: '0.84rem', fontWeight: 600, color: 'var(--text-muted)' }}>Filter by Status:</span>
            <div className="filter-pill-group">
              {['ALL', 'SUCCESS', 'BLOCKED', 'FAILED'].map((st) => (
                <button
                  key={st}
                  className={`filter-pill-btn ${statusFilter === st ? 'active' : ''}`}
                  onClick={() => setStatusFilter(st)}
                >
                  {st}
                </button>
              ))}
            </div>
          </div>

          {filteredHistory.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '3rem', color: 'var(--text-muted)' }}>
              No execution history records match the selected filter.
            </div>
          ) : (
            <div className="table-responsive-wrapper">
              <table className="scheduler-table">
                <thead>
                  <tr>
                    <th>Run ID</th>
                    <th>Control</th>
                    <th>Hostname</th>
                    <th>Trigger Mode</th>
                    <th>Status</th>
                    <th>Started At</th>
                    <th>Duration</th>
                    <th>Table Verification</th>
                    <th>Summary Outcome</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredHistory.map((run) => (
                    <tr key={run.id}>
                      <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--cyan-400)', fontWeight: 600 }}>
                        #{run.id}
                      </td>
                      <td>
                        <span className="ctrl-badge-small">{run.control_number}</span>
                        <span style={{ marginLeft: '0.4rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                          [{run.environment.toUpperCase()}]
                        </span>
                      </td>
                      <td>
                        <span className="hostname-pill" style={{ fontSize: '0.76rem', color: run.hostname ? '#38bdf8' : '#f87171', fontFamily: 'var(--font-mono)' }}>
                          {run.hostname ? `🖥️ ${run.hostname}` : 'None'}
                        </span>
                      </td>
                      <td>
                        <span className={`trigger-tag ${run.trigger_type.toLowerCase()}`}>
                          {run.trigger_type}
                        </span>
                      </td>
                      <td>
                        <span className={getStatusBadgeClass(run.status)}>
                          {run.status}
                        </span>
                      </td>
                      <td style={{ fontSize: '0.8rem', color: '#cbd5e1' }}>
                        {formatDateTime(run.started_at)}
                      </td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8rem' }}>
                        {run.duration_seconds !== null ? `${run.duration_seconds}s` : '—'}
                      </td>
                      <td>
                        <span style={{ fontSize: '0.8rem' }}>
                          <span style={{ color: run.tables_missing_count > 0 ? '#f59e0b' : '#34d399', fontWeight: 600 }}>
                            {run.tables_found_count}/{run.tables_checked_count} Verified
                          </span>
                          {run.tables_missing_count > 0 && (
                            <span style={{ color: '#f87171', marginLeft: '0.3rem' }}>
                              ({run.tables_missing_count} missing)
                            </span>
                          )}
                        </span>
                      </td>
                      <td style={{ fontSize: '0.78rem', color: '#94a3b8', maxWidth: '280px', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }} title={run.summary_message}>
                        {run.summary_message}
                      </td>
                      <td>
                        <button
                          className="btn-view-log"
                          onClick={() => setSelectedRunLog(run)}
                          title="View step-by-step console audit log"
                        >
                          📋 View Log
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* ── Modal: Create / Edit Schedule ── */}
      {showModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog glass-card scheduler-modal">
            <div className="modal-header">
              <h3>{editingSchedule ? 'Edit Control Schedule' : 'Schedule Automated Control'}</h3>
              <button className="btn-close" onClick={() => setShowModal(false)}>✕</button>
            </div>

            <form onSubmit={handleSaveSchedule} className="modal-form">
              {modalError && <div className="modal-error-banner">{modalError}</div>}

              <div className="form-group">
                <label>Target Control / HLA Document</label>
                <select
                  value={formData.document_id}
                  onChange={(e) => {
                    const docId = Number(e.target.value)
                    const selected = projectDocs.find((d) => d.id === docId)
                    const co = selected?.analysis?.control_overview || {}
                    const ctrlNum = co?.identification?.control_number || (co?.control_digits ? `Control-${co.control_digits}` : 'HLA Pipeline')
                    setFormData({
                      ...formData,
                      document_id: docId,
                      name: `${ctrlNum} Automated Run`
                    })
                  }}
                  className="form-control"
                  required
                >
                  {projectDocs.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.original_name || d.filename} ({d.file_type})
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-group">
                <label>Schedule Name</label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  placeholder="e.g. Daily Production Nightly Reconciliation"
                  className="form-control"
                  required
                />
              </div>

              <div className="form-group">
                <label>Execution Hostname / Server Host <span style={{ color: '#f87171' }}>*</span></label>
                <input
                  type="text"
                  value={formData.hostname}
                  onChange={(e) => setFormData({ ...formData, hostname: e.target.value })}
                  placeholder="e.g. localhost or db-server-01.internal"
                  className="form-control"
                  required
                />
                <small style={{ color: 'var(--text-muted)', fontSize: '0.86rem' }}>
                  Mandatory: The scheduler works only when a valid hostname is provided.
                </small>
              </div>

              <div className="form-row-2col">
                <div className="form-group">
                  <label>Environment</label>
                  <select
                    value={formData.environment}
                    onChange={(e) => setFormData({ ...formData, environment: e.target.value })}
                    className="form-control"
                  >
                    <option value="dev">Development (Dev)</option>
                    <option value="prod">Production (Prod)</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Frequency Type</label>
                  <select
                    value={formData.schedule_type}
                    onChange={(e) => setFormData({ ...formData, schedule_type: e.target.value })}
                    className="form-control"
                  >
                    <option value="daily">Daily (At specific time)</option>
                    <option value="hourly">Hourly (Every hour)</option>
                    <option value="weekly">Weekly (Specific days)</option>
                    <option value="monthly">Monthly (Specific day of month)</option>
                    <option value="interval">Custom Interval (Minutes)</option>
                    <option value="custom_cron">Advanced Cron Expression</option>
                  </select>
                </div>
              </div>

              {formData.schedule_type === 'daily' && (
                <div className="form-row-2col">
                  <div className="form-group">
                    <label>Execution Time (HH:MM 24h)</label>
                    <input
                      type="time"
                      value={formData.run_time}
                      onChange={(e) => setFormData({ ...formData, run_time: e.target.value })}
                      className="form-control"
                      required
                    />
                  </div>
                  <div className="form-group">
                    <label>Timezone</label>
                    <select
                      value={formData.timezone}
                      onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                      className="form-control"
                    >
                      <option value="UTC">UTC (Coordinated Universal Time)</option>
                      <option value="Asia/Kolkata">Asia/Kolkata (IST +5:30)</option>
                      <option value="America/New_York">America/New_York (EST/EDT)</option>
                      <option value="Europe/London">Europe/London (GMT/BST)</option>
                      <option value="Asia/Singapore">Asia/Singapore (SGT +8:00)</option>
                    </select>
                  </div>
                </div>
              )}

              {formData.schedule_type === 'hourly' && (
                <div className="form-group">
                  <label>Minute past the hour (0-59)</label>
                  <input
                    type="number"
                    min="0"
                    max="59"
                    value={parseInt(formData.run_time.split(':')[1] || '0', 10)}
                    onChange={(e) => setFormData({ ...formData, run_time: `00:${String(e.target.value).padStart(2, '0')}` })}
                    className="form-control"
                  />
                </div>
              )}

              {formData.schedule_type === 'weekly' && (
                <>
                  <div className="form-group">
                    <label>Days of Week (comma-separated: mon,tue,wed,thu,fri,sat,sun)</label>
                    <input
                      type="text"
                      value={formData.days_of_week}
                      onChange={(e) => setFormData({ ...formData, days_of_week: e.target.value })}
                      placeholder="mon,tue,wed,thu,fri"
                      className="form-control"
                      required
                    />
                  </div>
                  <div className="form-row-2col">
                    <div className="form-group">
                      <label>Execution Time</label>
                      <input
                        type="time"
                        value={formData.run_time}
                        onChange={(e) => setFormData({ ...formData, run_time: e.target.value })}
                        className="form-control"
                        required
                      />
                    </div>
                    <div className="form-group">
                      <label>Timezone</label>
                      <select
                        value={formData.timezone}
                        onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                        className="form-control"
                      >
                        <option value="UTC">UTC</option>
                        <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
                        <option value="America/New_York">America/New_York (EST)</option>
                        <option value="Europe/London">Europe/London (GMT)</option>
                        <option value="Asia/Singapore">Asia/Singapore (SGT +8:00)</option>
                      </select>
                    </div>
                  </div>
                </>
              )}

              {formData.schedule_type === 'monthly' && (
                <>
                  <div className="form-row-2col">
                    <div className="form-group">
                      <label>Day of Month</label>
                      <select
                        value={formData.day_of_month}
                        onChange={(e) => setFormData({ ...formData, day_of_month: e.target.value })}
                        className="form-control"
                      >
                        {Array.from({ length: 31 }, (_, i) => i + 1).map((d) => (
                          <option key={d} value={String(d)}>
                            {d === 1 ? '1st' : d === 2 ? '2nd' : d === 3 ? '3rd' : `${d}th`} of the month
                          </option>
                        ))}
                        <option value="last">Last day of the month</option>
                      </select>
                    </div>
                    <div className="form-group">
                      <label>Execution Time (HH:MM 24h)</label>
                      <input
                        type="time"
                        value={formData.run_time}
                        onChange={(e) => setFormData({ ...formData, run_time: e.target.value })}
                        className="form-control"
                        required
                      />
                    </div>
                  </div>
                  <div className="form-group">
                    <label>Timezone</label>
                    <select
                      value={formData.timezone}
                      onChange={(e) => setFormData({ ...formData, timezone: e.target.value })}
                      className="form-control"
                    >
                      <option value="UTC">UTC (Coordinated Universal Time)</option>
                      <option value="Asia/Kolkata">Asia/Kolkata (IST +5:30)</option>
                      <option value="America/New_York">America/New_York (EST/EDT)</option>
                      <option value="Europe/London">Europe/London (GMT/BST)</option>
                      <option value="Asia/Singapore">Asia/Singapore (SGT +8:00)</option>
                    </select>
                    <small style={{ color: 'var(--text-muted)', fontSize: '0.86rem', marginTop: '0.35rem', display: 'block' }}>
                      Executes monthly on {formData.day_of_month === 'last' ? 'the last day of the month' : `day ${formData.day_of_month}`} at {formData.run_time} ({formData.timezone}).
                    </small>
                  </div>
                </>
              )}

              {formData.schedule_type === 'interval' && (
                <div className="form-group">
                  <label>Interval in Minutes (e.g. 15, 30, 60, 120)</label>
                  <input
                    type="number"
                    min="5"
                    max="1440"
                    value={formData.interval_minutes}
                    onChange={(e) => setFormData({ ...formData, interval_minutes: Number(e.target.value) })}
                    className="form-control"
                    required
                  />
                </div>
              )}

              {formData.schedule_type === 'custom_cron' && (
                <div className="form-group">
                  <label>Cron Expression (min hour dom mon dow)</label>
                  <input
                    type="text"
                    value={formData.cron_expression}
                    onChange={(e) => setFormData({ ...formData, cron_expression: e.target.value })}
                    placeholder="0 2 * * *"
                    className="form-control"
                    required
                  />
                  <small style={{ color: 'var(--text-muted)', fontSize: '0.86rem', display: 'block', marginTop: '0.35rem' }}>
                    Example: <code>0 2 * * *</code> runs every day at 02:00.
                  </small>
                </div>
              )}

              {/* Automated Failure Email Notifications */}
              <div className="form-group" style={{ marginTop: '1rem', padding: '1rem', background: 'rgba(239, 68, 68, 0.06)', border: '1px solid rgba(239, 68, 68, 0.25)', borderRadius: '10px' }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.6rem' }}>
                  <label style={{ margin: 0, color: '#f87171', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.94rem' }}>
                    <span>🚨</span> Automatic Email Alerts on Failure
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', cursor: 'pointer', fontSize: '0.88rem', color: '#e2e8f0' }}>
                    <input
                      type="checkbox"
                      checked={formData.notify_on_failure !== false}
                      onChange={(e) => setFormData({ ...formData, notify_on_failure: e.target.checked })}
                    />
                    <span>Enabled</span>
                  </label>
                </div>
                <p style={{ margin: '0 0 0.6rem 0', fontSize: '0.88rem', color: '#94a3b8', lineHeight: 1.5 }}>
                  If the scheduled control run fails or upstream data has not arrived on scheduled time, automatic alert emails will be dispatched with full diagnostic logs and missing tables.
                </p>
                <div className="form-group" style={{ marginBottom: 0 }}>
                  <label style={{ fontSize: '0.88rem', color: '#cbd5e1' }}>Alert Recipient Emails (comma-separated)</label>
                  <input
                    type="text"
                    value={formData.notification_emails || ''}
                    onChange={(e) => setFormData({ ...formData, notification_emails: e.target.value })}
                    placeholder="e.g. data-ops@enterprise.com, oncall@domain.com"
                    className="form-control"
                  />
                  <small style={{ color: '#64748b', fontSize: '0.85rem', marginTop: '0.3rem', display: 'block' }}>
                    Note: Schedule creator and workspace administrators are also automatically notified.
                  </small>
                </div>
              </div>

              <div className="modal-footer">
                <button type="button" className="btn-secondary" onClick={() => setShowModal(false)} style={{ fontSize: '0.92rem' }}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={savingSchedule} style={{ fontSize: '0.94rem' }}>
                  {savingSchedule ? 'Saving...' : editingSchedule ? 'Update Schedule' : 'Activate Schedule'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Modal: Manual Control Run ── */}
      {showManualRunModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog glass-card scheduler-modal">
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                <span style={{ fontSize: '1.4rem' }}>⚡</span>
                <div>
                  <h3 style={{ margin: 0, fontSize: '1.35rem', fontWeight: 700, color: '#ffffff' }}>
                    Run Control Manually
                  </h3>
                  <p style={{ margin: '0.2rem 0 0 0', fontSize: '0.88rem', color: 'var(--text-muted)' }}>
                    Trigger immediate pipeline execution to verify source DB tables and target reconciliation.
                  </p>
                </div>
              </div>
              <button className="btn-close" onClick={() => setShowManualRunModal(false)}>✕</button>
            </div>

            <form className="modal-form" onSubmit={handleTriggerManualRun}>
              <div className="form-group">
                <label>Target HLA Control Document <span style={{ color: '#f87171' }}>*</span></label>
                <select
                  value={manualRunData.document_id}
                  onChange={(e) => setManualRunData({ ...manualRunData, document_id: Number(e.target.value) })}
                  className="form-control"
                  required
                >
                  {projectDocs.map((d) => (
                    <option key={d.id} value={d.id}>
                      {d.original_name || d.filename} ({d.file_type?.toUpperCase()})
                    </option>
                  ))}
                </select>
              </div>

              <div className="form-row-2col">
                <div className="form-group">
                  <label>Execution Environment</label>
                  <select
                    value={manualRunData.environment}
                    onChange={(e) => setManualRunData({ ...manualRunData, environment: e.target.value })}
                    className="form-control"
                  >
                    <option value="dev">Development (Dev)</option>
                    <option value="prod">Production (Prod)</option>
                  </select>
                </div>

                <div className="form-group">
                  <label>Execution Hostname <span style={{ color: '#f87171' }}>*</span></label>
                  <input
                    type="text"
                    value={manualRunData.hostname}
                    onChange={(e) => setManualRunData({ ...manualRunData, hostname: e.target.value })}
                    placeholder="e.g. localhost or db-server-01"
                    className="form-control"
                    required
                  />
                </div>
              </div>

              <div style={{ padding: '0.85rem 1rem', background: 'rgba(56, 189, 248, 0.08)', border: '1px solid rgba(56, 189, 248, 0.25)', borderRadius: '8px', fontSize: '0.88rem', color: '#bae6fd', lineHeight: 1.5 }}>
                ℹ️ <strong>Quality Gate Reminder:</strong> The control run strictly requires valid source database connections and available source tables. If source DB info is missing or tables are not found, the run will fail and trigger an automated failure alert.
              </div>

              <div className="modal-footer">
                <button type="button" className="btn-secondary" onClick={() => setShowManualRunModal(false)} style={{ fontSize: '0.92rem' }}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={triggeringManualRun} style={{ fontSize: '0.94rem' }}>
                  {triggeringManualRun ? 'Executing Pipeline…' : '▶ Execute Control Pipeline'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Modal: Execution Log Viewer ── */}
      {selectedRunLog && (
        <div className="modal-backdrop">
          <div className="modal-dialog glass-card log-modal">
            <div className="modal-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                <span className="ctrl-badge">{selectedRunLog.control_number}</span>
                <h3 style={{ margin: 0, fontSize: '1.3rem', fontWeight: 700, color: '#ffffff' }}>
                  Execution Run #{selectedRunLog.id} Audit Log
                </h3>
                <span className={getStatusBadgeClass(selectedRunLog.status)}>
                  {selectedRunLog.status}
                </span>
              </div>
              <button className="btn-close" onClick={() => setSelectedRunLog(null)}>✕</button>
            </div>

            <div className="log-meta-bar" style={{ fontSize: '0.92rem' }}>
              <div><strong>Started:</strong> {formatDateTime(selectedRunLog.started_at)}</div>
              <div><strong>Duration:</strong> {selectedRunLog.duration_seconds}s</div>
              <div><strong>Hostname:</strong> <span style={{ color: '#38bdf8' }}>{selectedRunLog.hostname || 'Not Provided'}</span></div>
              <div><strong>Trigger:</strong> {selectedRunLog.trigger_type}</div>
              <div><strong>Target Env:</strong> {selectedRunLog.environment?.toUpperCase()}</div>
              <div><strong>Verified Tables:</strong> {selectedRunLog.tables_found_count}/{selectedRunLog.tables_checked_count}</div>
            </div>

            {selectedRunLog.summary_message && (
              <div className={`log-summary-box ${selectedRunLog.status?.toLowerCase()}`} style={{ fontSize: '0.94rem', lineHeight: 1.5 }}>
                <strong>Summary Outcome:</strong> {selectedRunLog.summary_message}
              </div>
            )}

            {(selectedRunLog.status === 'BLOCKED' || selectedRunLog.status === 'FAILED') && (
              <div className="log-smtp-banner success">
                <span style={{ fontSize: '1.5rem' }}>📧</span>
                <div style={{ flex: 1 }}>
                  <strong style={{ fontSize: '1.02rem', color: '#34d399' }}>Automated Failure Alert Dispatched:</strong>{' '}
                  <span style={{ color: '#e2e8f0', fontSize: '0.96rem' }}>
                    Triggered to {selectedRunLog.result_details?.email_alert?.recipients?.join(', ') || primaryAlertEmail} with full audit diagnostics.
                  </span>
                </div>
                <button
                  type="button"
                  className="btn-configure-smtp-modal"
                  onClick={() => {
                    setSelectedRunLog(null)
                    setShowSMTPModal(true)
                  }}
                  style={{ fontSize: '0.92rem' }}
                >
                  📧 Email Center & Test
                </button>
              </div>
            )}

            <div className="log-console-wrap">
              <pre className="log-console-text">
                {selectedRunLog.execution_log || 'No console log recorded for this run.'}
              </pre>
            </div>

            <div className="modal-footer" style={{ justifyContent: 'flex-end' }}>
              <button className="btn-secondary" onClick={() => setSelectedRunLog(null)} style={{ fontSize: '0.92rem' }}>
                Close Log
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Modal: SMTP & Email Configuration ── */}
      {showSMTPModal && (
        <SMTPSettingsModal
          onClose={() => {
            setShowSMTPModal(false)
            fetchSchedulesAndHistory()
          }}
          currentUser={currentUser}
          defaultEmail={primaryAlertEmail}
        />
      )}
    </div>
  )
}
