import React, { useState, useEffect } from 'react'
import api from '../services/api'
import './SourceDBManager.css'

export default function SourceDBManager({ projectId, onClose, onSaved, currentUser }) {
  const isViewer = currentUser?.role?.toLowerCase() === 'viewer'
  const [managerMode, setManagerMode] = useState('manual') // 'manual' | 'vault'
  const [connectionsList, setConnectionsList] = useState([])
  const [activeConnId, setActiveConnId] = useState(null) // null = new connection
  const [loading, setLoading] = useState(false)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [testResult, setTestResult] = useState(null)

  // Connection Form State
  const [formData, setFormData] = useState({
    source_db_name: '',
    db_type: 'postgresql',
    host: 'localhost',
    port: '5432',
    database_name: 'hla_db',
    username: 'postgres',
    password: '',
    schema_name: '',
    connection_string: '',
  })

  // KDB Vault Form State
  const [vaultText, setVaultText] = useState('')
  const [vaultFile, setVaultFile] = useState(null)
  const [importingVault, setImportingVault] = useState(false)
  const [vaultResult, setVaultResult] = useState(null)

  const handleClose = () => {
    if (onClose) {
      onClose()
    }
  }

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        handleClose()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  useEffect(() => {
    if (projectId) {
      fetchConnections()
    }
  }, [projectId])

  const fetchConnections = async () => {
    setLoading(true)
    try {
      const res = await api.get(`/api/projects/${projectId}/connections`)
      const conns = res.data || []
      // Filter for source connections
      const sources = conns.filter(c => c.conn_role !== 'target')
      setConnectionsList(sources)

      if (sources.length > 0 && activeConnId === null) {
        selectConnection(sources[0])
      } else if (sources.length === 0) {
        initNewConnection()
      }
    } catch (err) {
      console.error('Failed to load connections:', err)
    } finally {
      setLoading(false)
    }
  }

  const selectConnection = (conn) => {
    setActiveConnId(conn.id)
    setFormData({
      source_db_name: conn.source_db_name || '',
      db_type: conn.db_type || 'postgresql',
      host: conn.host || 'localhost',
      port: conn.port ? String(conn.port) : '5432',
      database_name: conn.database_name || (conn.host === 'localhost' ? 'hla_db' : ''),
      username: conn.username || 'postgres',
      password: '',
      schema_name: conn.schema_name || 'public',
      connection_string: conn.connection_string || '',
    })
    setTestResult(conn.status === 'connected' ? { success: true, message: 'Verified connection active ✓' } : null)
  }

  const initNewConnection = () => {
    setActiveConnId(null)
    setFormData({
      source_db_name: '',
      db_type: 'postgresql',
      host: 'localhost',
      port: '5432',
      database_name: 'hla_db',
      username: 'postgres',
      password: '',
      schema_name: '',
      connection_string: '',
    })
    setTestResult(null)
  }

  const handleTest = async () => {
    setTesting(true)
    setTestResult(null)
    try {
      const res = await api.post(`/api/projects/${projectId}/connections/test`, {
        ...formData,
        database_name: formData.database_name?.trim() || (formData.host === 'localhost' ? 'hla_db' : '')
      })
      setTestResult(res.data)
    } catch (err) {
      setTestResult({
        success: false,
        message: err.response?.data?.error || 'Connection attempt failed',
      })
    } finally {
      setTesting(false)
    }
  }

  const handleSave = async (e) => {
    e.preventDefault()
    if (!formData.source_db_name.trim()) {
      alert('Please enter a Connection Name for this database.')
      return
    }

    setSaving(true)
    try {
      const payload = {
        ...formData,
        id: activeConnId || undefined,
        source_db_name: formData.source_db_name.trim(),
        database_name: formData.database_name?.trim() || (formData.host === 'localhost' ? 'hla_db' : ''),
        conn_role: 'source',
      }
      const res = await api.post(`/api/projects/${projectId}/connections`, payload)
      setTestResult(res.data)
      await fetchConnections()
      if (res.data?.connection?.id) {
        setActiveConnId(res.data.connection.id)
      }
      if (onSaved) onSaved()
    } catch (err) {
      setTestResult({
        success: false,
        message: err.response?.data?.error || 'Failed to save connection',
      })
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteConnection = async () => {
    if (!activeConnId) return
    const target = connectionsList.find(c => c.id === activeConnId)
    const name = target?.source_db_name || 'this connection'

    if (!window.confirm(`Are you sure you want to remove connection '${name}'?`)) {
      return
    }

    setDeleting(true)
    try {
      await api.delete(`/api/projects/${projectId}/connections/${activeConnId}`)
      await fetchConnections()
      initNewConnection()
      if (onSaved) onSaved()
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to remove connection.')
    } finally {
      setDeleting(false)
    }
  }

  const handleVaultUpload = async (e) => {
    e.preventDefault()
    setImportingVault(true)
    setVaultResult(null)

    try {
      let res
      if (vaultFile) {
        const data = new FormData()
        data.append('file', vaultFile)
        res = await api.post(`/api/projects/${projectId}/vault-upload`, data, {
          headers: { 'Content-Type': 'multipart/form-data' },
        })
      } else if (vaultText.trim()) {
        res = await api.post(`/api/projects/${projectId}/vault-upload`, {
          raw_content: vaultText,
          filename: 'vault.ini',
        })
      } else {
        alert('Please select a .kdb / vault file or paste configuration text.')
        setImportingVault(false)
        return
      }

      setVaultResult({
        success: true,
        message: res.data?.message,
        connections: res.data?.connections || [],
        total: res.data?.total_imported,
      })

      await fetchConnections()
      if (onSaved) onSaved()
    } catch (err) {
      setVaultResult({
        success: false,
        message: err.response?.data?.error || 'Failed to parse credential vault.',
      })
    } finally {
      setImportingVault(false)
    }
  }

  const handleLoadSampleTemplate = () => {
    const template = `[source.Production_Warehouse]
db_type = postgresql
host = localhost
port = 5432
database = hla_db
username = postgres
password = your_password_here
schema = public

[source.CRM_Analytics]
db_type = postgresql
host = localhost
port = 5432
database = hla_db
username = postgres
password = your_password_here
schema = public

[target.dev]
db_type = postgresql
host = localhost
port = 5432
database = hla_db
username = postgres
password = your_password_here
schema = target_dev

[target.prod]
db_type = postgresql
host = localhost
port = 5432
database = hla_db
username = postgres
password = your_password_here
schema = target_prod`
    setVaultText(template)
  }

  return (
    <div className="modal-backdrop" onClick={handleClose}>
      <div className="db-manager-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <h3>
            <span>⚙️</span> Database Connection Manager
          </h3>
          <button type="button" className="btn-close-modal" onClick={handleClose} title="Close (Esc)">✕</button>
        </div>

        {/* Mode Selector */}
        <div className="db-mode-selector">
          <button
            className={`db-mode-btn ${managerMode === 'manual' ? 'active' : ''}`}
            onClick={() => setManagerMode('manual')}
          >
            <span>✍️</span> Named Database Connections
          </button>
          <button
            className={`db-mode-btn ${managerMode === 'vault' ? 'active' : ''}`}
            onClick={() => setManagerMode('vault')}
          >
            <span>🔐</span> Import .kdb / Credential Vault
          </button>
        </div>

        {/* ── Mode 1: Manual Named Connections ── */}
        {managerMode === 'manual' && (
          <div>
            {/* Connection Tabs Strip */}
            <div className="db-select-tabs">
              {connectionsList.map((conn) => (
                <button
                  key={conn.id}
                  className={`db-tab-btn ${activeConnId === conn.id ? 'active' : ''}`}
                  onClick={() => selectConnection(conn)}
                >
                  <span style={{ marginRight: '4px' }}>🔌</span>
                  {conn.source_db_name} {conn.status === 'connected' && '✓'}
                </button>
              ))}

              <button
                type="button"
                className={`db-tab-btn-add ${activeConnId === null ? 'active' : ''}`}
                onClick={initNewConnection}
              >
                <span>+</span> Add Connection
              </button>
            </div>

            <form onSubmit={handleSave}>
              <div className="modal-body">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                  <p style={{ margin: 0, fontSize: '0.80rem', color: 'var(--text-dim)' }}>
                    {activeConnId
                      ? `Editing saved connection: "${formData.source_db_name}"`
                      : 'Create a new named database connection for source table introspection.'}
                  </p>
                  {activeConnId && !isViewer && (
                    <button
                      type="button"
                      className="btn-delete-conn"
                      onClick={handleDeleteConnection}
                      disabled={deleting}
                      title="Remove this connection"
                      style={{ padding: '0.15rem 0.5rem', fontSize: '0.78rem' }}
                    >
                      🗑️ Delete
                    </button>
                  )}
                </div>

                <div className="db-grid-inputs">
                  {/* Row 1: Connection Name + Default Schema */}
                  <div className="form-group">
                    <label className="form-label" style={{ color: 'var(--primary)', fontWeight: 600, fontSize: '0.82rem', marginBottom: '0.25rem' }}>
                      Connection / Source DB Name *
                    </label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ border: '1px solid var(--border-focus)', background: 'var(--primary-subtle)', padding: '0.42rem 0.65rem' }}
                      placeholder="e.g. Primary_Warehouse, Oracle_Billing"
                      value={formData.source_db_name}
                      onChange={(e) => setFormData({ ...formData, source_db_name: e.target.value })}
                      required
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', marginBottom: '0.25rem' }}>
                      <span>Default Schema (Optional)</span>
                      <span style={{ fontSize: '0.72rem', color: '#94a3b8' }}>Auto-scans all</span>
                    </label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ padding: '0.42rem 0.65rem' }}
                      placeholder={formData.db_type === 'snowflake' ? 'PUBLIC (or blank)' : 'Auto-scans all schemas'}
                      value={formData.schema_name}
                      onChange={(e) => setFormData({ ...formData, schema_name: e.target.value })}
                    />
                  </div>

                  {/* Row 2: Database & Storage Type (span 2) */}
                  <div className="form-group" style={{ gridColumn: 'span 2' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem', flexWrap: 'wrap', gap: '0.25rem' }}>
                      <label className="form-label" style={{ margin: 0, fontSize: '0.82rem' }}>Database & Storage Type</label>
                      {/* Cloud Quick Presets as compact chips */}
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.3rem' }}>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ padding: '0.12rem 0.45rem', fontSize: '0.74rem', background: formData.db_type === 'azure_sql' ? 'rgba(14,165,233,0.2)' : undefined, borderColor: formData.db_type === 'azure_sql' ? '#0ea5e9' : undefined }}
                          onClick={() => setFormData((prev) => ({
                            ...prev,
                            db_type: 'azure_sql',
                            host: 'your-server.database.windows.net',
                            port: '1433',
                            schema_name: 'dbo',
                            username: 'cloudadmin'
                          }))}
                        >
                          🔷 Azure SQL
                        </button>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ padding: '0.12rem 0.45rem', fontSize: '0.74rem', background: formData.db_type === 'rds_postgres' ? 'rgba(234,88,12,0.2)' : undefined, borderColor: formData.db_type === 'rds_postgres' ? '#ea580c' : undefined }}
                          onClick={() => setFormData((prev) => ({
                            ...prev,
                            db_type: 'rds_postgres',
                            host: 'mydb.c12345.rds.amazonaws.com',
                            port: '5432',
                            schema_name: 'public',
                            username: 'postgres'
                          }))}
                        >
                          🟠 AWS RDS
                        </button>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ padding: '0.12rem 0.45rem', fontSize: '0.74rem', background: formData.db_type === 'snowflake' ? 'rgba(56,189,248,0.2)' : undefined, borderColor: formData.db_type === 'snowflake' ? '#38bdf8' : undefined }}
                          onClick={() => setFormData((prev) => ({
                            ...prev,
                            db_type: 'snowflake',
                            host: 'xy12345.us-east-1',
                            port: 'COMPUTE_WH',
                            database_name: 'ANALYTICS_DB',
                            schema_name: 'PUBLIC',
                            username: 'SF_USER'
                          }))}
                        >
                          ❄️ Snowflake
                        </button>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ padding: '0.12rem 0.45rem', fontSize: '0.74rem' }}
                          onClick={() => setFormData((prev) => ({
                            ...prev,
                            db_type: 'mssql',
                            host: 'localhost',
                            port: '1433',
                            schema_name: 'dbo',
                            username: 'sa'
                          }))}
                        >
                          🏢 MSSQL
                        </button>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ padding: '0.12rem 0.45rem', fontSize: '0.74rem' }}
                          onClick={() => setFormData((prev) => ({
                            ...prev,
                            db_type: 'mysql',
                            host: 'localhost',
                            port: '3306',
                            schema_name: 'mydb',
                            username: 'root'
                          }))}
                        >
                          🐬 MySQL
                        </button>
                      </div>
                    </div>

                    <select
                      className="form-input"
                      style={{ padding: '0.42rem 0.65rem' }}
                      value={formData.db_type}
                      onChange={(e) => setFormData({
                        ...formData,
                        db_type: e.target.value,
                        port: e.target.value === 'snowflake' ? (formData.port && isNaN(Number(formData.port)) ? formData.port : 'COMPUTE_WH') : (formData.port && !isNaN(Number(formData.port)) ? formData.port : '5432'),
                        schema_name: e.target.value === 'snowflake' ? (formData.schema_name === 'public' ? 'PUBLIC' : formData.schema_name) : formData.schema_name
                      })}
                    >
                      <optgroup label="AWS Cloud Databases">
                        <option value="rds_postgres">AWS RDS PostgreSQL / Aurora</option>
                        <option value="rds_mysql">AWS RDS MySQL / Aurora</option>
                        <option value="redshift">AWS Redshift</option>
                        <option value="rds_mssql">AWS RDS SQL Server</option>
                      </optgroup>
                      <optgroup label="Azure Cloud Databases">
                        <option value="azure_sql">Azure SQL Database / Synapse</option>
                        <option value="azure_postgres">Azure Database for PostgreSQL</option>
                        <option value="azure_mysql">Azure Database for MySQL</option>
                      </optgroup>
                      <optgroup label="Google Cloud Platform">
                        <option value="gcp_postgres">Google Cloud SQL (PostgreSQL)</option>
                        <option value="gcp_mysql">Google Cloud SQL (MySQL)</option>
                        <option value="bigquery">Google Cloud BigQuery</option>
                      </optgroup>
                      <optgroup label="Standard / Enterprise Engines">
                        <option value="postgresql">PostgreSQL</option>
                        <option value="mssql">Microsoft SQL Server (MSSQL)</option>
                        <option value="mysql">MySQL / MariaDB</option>
                        <option value="snowflake">Snowflake Data Cloud</option>
                        <option value="oracle">Oracle Database</option>
                        <option value="sqlite">SQLite / DuckDB</option>
                        <option value="sandbox">Sandbox (Simulated Cluster)</option>
                      </optgroup>
                    </select>
                  </div>

                  {/* Row 3: Host + Port */}
                  <div className="form-group">
                    <label className="form-label" style={{ marginBottom: '0.25rem', fontSize: '0.82rem' }}>
                      {formData.db_type === 'snowflake' ? 'Snowflake Account Identifier' : 'Host / IP'}
                    </label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ padding: '0.42rem 0.65rem' }}
                      placeholder={formData.db_type === 'snowflake' ? 'e.g. xy12345.us-east-1' : 'localhost or host IP'}
                      value={formData.host}
                      onChange={(e) => setFormData({ ...formData, host: e.target.value })}
                      disabled={formData.db_type === 'sandbox'}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label" style={{ marginBottom: '0.25rem', fontSize: '0.82rem' }}>
                      {formData.db_type === 'snowflake' ? 'Warehouse (Compute Cluster)' : 'Port'}
                    </label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ padding: '0.42rem 0.65rem' }}
                      placeholder={formData.db_type === 'snowflake' ? 'COMPUTE_WH' : '5432'}
                      value={formData.port}
                      onChange={(e) => setFormData({ ...formData, port: e.target.value })}
                      disabled={formData.db_type === 'sandbox'}
                    />
                  </div>

                  {/* Row 4: Database Name + Username */}
                  <div className="form-group">
                    <label className="form-label" style={{ marginBottom: '0.25rem', fontSize: '0.82rem' }}>Database Name</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ padding: '0.42rem 0.65rem' }}
                      placeholder={formData.db_type === 'snowflake' ? 'e.g. ANALYTICS_DB' : 'e.g. hla_db'}
                      value={formData.database_name}
                      onChange={(e) => setFormData({ ...formData, database_name: e.target.value })}
                    />
                  </div>

                  <div className="form-group">
                    <label className="form-label" style={{ marginBottom: '0.25rem', fontSize: '0.82rem' }}>Username</label>
                    <input
                      type="text"
                      className="form-input"
                      style={{ padding: '0.42rem 0.65rem' }}
                      placeholder={formData.db_type === 'snowflake' ? 'SF_USER' : 'postgres'}
                      value={formData.username}
                      onChange={(e) => setFormData({ ...formData, username: e.target.value })}
                      disabled={formData.db_type === 'sandbox'}
                    />
                  </div>

                  {/* Row 5: Password (span 2) */}
                  <div className="form-group" style={{ gridColumn: 'span 2' }}>
                    <label className="form-label" style={{ marginBottom: '0.25rem', fontSize: '0.82rem' }}>Password</label>
                    <input
                      type="password"
                      className="form-input"
                      style={{ padding: '0.42rem 0.65rem' }}
                      placeholder="Enter password (leave blank to keep existing)"
                      value={formData.password}
                      onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                      disabled={formData.db_type === 'sandbox'}
                    />
                  </div>
                </div>

                {testResult && (
                  <div className={`db-test-result ${testResult.success ? 'success' : 'error'}`} style={{ padding: '0.35rem 0.65rem', fontSize: '0.82rem', marginTop: '0.35rem' }}>
                    <span>{testResult.success ? '✓' : '✕'}</span>
                    <span>{testResult.message}</span>
                  </div>
                )}
              </div>

              <div className="modal-footer">
                <button
                  type="button"
                  className="btn-modal-cancel"
                  onClick={handleClose}
                >
                  Close
                </button>
                <button
                  type="button"
                  className="btn-modal-cancel"
                  onClick={handleTest}
                  disabled={testing}
                >
                  {testing ? 'Testing…' : '🔍 Test Connection'}
                </button>
                {!isViewer ? (
                  <button
                    type="submit"
                    className="btn-modal-submit"
                    disabled={saving}
                  >
                    {saving ? 'Saving…' : (activeConnId ? 'Update Connection' : 'Save Connection')}
                  </button>
                ) : (
                  <span style={{ fontSize: '0.8rem', color: '#64748b', fontStyle: 'italic' }}>
                    👁️ View-only mode: Architects & Admins can save DB credentials.
                  </span>
                )}
              </div>
            </form>
          </div>
        )}

        {/* ── Mode 2: Upload .kdb / Credential Vault File ── */}
        {managerMode === 'vault' && (
          <form onSubmit={handleVaultUpload}>
            <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem' }}>
              <p style={{ margin: 0, fontSize: '0.80rem', color: 'var(--text-muted)', lineHeight: 1.35 }}>
                Upload or paste a single <strong style={{ color: 'var(--primary)' }}>.kdb, .ini, .json, .yaml, or .xml</strong> credential vault file.
                The engine extracts named profile sections for source/target databases and verifies connectivity.
              </p>

              {/* File Dropzone */}
              <div className="vault-file-box" style={{ padding: '0.75rem 1rem' }}>
                <input
                  type="file"
                  id="vault-file-input"
                  accept=".kdb,.ini,.json,.yaml,.yml,.xml,.txt"
                  onChange={(e) => setVaultFile(e.target.files[0] || null)}
                  style={{ display: 'none' }}
                />
                <label htmlFor="vault-file-input" className="vault-drop-label" style={{ gap: '0.65rem' }}>
                  <span style={{ fontSize: '1.4rem' }}>📁</span>
                  <div>
                    <span style={{ color: '#ffffff', fontWeight: 700, fontSize: '0.85rem' }}>
                      {vaultFile ? vaultFile.name : 'Choose a .kdb / Vault file or drag & drop'}
                    </span>
                    <span style={{ display: 'block', fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                      Supports .kdb, .ini, .json, .yaml, KeePass .xml
                    </span>
                  </div>
                </label>
                {vaultFile && (
                  <button
                    type="button"
                    className="btn-clear-file"
                    onClick={() => setVaultFile(null)}
                    title="Remove file"
                  >
                    ✕
                  </button>
                )}
              </div>

              {/* Or Paste Raw Text */}
              <div className="vault-paste-box">
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                  <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 700 }}>
                    Or Paste Config Text:
                  </span>
                  <button
                    type="button"
                    className="btn-template-hint"
                    onClick={handleLoadSampleTemplate}
                    style={{ padding: '0.15rem 0.45rem', fontSize: '0.72rem' }}
                  >
                    Load Sample Template
                  </button>
                </div>
                <textarea
                  className="vault-textarea"
                  rows={4}
                  value={vaultText}
                  onChange={(e) => setVaultText(e.target.value)}
                  placeholder={`[source.Warehouse_DB]\nhost = localhost\nport = 5432\ndatabase = hla_db\nusername = postgres\npassword = ...\n\n[target.dev]\nschema = target_dev\n...`}
                />
              </div>

              {vaultResult && (
                <div className={`db-test-result ${vaultResult.success ? 'success' : 'error'}`}>
                  <span>{vaultResult.success ? '✓' : '✕'}</span>
                  <span>{vaultResult.message}</span>
                </div>
              )}
            </div>

            <div className="modal-footer">
              <button
                type="button"
                className="btn-modal-cancel"
                onClick={handleClose}
              >
                Close
              </button>
              {!isViewer ? (
                <button
                  type="submit"
                  className="btn-modal-submit"
                  disabled={importingVault}
                >
                  {importingVault ? 'Parsing & Verifying…' : '⚡ Parse & Import All Profiles'}
                </button>
              ) : (
                <span style={{ fontSize: '0.8rem', color: '#64748b', fontStyle: 'italic' }}>
                  👁️ View-only mode: Architects & Admins can import vault credentials.
                </span>
              )}
            </div>
          </form>
        )}
      </div>
    </div>
  )
}
