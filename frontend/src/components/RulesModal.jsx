import React, { useState, useEffect } from 'react'
import axios from 'axios'
import { copyToClipboard } from '../utils/clipboard'
import './RulesModal.css'

export default function RulesModal({ isOpen, onClose, activeDocRules = null, documentId = null }) {
  const [rules, setRules] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('filters') // 'filters', 'balance', 'all', 'simulator', 'extracted'
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedStream, setSelectedStream] = useState('ALL')
  const [copiedRuleId, setCopiedRuleId] = useState(null)
  const [expandedSql, setExpandedSql] = useState({})

  // Simulator state
  const [simRecord, setSimRecord] = useState({
    host_name: '',
    ip: '',
    vdom: 'partition_1',
    profile_name: '',
    circuit_id: 'REC-9921',
    copf_id: 'ORD-1092834',
    status: 'ACTIVE',
  })
  const [simResults, setSimResults] = useState(null)

  useEffect(() => {
    if (!isOpen) return
    fetchCatalog()
  }, [isOpen, documentId])

  const fetchCatalog = async () => {
    setLoading(true)
    setError('')
    try {
      const url = documentId ? `/api/rules/catalog?document_id=${documentId}` : '/api/rules/catalog'
      const res = await axios.get(url)
      setRules(res.data.rules || [])
    } catch (err) {
      console.error('Failed to load rules catalog:', err)
      setError('Could not load enterprise rules catalog.')
    } finally {
      setLoading(false)
    }
  }

  if (!isOpen) return null

  const handleCopySql = async (ruleId, sql) => {
    const ok = await copyToClipboard(sql)
    if (ok) {
      setCopiedRuleId(ruleId)
      setTimeout(() => setCopiedRuleId(null), 2000)
    }
  }

  const toggleSql = (ruleId) => {
    setExpandedSql(prev => ({ ...prev, [ruleId]: !prev[ruleId] }))
  }

  // Filter logic
  const filteredRules = rules.filter(r => {
    // Tab filter
    if (activeTab === 'filters') {
      const num = parseInt(r.rule_id.replace('R', ''), 10)
      if (num < 1 || num > 10) return false
    } else if (activeTab === 'balance') {
      const num = parseInt(r.rule_id.replace('R', ''), 10)
      if (num < 11) return false
    }

    // Stream filter
    if (selectedStream !== 'ALL') {
      if (!r.stream.toLowerCase().includes(selectedStream.toLowerCase())) return false
    }

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      return (
        r.rule_id.toLowerCase().includes(q) ||
        r.name.toLowerCase().includes(q) ||
        r.stream.toLowerCase().includes(q) ||
        r.description.toLowerCase().includes(q) ||
        r.category.toLowerCase().includes(q)
      )
    }
    return true
  })

  // Dynamic streams extracted from loaded rules
  const availableStreams = ['ALL', ...Array.from(new Set(rules.map(r => r.stream || r.data_stream).filter(Boolean)))]

  // Preset loader for simulator
  const loadPreset = (type) => {
    if (type === 'valid') {
      setSimRecord({
        host_name: 'FW-MUM-VUTM-01',
        ip: '10.142.18.5',
        vdom: 'VUTM_CORP',
        profile_name: 'HDFC_CORP_GW',
        circuit_id: 'SN-MUM-9921',
        copf_id: 'ON1092834',
        status: 'ACTIVE'
      })
    } else if (type === 'null_host_ip') {
      setSimRecord({
        host_name: '',
        ip: '',
        vdom: 'root',
        profile_name: 'TEST_GW',
        circuit_id: 'SN-MUM-9921',
        copf_id: 'ON1092834',
        status: 'ACTIVE'
      })
    } else if (type === 'dummy_ip') {
      setSimRecord({
        host_name: 'FW-DEV-01',
        ip: '0.0.0.0',
        vdom: 'DEV',
        profile_name: 'INTERNAL_DEV',
        circuit_id: 'SN-DEL-1024',
        copf_id: 'MDDOS88219',
        status: 'ACTIVE'
      })
    } else if (type === 'lab_profile') {
      setSimRecord({
        host_name: 'FW-LAB-TEST-02',
        ip: '10.200.1.15',
        vdom: 'TEST_VDOM',
        profile_name: 'LAB_TEST_PROFILE',
        circuit_id: 'SN-BLR-5542',
        copf_id: 'ON7732190',
        status: 'ACTIVE'
      })
    } else if (type === 'decommissioned') {
      setSimRecord({
        host_name: 'OLD-FW-HYD-99',
        ip: '172.16.88.4',
        vdom: 'DECOMM',
        profile_name: 'RETIRED_PROFILE',
        circuit_id: 'SN-HYD-0012',
        copf_id: 'OLD99812',
        status: 'DECOMMISSIONED'
      })
    }
    setSimResults(null)
  }

  const runSimulation = () => {
    const findings = []
    let passedAll = true

    // Mandatory key check
    if (!simRecord.host_name.trim() && !simRecord.ip.trim()) {
      findings.push({
        rule: 'Mandatory Null Integrity Check',
        verdict: 'FAIL',
        reason: 'Both primary identifiers (Host/Entity and IP/Key) are NULL/empty.',
        action: 'DROPPED by Pre-Execution Filter'
      })
      passedAll = false
    } else {
      findings.push({
        rule: 'Mandatory Null Integrity Check',
        verdict: 'PASS',
        reason: 'Mandatory identification keys present.',
        action: 'Retained'
      })
    }

    // Dummy parameter exclusion test
    const dummyIps = ['0.0.0.0', '1.1.1.1', '127.0.0.1', '0.0.0.1', '255.255.255.255']
    if (dummyIps.includes(simRecord.ip.trim())) {
      findings.push({
        rule: 'Configurable Dummy / Exclusion Parameter Filter',
        verdict: 'FAIL',
        reason: `Value '${simRecord.ip}' is identified as test/dummy placeholder parameter.`,
        action: 'EXCLUDED from reconciliation pool'
      })
      passedAll = false
    } else {
      findings.push({
        rule: 'Configurable Dummy / Exclusion Parameter Filter',
        verdict: 'PASS',
        reason: 'Value passed exclusion verification.',
        action: 'Retained'
      })
    }

    // Exclusion profile test
    if (simRecord.profile_name.toUpperCase().includes('LAB_TEST') || simRecord.profile_name.toUpperCase().includes('DUMMY') || simRecord.profile_name.toUpperCase().includes('SANDBOX')) {
      findings.push({
        rule: 'Environment Exclusion Filter',
        verdict: 'FAIL',
        reason: `Profile '${simRecord.profile_name}' matched exclusion pattern 'LAB_TEST% / DUMMY% / SANDBOX%'.`,
        action: 'EXCLUDED from reconciliation'
      })
      passedAll = false
    } else {
      findings.push({
        rule: 'Environment Exclusion Filter',
        verdict: 'PASS',
        reason: 'Production entity profile verified.',
        action: 'Retained'
      })
    }

    // Status lifecycle test
    if (['DECOMMISSIONED', 'RETIRED', 'INACTIVE', 'CANCELLED'].includes(simRecord.status.toUpperCase())) {
      findings.push({
        rule: 'Lifecycle Status Scope Filter',
        verdict: 'FAIL',
        reason: `Lifecycle status '${simRecord.status}' is marked decommissioned/inactive.`,
        action: 'DROPPED from active baseline'
      })
      passedAll = false
    } else {
      findings.push({
        rule: 'Lifecycle Status Scope Filter',
        verdict: 'PASS',
        reason: `Active operational status verified.`,
        action: 'Retained'
      })
    }

    // R11 Outcome
    if (passedAll) {
      findings.push({
        rule: 'R11 (Balance Dataset Gate)',
        verdict: 'PASSED_GATE',
        reason: 'Record passed all R1–R10 pre-execution checks without rejection.',
        action: 'STAGED into CTRL_X_BALANCED_DATASET_A'
      })
    } else {
      findings.push({
        rule: 'R11 (Balance Dataset Gate)',
        verdict: 'REJECTED',
        reason: 'One or more upstream filters rejected this record.',
        action: 'ROUTED to Quarantine / Discard Log'
      })
    }

    setSimResults({ passedAll, findings })
  }

  return (
    <div className="rules-modal-overlay" onClick={onClose}>
      <div className="rules-modal-card" onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div className="rules-modal-header">
          <div className="rules-modal-title-group">
            <div className="rules-badge">
              <span>🧠</span> ETL RULE ENGINE • PRE-EXECUTION & BALANCE RECONCILIATION
            </div>
            <h2>R1–R10 Filter Rules & R11 Balance Dataset Catalog</h2>
            <p className="rules-modal-subtitle">
              Enterprise architecture rule specifications extracted from client HLA designs. Inspect logic, copy SQL queries, or simulate record evaluation.
            </p>
          </div>
          <button className="rules-close-btn" onClick={onClose} title="Close rules catalog">
            ✕
          </button>
        </div>

        {/* Top Segmented Navigation Tabs */}
        <div className="rules-nav-bar">
          <div className="rules-tabs-group">
            <button
              className={`rules-nav-tab ${activeTab === 'filters' ? 'active' : ''}`}
              onClick={() => setActiveTab('filters')}
            >
              🎯 Filter Rules (R1–R10)
            </button>
            <button
              className={`rules-nav-tab ${activeTab === 'balance' ? 'active' : ''}`}
              onClick={() => setActiveTab('balance')}
            >
              ⚖️ Balance & Recon (R11–R15)
            </button>
            <button
              className={`rules-nav-tab ${activeTab === 'all' ? 'active' : ''}`}
              onClick={() => setActiveTab('all')}
            >
              📚 All Master Rules ({rules.length})
            </button>
            <button
              className={`rules-nav-tab ${activeTab === 'simulator' ? 'active' : ''}`}
              onClick={() => setActiveTab('simulator')}
            >
              ⚡ Live Rule Evaluator
            </button>
            {activeDocRules && activeDocRules.length > 0 && (
              <button
                className={`rules-nav-tab ${activeTab === 'extracted' ? 'active' : ''}`}
                onClick={() => setActiveTab('extracted')}
              >
                📄 Extracted from Active Doc ({activeDocRules.length})
              </button>
            )}
          </div>

          {activeTab !== 'simulator' && (
            <div className="rules-search-wrap">
              <span className="search-icon">🔍</span>
              <input
                type="text"
                placeholder="Search rule ID, table, or keywords..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="rules-search-input"
              />
              {searchQuery && (
                <button className="clear-search-btn" onClick={() => setSearchQuery('')}>✕</button>
              )}
            </div>
          )}
        </div>

        {/* Stream Filter Pills */}
        {activeTab !== 'simulator' && activeTab !== 'extracted' && (
          <div className="stream-filter-row">
            <span className="stream-filter-label">Filter by Data Stream:</span>
            {availableStreams.map(stream => (
              <button
                key={stream}
                className={`stream-pill ${selectedStream === stream ? 'active' : ''}`}
                onClick={() => setSelectedStream(stream)}
              >
                {stream}
              </button>
            ))}
          </div>
        )}

        {/* Modal Body Content */}
        <div className="rules-modal-body">
          {loading ? (
            <div className="rules-loading-state">
              <div className="spinner-cyan" />
              <span>Loading enterprise rule specifications…</span>
            </div>
          ) : error ? (
            <div className="rules-error-state">
              <span>⚠️</span> {error}
            </div>
          ) : activeTab === 'simulator' ? (
            /* ── Interactive Simulator View ── */
            <div className="rules-simulator-view">
              <div className="simulator-intro-box">
                <div className="sim-badge">INTERACTIVE TEST BENCH</div>
                <h3>Simulate Pre-Execution Filtering & Balance Gatekeeper</h3>
                <p>
                  Input sample record values or pick an enterprise preset to see how the ETL rule engine evaluates and either retains, excludes, or drops the record before reaching the Balance Dataset.
                </p>

                <div className="preset-buttons-row">
                  <span style={{ fontSize: '0.8rem', color: '#94a3b8', fontWeight: 600 }}>Quick Presets:</span>
                  <button className="btn-sim-preset valid" onClick={() => loadPreset('valid')}>
                    ✅ Valid Production Record
                  </button>
                  <button className="btn-sim-preset danger" onClick={() => loadPreset('null_host_ip')}>
                    ❌ Null Primary Identifiers
                  </button>
                  <button className="btn-sim-preset warning" onClick={() => loadPreset('dummy_ip')}>
                    ⚠️ Dummy Parameter (0.0.0.0)
                  </button>
                  <button className="btn-sim-preset warning" onClick={() => loadPreset('lab_profile')}>
                    🧪 Lab / Test Profile
                  </button>
                  <button className="btn-sim-preset danger" onClick={() => loadPreset('decommissioned')}>
                    🛑 Decommissioned Lifecycle
                  </button>
                </div>
              </div>

              <div className="sim-grid">
                {/* Inputs Form */}
                <div className="sim-card-form">
                  <h4 style={{ margin: '0 0 1rem 0', color: '#00f2fe', fontSize: '0.95rem' }}>
                    📝 Staged Telemetry Record Attributes
                  </h4>

                  <div className="sim-form-group">
                    <label>Primary Key / Host (Key_1)</label>
                    <input
                      type="text"
                      placeholder="e.g. ENTITY-NODE-01"
                      value={simRecord.host_name}
                      onChange={e => setSimRecord({ ...simRecord, host_name: e.target.value })}
                    />
                  </div>

                  <div className="sim-form-group">
                    <label>Secondary Key / Address (Key_2)</label>
                    <input
                      type="text"
                      placeholder="e.g. 10.142.18.5"
                      value={simRecord.ip}
                      onChange={e => setSimRecord({ ...simRecord, ip: e.target.value })}
                    />
                  </div>

                  <div className="sim-form-row">
                    <div className="sim-form-group">
                      <label>Sub-Domain / Stream Partition</label>
                      <input
                        type="text"
                        placeholder="e.g. partition_1"
                        value={simRecord.vdom}
                        onChange={e => setSimRecord({ ...simRecord, vdom: e.target.value })}
                      />
                    </div>
                    <div className="sim-form-group">
                      <label>Profile / Tenant</label>
                      <input
                        type="text"
                        placeholder="e.g. PROD_GW_01"
                        value={simRecord.profile_name}
                        onChange={e => setSimRecord({ ...simRecord, profile_name: e.target.value })}
                      />
                    </div>
                  </div>

                  <div className="sim-form-row">
                    <div className="sim-form-group">
                      <label>Record / Entity ID</label>
                      <input
                        type="text"
                        value={simRecord.circuit_id}
                        onChange={e => setSimRecord({ ...simRecord, circuit_id: e.target.value })}
                      />
                    </div>
                    <div className="sim-form-group">
                      <label>Asset Status</label>
                      <select
                        value={simRecord.status}
                        onChange={e => setSimRecord({ ...simRecord, status: e.target.value })}
                        className="sim-select"
                      >
                        <option value="ACTIVE">ACTIVE</option>
                        <option value="PROVISIONED">PROVISIONED</option>
                        <option value="DECOMMISSIONED">DECOMMISSIONED</option>
                        <option value="RETIRED">RETIRED</option>
                        <option value="INACTIVE">INACTIVE</option>
                      </select>
                    </div>
                  </div>

                  <button className="btn-run-sim" onClick={runSimulation}>
                    ⚡ Run Rule Evaluation Engine
                  </button>
                </div>

                {/* Simulation Output */}
                <div className="sim-card-results">
                  <h4 style={{ margin: '0 0 1rem 0', color: '#f8fafc', fontSize: '0.95rem' }}>
                    📊 Rule Engine Execution Breakdown
                  </h4>

                  {!simResults ? (
                    <div className="sim-empty-results">
                      <span style={{ fontSize: '2.5rem', marginBottom: '0.5rem' }}>🧪</span>
                      <p>Click "Run Rule Evaluation Engine" or select a preset to evaluate this record.</p>
                    </div>
                  ) : (
                    <div>
                      {/* Overall Verdict Banner */}
                      <div className={`sim-verdict-banner ${simResults.passedAll ? 'pass' : 'fail'}`}>
                        <span style={{ fontSize: '1.4rem' }}>{simResults.passedAll ? '✅' : '🛑'}</span>
                        <div>
                          <h4 style={{ margin: 0 }}>
                            {simResults.passedAll
                              ? 'CLEARED FOR BALANCE DATASET (R11)'
                              : 'RECORD REJECTED BY ETL FILTER'}
                          </h4>
                          <p style={{ margin: '0.2rem 0 0 0', fontSize: '0.8rem', opacity: 0.9 }}>
                            {simResults.passedAll
                              ? 'All pre-execution assertions passed. Record qualifies for reconciliation node.'
                              : 'One or more data quality or exclusion rules flagged this record.'}
                          </p>
                        </div>
                      </div>

                      {/* Rule by Rule breakdown */}
                      <div className="sim-rule-list">
                        {simResults.findings.map((f, i) => (
                          <div
                            key={i}
                            className={`sim-rule-item ${f.verdict === 'PASS' || f.verdict === 'PASSED_GATE' ? 'pass' : 'fail'}`}
                          >
                            <div className="sim-item-head">
                              <span className="sim-rule-name">{f.rule}</span>
                              <span className={`sim-pill ${f.verdict.toLowerCase()}`}>
                                {f.verdict}
                              </span>
                            </div>
                            <div className="sim-item-reason">{f.reason}</div>
                            <div className="sim-item-action">
                              <strong>Action:</strong> {f.action}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ) : activeTab === 'extracted' ? (
            /* ── Active Document Extracted Rules View ── */
            <div className="rules-cards-grid">
              {activeDocRules.map((r, idx) => (
                <div key={idx} className="rule-card">
                  <div className="rule-card-header">
                    <span className="rule-id-pill">{r.rule_id || `R${idx + 1}`}</span>
                    <span className="rule-name">{r.category || 'Extracted Rule'}</span>
                    <span className="rule-stream-tag">{r.data_stream || 'General'}</span>
                  </div>
                  <p className="rule-statement">{r.rule_statement || r.description}</p>
                </div>
              ))}
            </div>
          ) : (
            /* ── Master Rules List View ── */
            <div className="rules-cards-grid">
              {filteredRules.length === 0 ? (
                <div className="rules-empty-state">
                  <span>🔍</span> No rules matched your filter criteria.
                </div>
              ) : (
                filteredRules.map(rule => {
                  const isBal = parseInt(rule.rule_id.replace('R', ''), 10) >= 11
                  const isExpanded = expandedSql[rule.rule_id]
                  return (
                    <div key={rule.rule_id} className={`rule-card ${isBal ? 'balance-border' : ''}`}>
                      <div className="rule-card-header">
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                          <span className={`rule-id-pill ${isBal ? 'balance-pill' : ''}`}>
                            {rule.rule_id}
                          </span>
                          <span className="rule-name">{rule.name}</span>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <span className="rule-stream-tag">{rule.stream}</span>
                          <span className={`rule-severity-pill ${rule.severity.toLowerCase().replace(/\s+/g, '-')}`}>
                            {rule.severity}
                          </span>
                        </div>
                      </div>

                      <div className="rule-target-row">
                        <span className="rule-target-label">Target Dataset:</span>
                        <code>{rule.target_table}</code>
                      </div>

                      <p className="rule-description">{rule.description}</p>
                      <p className="rule-statement">{rule.statement}</p>

                      <div className="rule-impact-box">
                        <span className="impact-icon">⚡</span>
                        <span><strong>Impact:</strong> {rule.impact}</span>
                      </div>

                      {/* SQL Code Block */}
                      <div className="rule-sql-section">
                        <div className="sql-header-bar">
                          <button
                            className="btn-toggle-sql"
                            onClick={() => toggleSql(rule.rule_id)}
                          >
                            <span>{isExpanded ? '▼' : '▶'}</span>
                            <span>{isExpanded ? 'Hide SQL Logic' : 'View SQL Query Logic'}</span>
                          </button>
                          <button
                            className="btn-copy-sql"
                            onClick={() => handleCopySql(rule.rule_id, rule.sql_sample)}
                            title="Copy SQL implementation"
                          >
                            {copiedRuleId === rule.rule_id ? '✓ Copied!' : '📋 Copy SQL'}
                          </button>
                        </div>

                        {isExpanded && (
                          <pre className="sql-code-block">
                            <code>{rule.sql_sample}</code>
                          </pre>
                        )}
                      </div>
                    </div>
                  )
                })
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="rules-modal-footer">
          <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
            Enterprise Zero-Trust ETL Specification • Standard R1–R15 HLA Compliance
          </span>
          <button className="rules-btn-primary" onClick={onClose}>
            Close Catalog
          </button>
        </div>
      </div>
    </div>
  )
}
