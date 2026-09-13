import React, { useState, useEffect } from 'react'
import axios from 'axios'
import './GlobalIntrospectModal.css'

export default function GlobalIntrospectModal({ isOpen, onClose }) {
  const [savedConnections, setSavedConnections] = useState([])
  const [selectedDb, setSelectedDb] = useState('local_pg') // 'local_pg' | custom connection name | 'custom'
  const [schemaName, setSchemaName] = useState('public')
  const [tableName, setTableName] = useState('users')

  // Custom connection state
  const [showCustomConfig, setShowCustomConfig] = useState(false)
  const [customConfig, setCustomConfig] = useState({
    source_db_name: 'Custom_Source_DB',
    db_type: 'postgresql',
    host: 'localhost',
    port: '5432',
    database_name: 'hla_db',
    username: 'postgres',
    password: '',
    schema_name: 'public',
  })

  // Connection test state
  const [testingConn, setTestingConn] = useState(false)
  const [connStatus, setConnStatus] = useState(null) // { success: bool, message: str }

  // Introspection state
  const [introspecting, setIntrospecting] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')
  const [activeResultTab, setActiveResultTab] = useState('columns') // 'columns', 'sample', 'ddl', 'reconciliation'
  const [copiedDdl, setCopiedDdl] = useState(false)

  useEffect(() => {
    if (isOpen) {
      loadSavedConnections()
    }
  }, [isOpen])

  const loadSavedConnections = async () => {
    try {
      const res = await axios.get('/api/projects')
      const projects = res.data || []
      const allConns = []
      const seenNames = new Set()

      for (const p of projects) {
        try {
          const cRes = await axios.get(`/api/projects/${p.id}/connections`)
          const conns = cRes.data || []
          conns.forEach(c => {
            if (!seenNames.has(c.source_db_name)) {
              seenNames.add(c.source_db_name)
              allConns.push(c)
            }
          })
        } catch (e) {
          // ignore individual project connection fetch error
        }
      }
      setSavedConnections(allConns)
    } catch (err) {
      console.error('Failed to load saved connections for introspector:', err)
    }
  }

  if (!isOpen) return null

  const handleSelectDb = (dbKey, connObj = null) => {
    setSelectedDb(dbKey)
    setConnStatus(null)
    setResult(null)
    setError('')

    if (dbKey === 'local_pg') {
      setSchemaName('public')
      setTableName('users')
      setShowCustomConfig(false)
    } else if (dbKey === 'custom') {
      setShowCustomConfig(true)
      setSchemaName(customConfig.schema_name || 'public')
    } else if (connObj) {
      setShowCustomConfig(true)
      setCustomConfig({
        source_db_name: connObj.source_db_name,
        db_type: connObj.db_type || 'postgresql',
        host: connObj.host || 'localhost',
        port: connObj.port ? String(connObj.port) : '5432',
        database_name: connObj.database_name || 'hla_db',
        username: connObj.username || 'postgres',
        password: '',
        schema_name: connObj.schema_name || 'public',
      })
      setSchemaName(connObj.schema_name || 'public')
      setTableName('')
    }
  }

  const handleQuickTable = (schema, table) => {
    setSchemaName(schema)
    setTableName(table)
    handleIntrospect(schema, table)
  }

  const handleTestConnection = async () => {
    setTestingConn(true)
    setConnStatus(null)
    try {
      const payload = {
        source_db_name: selectedDb === 'local_pg' ? 'local postgres' : customConfig.source_db_name,
        ...(selectedDb === 'local_pg' ? { use_local: true } : customConfig),
      }
      const res = await axios.post('/api/connections/test-global', payload)
      setConnStatus(res.data)
    } catch (err) {
      setConnStatus({
        success: false,
        message: err.response?.data?.error || 'Connection failed to respond.',
      })
    } finally {
      setTestingConn(false)
    }
  }

  const handleIntrospect = async (overrideSchema = null, overrideTable = null) => {
    const sName = overrideSchema || schemaName
    const tName = overrideTable || tableName

    if (!tName.trim()) {
      setError('Please provide a table name to introspect.')
      return
    }

    setIntrospecting(true)
    setError('')
    setResult(null)

    try {
      const payload = {
        source_db_name: selectedDb === 'local_pg' ? 'local postgres' : customConfig.source_db_name,
        schema_name: sName.trim() || 'public',
        table_name: tName.trim(),
        connection_config: selectedDb === 'local_pg' ? { use_local: true } : customConfig,
      }

      const res = await axios.post('/api/introspect-table', payload)
      setResult(res.data)
      setActiveResultTab('columns')
    } catch (err) {
      console.error('Introspection failed:', err)
      setError(err.response?.data?.error || 'Failed to introspect table schema.')
    } finally {
      setIntrospecting(false)
    }
  }

  const handleCopyDdl = () => {
    if (!result?.ddl) return
    navigator.clipboard.writeText(result.ddl)
    setCopiedDdl(true)
    setTimeout(() => setCopiedDdl(false), 2000)
  }

  // Match key analysis for Reconciliation Readiness
  const analyzeMatchKeys = () => {
    if (!result?.columns) return []
    const cols = result.columns.map(c => c.column_name.toLowerCase())
    const checks = []

    // IP Check
    const hasIp = cols.some(c => c.includes('ip'))
    checks.push({
      key: 'IP Address Field',
      detected: hasIp,
      fields: result.columns.filter(c => c.column_name.toLowerCase().includes('ip')).map(c => c.column_name),
      tier: 'Pass 1 (Exact Match)',
      readiness: hasIp ? 'ELIGIBLE' : 'NOT FOUND',
      notes: hasIp ? 'Enables high-confidence IP baseline reconciliation.' : 'Cannot perform exact IP match.',
    })

    // Hostname Check
    const hasHost = cols.some(c => c.includes('host'))
    checks.push({
      key: 'Host Name Field',
      detected: hasHost,
      fields: result.columns.filter(c => c.column_name.toLowerCase().includes('host')).map(c => c.column_name),
      tier: 'Pass 2 & 3 (Exact & Fuzzy)',
      readiness: hasHost ? 'ELIGIBLE' : 'NOT FOUND',
      notes: hasHost ? 'Enables secondary hostname & Levenshtein fuzzy matching.' : 'Hostname reconciliation unavailable.',
    })

    // Circuit / Order Check
    const hasCircuit = cols.some(c => c.includes('circuit') || c.includes('copf') || c.includes('order'))
    checks.push({
      key: 'Circuit & COPF Billing Keys',
      detected: hasCircuit,
      fields: result.columns.filter(c => c.column_name.toLowerCase().includes('circuit') || c.column_name.toLowerCase().includes('copf')).map(c => c.column_name),
      tier: 'Pass 4 (Revenue Assurance)',
      readiness: hasCircuit ? 'ELIGIBLE' : 'NOT FOUND',
      notes: hasCircuit ? 'Qualifies for revenue leakage cross-audit with billing feeds.' : 'Circuit tracking keys not identified.',
    })

    return checks
  }

  return (
    <div className="introspect-modal-overlay" onClick={onClose}>
      <div className="introspect-modal-card" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="introspect-modal-header">
          <div className="introspect-title-group">
            <div className="introspect-badge">
              <span>⚙️</span> LIVE DB INTROSPECTION ENGINE • DYNAMIC SCHEMA DISCOVERY
            </div>
            <h2>Universal Source Database Connector & Schema Introspector</h2>
            <p className="introspect-subtitle">
              Inspect live schemas, column data types, nullability, row volumes, and data previews across configured source databases or the local PostgreSQL database.
            </p>
          </div>
          <button className="introspect-close-btn" onClick={onClose} title="Close Introspector">
            ✕
          </button>
        </div>

        {/* Source DB Selection & Connection Ping Bar */}
        <div className="introspect-top-bar">
          <div className="db-selector-group">
            <span className="db-selector-label">Target Database:</span>

            {/* Local App DB */}
            <button
              className={`db-chip ${selectedDb === 'local_pg' ? 'active' : ''}`}
              onClick={() => handleSelectDb('local_pg')}
            >
              <span>🐘</span>
              <span>PostgreSQL 18 (Local App DB)</span>
            </button>

            {/* Dynamically Loaded Saved Connections */}
            {savedConnections.map(c => (
              <button
                key={c.id}
                className={`db-chip ${selectedDb === c.source_db_name ? 'active' : ''}`}
                onClick={() => handleSelectDb(c.source_db_name, c)}
              >
                <span>🔌</span>
                <span>{c.source_db_name}</span>
              </button>
            ))}

            {/* Custom Connection Chip */}
            <button
              className={`db-chip ${selectedDb === 'custom' ? 'active' : ''}`}
              onClick={() => handleSelectDb('custom')}
            >
              <span>⚙️</span>
              <span>Custom Connection</span>
            </button>
          </div>

          <button
            className="btn-ping-conn"
            onClick={handleTestConnection}
            disabled={testingConn}
          >
            <span>⚡</span>
            <span>{testingConn ? 'Pinging…' : 'Test Ping'}</span>
          </button>
        </div>

        {/* Connection status banner */}
        {connStatus && (
          <div className={`conn-status-banner ${connStatus.success ? 'success' : 'failed'}`}>
            <span>{connStatus.success ? '●' : '▲'}</span>
            <span>{connStatus.message}</span>
          </div>
        )}

        {/* Custom / Saved DB Config Drawer */}
        {showCustomConfig && (
          <div className="custom-config-drawer">
            <div className="custom-form-row">
              <div className="custom-field">
                <label>Connection Name</label>
                <input
                  type="text"
                  value={customConfig.source_db_name}
                  onChange={e => setCustomConfig({ ...customConfig, source_db_name: e.target.value })}
                  placeholder="e.g. Orders_DB"
                />
              </div>
              <div className="custom-field">
                <label>Database Type</label>
                <select
                  value={customConfig.db_type}
                  onChange={e => {
                    const newType = e.target.value
                    setCustomConfig({
                      ...customConfig,
                      db_type: newType,
                      port: newType === 'snowflake' ? (customConfig.port && isNaN(Number(customConfig.port)) ? customConfig.port : 'COMPUTE_WH') : (customConfig.port && !isNaN(Number(customConfig.port)) ? customConfig.port : '5432'),
                      schema_name: newType === 'snowflake' ? 'PUBLIC' : (customConfig.schema_name || 'public')
                    })
                  }}
                >
                  <option value="postgresql">PostgreSQL / AWS RDS</option>
                  <option value="mssql">Microsoft SQL Server / Azure SQL</option>
                  <option value="mysql">MySQL / Cloud SQL</option>
                  <option value="snowflake">Snowflake Data Cloud</option>
                  <option value="redshift">AWS Redshift</option>
                  <option value="oracle">Oracle Database</option>
                  <option value="sqlite">SQLite / DuckDB</option>
                  <option value="sandbox">Sandbox (Simulated)</option>
                </select>
              </div>
              <div className="custom-field">
                <label>{customConfig.db_type === 'snowflake' ? 'Snowflake Account' : 'Host'}</label>
                <input
                  type="text"
                  placeholder={customConfig.db_type === 'snowflake' ? 'e.g. xy12345.us-east-1' : 'localhost'}
                  value={customConfig.host}
                  onChange={e => setCustomConfig({ ...customConfig, host: e.target.value })}
                />
              </div>
              <div className="custom-field">
                <label>{customConfig.db_type === 'snowflake' ? 'Warehouse' : 'Port'}</label>
                <input
                  type="text"
                  value={customConfig.port}
                  placeholder={customConfig.db_type === 'snowflake' ? 'COMPUTE_WH' : '5432'}
                  onChange={e => setCustomConfig({ ...customConfig, port: e.target.value })}
                />
              </div>
              <div className="custom-field">
                <label>DB Name</label>
                <input
                  type="text"
                  placeholder={customConfig.db_type === 'snowflake' ? 'ANALYTICS_DB' : 'hla_db'}
                  value={customConfig.database_name}
                  onChange={e => setCustomConfig({ ...customConfig, database_name: e.target.value })}
                />
              </div>
              <div className="custom-field">
                <label>Username</label>
                <input
                  type="text"
                  placeholder={customConfig.db_type === 'snowflake' ? 'SF_USER' : 'postgres'}
                  value={customConfig.username}
                  onChange={e => setCustomConfig({ ...customConfig, username: e.target.value })}
                />
              </div>
              <div className="custom-field">
                <label>Password</label>
                <input
                  type="password"
                  placeholder="Password"
                  value={customConfig.password}
                  onChange={e => setCustomConfig({ ...customConfig, password: e.target.value })}
                />
              </div>
            </div>
          </div>
        )}

        {/* Table Selector & Quick Table Chips */}
        <div className="table-controls-bar">
          <div className="inputs-cluster">
            <div className="input-with-label">
              <label>Schema (Optional)</label>
              <input
                type="text"
                value={schemaName}
                onChange={e => setSchemaName(e.target.value)}
                placeholder="All schemas (auto-discover)"
                className="t-input"
              />
            </div>
            <div className="input-with-label" style={{ flex: 1.5 }}>
              <label>Physical Table Name</label>
              <input
                type="text"
                value={tableName}
                onChange={e => setTableName(e.target.value)}
                placeholder="e.g. users, customers, or billing_orders"
                className="t-input"
              />
            </div>
            <button
              className="btn-introspect-action"
              onClick={() => handleIntrospect()}
              disabled={introspecting}
            >
              <span>{introspecting ? '⏳' : '🚀'}</span>
              <span>{introspecting ? 'Introspecting Table…' : 'Introspect Table'}</span>
            </button>
          </div>

          {/* Quick Table Presets for Local DB */}
          {selectedDb === 'local_pg' && (
            <div className="quick-presets-row">
              <span className="preset-label">App Tables:</span>
              <button className="btn-table-pill" onClick={() => handleQuickTable('public', 'users')}>
                users
              </button>
              <button className="btn-table-pill" onClick={() => handleQuickTable('public', 'projects')}>
                projects
              </button>
              <button className="btn-table-pill" onClick={() => handleQuickTable('public', 'documents')}>
                documents
              </button>
              <button className="btn-table-pill" onClick={() => handleQuickTable('public', 'db_connections')}>
                db_connections
              </button>
              <button className="btn-table-pill" onClick={() => handleQuickTable('public', 'target_artifacts')}>
                target_artifacts
              </button>
            </div>
          )}
        </div>

        {/* Error Alert */}
        {error && (
          <div className="introspect-error-box">
            <span>⚠️</span>
            <span>{error}</span>
          </div>
        )}

        {/* ── Results Container ── */}
        {result ? (
          <div className="introspect-result-container">
            {/* Metadata Summary KPI Bar */}
            <div className="result-kpi-bar">
              <div className="kpi-block">
                <span className="kpi-k">Source Database</span>
                <span className="kpi-v highlight">{result.source_db || selectedDb}</span>
              </div>
              <div className="kpi-block">
                <span className="kpi-k">Full Table Identifier</span>
                <span className="kpi-v">{result.schema_name}.{result.table_name}</span>
              </div>
              <div className="kpi-block">
                <span className="kpi-k">Total Row Volume</span>
                <span className="kpi-v">{result.row_count ? result.row_count.toLocaleString() : '0'} rows</span>
              </div>
              <div className="kpi-block">
                <span className="kpi-k">Columns Count</span>
                <span className="kpi-v">{result.columns ? result.columns.length : 0} attributes</span>
              </div>
              <div className="kpi-block">
                <span className="kpi-k">Status</span>
                <span className={`kpi-tag ${result.is_simulated ? 'simulated' : 'live'}`}>
                  {result.is_simulated ? 'Simulated Schema' : 'Live PostgreSQL Data'}
                </span>
              </div>
            </div>

            {/* Results Tab Bar */}
            <div className="result-tabs-bar">
              <div className="result-tabs-left">
                <button
                  className={`rt-tab ${activeResultTab === 'columns' ? 'active' : ''}`}
                  onClick={() => setActiveResultTab('columns')}
                >
                  <span>📋</span> Column Schema & Types ({result.columns?.length || 0})
                </button>
                <button
                  className={`rt-tab ${activeResultTab === 'sample' ? 'active' : ''}`}
                  onClick={() => setActiveResultTab('sample')}
                >
                  <span>🔍</span> Live Sample Data ({result.sample_rows?.length || 0} rows)
                </button>
                <button
                  className={`rt-tab ${activeResultTab === 'ddl' ? 'active' : ''}`}
                  onClick={() => setActiveResultTab('ddl')}
                >
                  <span>🏛️</span> DDL Definition
                </button>
                <button
                  className={`rt-tab ${activeResultTab === 'reconciliation' ? 'active' : ''}`}
                  onClick={() => setActiveResultTab('reconciliation')}
                >
                  <span>⚖️</span> Reconciliation Readiness Check
                </button>
              </div>

              {activeResultTab === 'ddl' && (
                <button className="btn-copy-ddl" onClick={handleCopyDdl}>
                  <span>{copiedDdl ? '✓' : '📋'}</span>
                  <span>{copiedDdl ? 'Copied DDL' : 'Copy DDL'}</span>
                </button>
              )}
            </div>

            {/* Tab 1: Column Schema Table */}
            {activeResultTab === 'columns' && (
              <div className="result-table-wrapper">
                <table className="introspect-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Column Name</th>
                      <th>Physical Data Type</th>
                      <th>Nullable</th>
                      <th>Default Expression</th>
                      <th>Classification Tag</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.columns && result.columns.map((col, idx) => {
                      const cName = col.column_name.toLowerCase()
                      let tag = 'General Attribute'
                      let tagColor = 'var(--text-muted)'

                      if (cName.includes('ip') || cName.includes('host') || cName.includes('identity') || cName.includes('key') || cName.includes('pk') || cName.endsWith('_id') || cName === 'id') {
                        tag = 'Primary Match Identity'
                        tagColor = 'var(--cyan-400)'
                      } else if (cName.includes('code') || cName.includes('ref') || cName.includes('order') || cName.includes('num') || cName.includes('account')) {
                        tag = 'Composite Reference Key'
                        tagColor = 'var(--amber-400)'
                      } else if (cName.includes('charge') || cName.includes('mrc') || cName.includes('nrc') || cName.includes('cost')) {
                        tag = 'Financial Metric'
                        tagColor = 'var(--emerald-400)'
                      }

                      return (
                        <tr key={idx}>
                          <td style={{ color: 'var(--text-muted)' }}>{idx + 1}</td>
                          <td>
                            <strong className="code-text" style={{ color: '#ffffff' }}>
                              {col.column_name}
                            </strong>
                          </td>
                          <td>
                            <span className="type-badge">{col.data_type}</span>
                          </td>
                          <td>
                            <span className={`null-badge ${col.is_nullable === 'YES' ? 'yes' : 'no'}`}>
                              {col.is_nullable === 'YES' ? 'NULLABLE' : 'NOT NULL'}
                            </span>
                          </td>
                          <td className="code-text" style={{ fontSize: '0.76rem', color: 'var(--text-dim)' }}>
                            {col.default || '—'}
                          </td>
                          <td>
                            <span className="class-tag" style={{ color: tagColor, borderColor: `${tagColor}44`, background: `${tagColor}15` }}>
                              {tag}
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {/* Tab 2: Sample Rows Table */}
            {activeResultTab === 'sample' && (
              <div className="result-table-wrapper">
                {result.sample_rows && result.sample_rows.length > 0 ? (
                  <table className="introspect-table">
                    <thead>
                      <tr>
                        {Object.keys(result.sample_rows[0]).map((k) => (
                          <th key={k}>{k}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.sample_rows.map((row, rIdx) => (
                        <tr key={rIdx}>
                          {Object.values(row).map((val, vIdx) => (
                            <td key={vIdx} className="code-text" style={{ fontSize: '0.78rem' }}>
                              {val !== null && val !== undefined ? String(val) : <span style={{ color: 'var(--text-muted)', fontStyle: 'italic' }}>NULL</span>}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                ) : (
                  <div className="empty-sample-box">
                    <span>⚠️ No sample records available or table is empty.</span>
                  </div>
                )}
              </div>
            )}

            {/* Tab 3: DDL Definition */}
            {activeResultTab === 'ddl' && (
              <div className="ddl-code-box">
                <pre>
                  <code>{result.ddl || '-- No DDL generated'}</code>
                </pre>
              </div>
            )}

            {/* Tab 4: Reconciliation Readiness Check */}
            {activeResultTab === 'reconciliation' && (
              <div className="recon-readiness-panel">
                <div className="readiness-header">
                  <h4>Target Balance & Reconciliation Suitability Analysis</h4>
                  <p>
                    Evaluates whether table <strong>{result.table_name}</strong> has the required composite identity keys to support R12 tiered matching and R15 revenue assurance ledgers:
                  </p>
                </div>

                <div className="readiness-cards-grid">
                  {analyzeMatchKeys().map((check, idx) => (
                    <div key={idx} className={`readiness-card ${check.detected ? 'passed' : 'missing'}`}>
                      <div className="rc-top">
                        <span className="rc-tier">{check.tier}</span>
                        <span className={`rc-badge ${check.readiness.toLowerCase()}`}>
                          {check.detected ? '✓ READY' : '✕ MISSING'}
                        </span>
                      </div>
                      <h5 className="rc-title">{check.key}</h5>
                      <p className="rc-notes">{check.notes}</p>
                      {check.detected && (
                        <div className="rc-fields">
                          <span>Detected fields: </span>
                          <strong>{check.fields.join(', ')}</strong>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Empty State */
          <div className="introspect-empty-state">
            <span className="empty-icon">🔍</span>
            <h3>No Table Introspected Yet</h3>
            <p>
              Select a database connection above, specify the schema and physical table name, and click <strong>"Introspect Table"</strong> to examine live column types, nullability, and sample rows.
            </p>
          </div>
        )}

        {/* Modal Footer */}
        <div className="introspect-modal-footer">
          <span className="footer-status-text">
            Live Schema Extractor • Compliant with Enterprise ETL Target Architecture
          </span>
          <button className="btn-modal-done" onClick={onClose}>
            Done
          </button>
        </div>
      </div>
    </div>
  )
}
