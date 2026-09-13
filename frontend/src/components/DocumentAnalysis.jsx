import { useState, useEffect } from 'react'
import axios from 'axios'
import SourceDBManager from './SourceDBManager'
import TableSchemaModal from './TableSchemaModal'
import './DocumentAnalysis.css'

export default function DocumentAnalysis({ documentId, projectId, onRefreshList, currentUser }) {
  const [doc, setDoc] = useState(null)
  const [loading, setLoading] = useState(false)
  const [analyzing, setAnalyzing] = useState(false)
  const [activeTab, setActiveTab] = useState('pipeline') // 'pipeline' | 'sources' | 'rules' | 'mappings' | 'synthesis'
  const [mappingFilter, setMappingFilter] = useState('all') // 'all' | 'direct' | 'derived'
  const [searchQuery, setSearchQuery] = useState('')
  const [errorMsg, setErrorMsg] = useState('')

  const canAnalyze = currentUser && ['admin', 'architect'].includes(currentUser.role?.toLowerCase())

  // Source DB Connection & Live Schema inspection states
  const [showDBManager, setShowDBManager] = useState(false)
  const [selectedTableSchema, setSelectedTableSchema] = useState(null)
  const [fetchingSchemaTable, setFetchingSchemaTable] = useState(null)

  useEffect(() => {
    if (documentId) {
      fetchDocDetails(documentId)
    }
  }, [documentId])

  const fetchDocDetails = async (id) => {
    setLoading(true)
    setErrorMsg('')
    try {
      const res = await axios.get(`/api/documents/${id}`)
      setDoc(res.data)
    } catch (err) {
      setErrorMsg('Failed to load document details.')
    } finally {
      setLoading(false)
    }
  }

  const handleTriggerAnalysis = async () => {
    if (!doc) return
    setAnalyzing(true)
    setErrorMsg('')
    try {
      const res = await axios.post(`/api/documents/${doc.id}/analyze`)
      if (res.data && res.data.analysis) {
        setDoc((prev) => ({
          ...prev,
          status: 'analyzed',
          analysis: res.data.analysis,
        }))
        if (onRefreshList) onRefreshList()
      }
    } catch (err) {
      setErrorMsg(err.response?.data?.error || 'Analysis execution failed.')
    } finally {
      setAnalyzing(false)
    }
  }

  const handleFetchTableSchema = async (src) => {
    const tableKey = `${src.source_schema}.${src.source_table}`
    setFetchingSchemaTable(tableKey)
    try {
      const pId = projectId || doc?.project_id || 1
      const res = await axios.post(`/api/projects/${pId}/fetch-table-schema`, {
        source_db_name: src.source_db,
        schema_name: src.source_schema,
        table_name: src.source_table,
      })
      setSelectedTableSchema(res.data)
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to fetch table schema from source database.')
    } finally {
      setFetchingSchemaTable(null)
    }
  }

  if (loading) {
    return (
      <div className="analysis-dashboard">
        <div className="dashboard-loading-box">
          <div className="spinner-cyan" />
          <span>Loading solution architecture details…</span>
        </div>
      </div>
    )
  }

  if (!doc) return null

  const analysis = doc.analysis || {}
  const sources = analysis.sources || []
  const rules = analysis.rules || {}
  const inputStreams = rules.input_streams || []
  const filterRules = rules.filter_rules || []
  const balanceRules = rules.balance_rules || []
  const reconciliationFlows = rules.reconciliation_flows || []
  const mappings = analysis.mappings || []
  const summaryCounts = analysis.summary_counts || {}
  const llmSynthesis = analysis.llm_synthesis || {}

  const templateCompliance = analysis.template_compliance || {}
  const controlOverview = analysis.control_overview || {}
  const ctrlId = controlOverview.identification || {}
  const extractionRequirements = analysis.extraction_requirements || []
  const filtrationSteps = rules.filtration_steps || []
  const configTables = analysis.config_tables || []
  const reportInventory = analysis.report_inventory || []
  const dataModel = analysis.data_model || []
  const buckets = analysis.buckets || []
  const derivedFields = analysis.derived_fields || []

  const distinctSourceDBs = Array.from(new Set(sources.map((s) => s.source_db).filter(Boolean)))

  // Filter mappings
  const filteredMappings = mappings.filter((m) => {
    if (mappingFilter === 'direct' && m.mapping_type !== 'Direct') return false
    if (mappingFilter === 'derived' && m.mapping_type !== 'Derived') return false
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      const matchCol = m.target_column?.toLowerCase().includes(q)
      const matchSrc = m.source_field?.toLowerCase().includes(q)
      const matchTbl = m.source_table?.toLowerCase().includes(q)
      const matchLogic = m.derivation_logic?.toLowerCase().includes(q)
      return matchCol || matchSrc || matchTbl || matchLogic
    }
    return true
  })

  return (
    <section className="analysis-dashboard" id="analysis-dashboard">
      {/* ── Document Control Header ── */}
      <div className="doc-control-bar">
        <div className="doc-info-block">
          <div className="doc-badge-icon">HLA</div>
          <div className="doc-title-group">
            <h2>{doc.original_name || doc.filename}</h2>
            <div className="doc-meta-tags">
              <span className={`status-pill ${doc.status}`}>{doc.status || 'uploaded'}</span>
              <span>{(doc.file_size / 1024).toFixed(1)} KB</span>
              <span>Doc #{doc.id}</span>
              {doc.uploaded_at && (
                <span>Uploaded {new Date(doc.uploaded_at).toLocaleDateString()}</span>
              )}
              {templateCompliance.compliance_score !== undefined && (
                <span
                  style={{
                    background: templateCompliance.is_compliant ? 'rgba(5, 213, 179, 0.15)' : 'rgba(255, 184, 0, 0.15)',
                    color: templateCompliance.is_compliant ? '#05d5b3' : '#ffb800',
                    border: `1px solid ${templateCompliance.is_compliant ? 'rgba(5, 213, 179, 0.4)' : 'rgba(255, 184, 0, 0.4)'}`,
                    padding: '0.15rem 0.55rem',
                    borderRadius: '999px',
                    fontWeight: '700',
                    fontSize: '0.72rem'
                  }}
                  title={templateCompliance.missing_sections?.length ? `Missing: ${templateCompliance.missing_sections.join(', ')}` : 'Conforms to all 13 standard tables'}
                >
                  {templateCompliance.is_compliant ? `✓ Template Compliant (${templateCompliance.compliance_score}%)` : `⚠️ ${templateCompliance.compliance_score}% Compliant`}
                </span>
              )}
            </div>
          </div>
        </div>

        <div className="doc-actions-cluster">
          {canAnalyze && (
            <button
              className="action-btn btn-analyze"
              onClick={handleTriggerAnalysis}
              disabled={analyzing}
              id="btn-run-analysis"
            >
              <span>{analyzing ? '⏳' : '⚡'}</span>
              <span>{analyzing ? 'Analyzing with AI…' : 'Run AI Architecture Analysis'}</span>
            </button>
          )}

          <button
            className="action-btn btn-open-db"
            onClick={() => setShowDBManager(true)}
            id="btn-open-db-config"
          >
            <span>⚙️</span>
            <span>Source DBs ({distinctSourceDBs.length})</span>
          </button>
        </div>
      </div>

      {errorMsg && (
        <div className="analysis-error-banner">
          <span>⚠️</span> {errorMsg}
        </div>
      )}

      {/* ── If Analyzed: Show Metrics, Interactive Lineage Flow, & Tabs ── */}
      {doc.status === 'analyzed' && (
        <>
          {/* Executive Metrics Ribbon */}
          <div className="metrics-ribbon">
            <div className="metric-card cyan">
              <span className="metric-label">Source Datasets</span>
              <span className="metric-value">{summaryCounts.total_sources || sources.length}</span>
              <span className="metric-sub">
                {summaryCounts.truncate_sources || 0} Truncate · {summaryCounts.append_sources || 0} Append
              </span>
            </div>

            <div className="metric-card teal">
              <span className="metric-label">Filter Rules (R1–R10)</span>
              <span className="metric-value">{summaryCounts.filter_rules || filterRules.length}</span>
              <span className="metric-sub">Pre-execution validation</span>
            </div>

            <div className="metric-card purple">
              <span className="metric-label">Balance Rules (R11+)</span>
              <span className="metric-value">{summaryCounts.balance_rules || balanceRules.length}</span>
              <span className="metric-sub">Reconciliation node & buckets</span>
            </div>

            <div className="metric-card amber">
              <span className="metric-label">Target Attributes</span>
              <span className="metric-value">{summaryCounts.total_attributes || mappings.length}</span>
              <span className="metric-sub">
                {summaryCounts.direct_attributes || 0} Direct · {summaryCounts.derived_attributes || 0} Derived
              </span>
            </div>
          </div>

          {/* ── Interactive Visual ETL Pipeline Flow Diagram ── */}
          <div className="pipeline-flow-container">
            <div className="pipeline-header">
              <div className="pipeline-title-group">
                <span className="badge-pill cyan">ARCHITECTURE LINEAGE</span>
                <h3>End-to-End ETL Reconciliation Flow</h3>
              </div>
              <span style={{ fontSize: '0.78rem', color: '#94a3b8' }}>
                Extracted from HLA Architecture Specification
              </span>
            </div>

            <div className="pipeline-stages-track">
              {/* Stage 1: Ingestion Feeds */}
              <div
                className="pipeline-stage-node clickable"
                onClick={() => setActiveTab('sources')}
              >
                <div className="stage-node-header">
                  <span className="stage-step-tag">STAGE 1</span>
                  <span className="stage-icon">📥</span>
                </div>
                <h4>Upstream Feeds</h4>
                <p>
                  {sources.length} source dataset{sources.length === 1 ? '' : 's'}
                  {sources.length > 0 ? ` (${sources.slice(0, 3).map(s => s.source_table).join(', ')}${sources.length > 3 ? '...' : ''})` : ''}
                </p>
                <span className="stage-node-action">Inspect Inventory ➔</span>
              </div>

              <div className="pipeline-arrow">➔</div>

              {/* Stage 2: Filter Rules R1-R10 */}
              <div
                className="pipeline-stage-node clickable"
                onClick={() => setActiveTab('rules')}
              >
                <div className="stage-node-header">
                  <span className="stage-step-tag">STAGE 2</span>
                  <span className="stage-icon">🧹</span>
                </div>
                <h4>R1–R10 Filters</h4>
                <p>{filterRules.length || 10} quality & deduplication rules</p>
                <span className="stage-node-action">View Logic ➔</span>
              </div>

              <div className="pipeline-arrow">➔</div>

              {/* Stage 3: Balance Gate Node */}
              <div
                className="pipeline-stage-node clickable highlight-teal"
                onClick={() => setActiveTab('rules')}
              >
                <div className="stage-node-header">
                  <span className="stage-step-tag" style={{ color: '#05d5b3', borderColor: 'rgba(5, 213, 179, 0.3)' }}>STAGE 3</span>
                  <span className="stage-icon">⚖️</span>
                </div>
                <h4>R11 Balance Gate</h4>
                <p>Consolidated clean dataset staging (CTRL_X_BALANCED)</p>
                <span className="stage-node-action" style={{ color: '#05d5b3' }}>Gatekeeper ➔</span>
              </div>

              <div className="pipeline-arrow">➔</div>

              {/* Stage 4: Reconciliation Matches */}
              <div
                className="pipeline-stage-node clickable"
                onClick={() => setActiveTab('mappings')}
              >
                <div className="stage-node-header">
                  <span className="stage-step-tag">STAGE 4</span>
                  <span className="stage-icon">🔍</span>
                </div>
                <h4>Recon Matching</h4>
                <p>IP Exact ➔ Host Name ➔ Fuzzy match logic</p>
                <span className="stage-node-action">View Mappings ➔</span>
              </div>

              <div className="pipeline-arrow">➔</div>

              {/* Stage 5: Output Buckets */}
              <div className="pipeline-stage-node highlight-purple">
                <div className="stage-node-header">
                  <span className="stage-step-tag" style={{ color: '#c084fc', borderColor: 'rgba(192, 132, 252, 0.3)' }}>STAGE 5</span>
                  <span className="stage-icon">📊</span>
                </div>
                <h4>Output Buckets</h4>
                <p>BB (Reconciled) vs YN (Exceptions & KRI Alerts)</p>
                <span className="stage-node-badge">Audit Ready</span>
              </div>
            </div>
          </div>

          {/* ── Studio Navigation Tabs ── */}
          <div className="studio-tabs-bar">
            <button
              className={`studio-tab-btn ${activeTab === 'sources' ? 'active' : ''}`}
              onClick={() => setActiveTab('sources')}
              id="tab-btn-sources"
            >
              <span>📊</span> Source Systems & Tables ({sources.length})
            </button>
            <button
              className={`studio-tab-btn ${activeTab === 'rules' ? 'active' : ''}`}
              onClick={() => setActiveTab('rules')}
              id="tab-btn-rules"
            >
              <span>🧠</span> Filter & Balance Rules ({filterRules.length + balanceRules.length})
            </button>
            <button
              className={`studio-tab-btn ${activeTab === 'mappings' ? 'active' : ''}`}
              onClick={() => setActiveTab('mappings')}
              id="tab-btn-mappings"
            >
              <span>🗺️</span> Attribute Mapping Matrix ({mappings.length})
            </button>
            {dataModel.length > 0 && (
              <button
                className={`studio-tab-btn ${activeTab === 'datamodel' ? 'active' : ''}`}
                onClick={() => setActiveTab('datamodel')}
                id="tab-btn-datamodel"
              >
                <span>🗄️</span> Data Model ({dataModel.length})
              </button>
            )}
            {buckets.length > 0 && (
              <button
                className={`studio-tab-btn ${activeTab === 'buckets' ? 'active' : ''}`}
                onClick={() => setActiveTab('buckets')}
                id="tab-btn-buckets"
              >
                <span>📊</span> Buckets & KRI ({buckets.length})
              </button>
            )}
            <button
                className={`studio-tab-btn ${activeTab === 'synthesis' ? 'active' : ''}`}
                onClick={() => setActiveTab('synthesis')}
                id="tab-btn-synthesis"
            >
              <span>✨</span> Architecture Synthesis & Code
            </button>
            <button
              className={`studio-tab-btn ${activeTab === 'template' ? 'active' : ''}`}
              onClick={() => setActiveTab('template')}
              id="tab-btn-template"
            >
              <span>📋</span> Solution Design Specs ({templateCompliance.compliance_score !== undefined ? `${templateCompliance.compliance_score}%` : 'Template'})
            </button>
          </div>

          {/* ── TAB 1: Source Systems & Tables ── */}
          {activeTab === 'sources' && (
            <div className="tab-card-panel">
              <div className="panel-header-strip">
                <div>
                  <h4 style={{ margin: '0 0 0.2rem 0', color: '#ffffff' }}>Configured Upstream Source Tables</h4>
                  <p style={{ margin: 0, fontSize: '0.82rem', color: '#94a3b8' }}>
                    Extracted from the HLA document. Click "Live Introspect" on any table to examine actual column data types and live sample rows.
                  </p>
                </div>
                <button
                  className="btn-secondary"
                  style={{ fontSize: '0.78rem' }}
                  onClick={() => setShowDBManager(true)}
                >
                  ⚙️ Manage Source DB Credentials
                </button>
              </div>

              <div className="table-responsive-wrapper">
                <table className="analysis-table" id="sources-table">
                  <thead>
                    <tr>
                      <th>Source DB</th>
                      <th>Schema</th>
                      <th>Physical Table Name</th>
                      <th>Frequency</th>
                      <th>Schedule / Window</th>
                      <th>Type of Load</th>
                      <th>Live Inspection</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sources.map((src, idx) => {
                      const tableKey = `${src.source_schema}.${src.source_table}`
                      const isFetching = fetchingSchemaTable === tableKey
                      return (
                        <tr key={idx}>
                          <td>
                            <span className="badge-db-source">{src.source_db || 'Source DB'}</span>
                          </td>
                          <td style={{ color: '#94a3b8', fontFamily: 'JetBrains Mono', fontSize: '0.78rem' }}>
                            {src.source_schema || 'public'}
                          </td>
                          <td className="table-code-cell">
                            <code>{src.source_table || src.full_table_name}</code>
                          </td>
                          <td>{src.frequency || 'Daily'}</td>
                          <td style={{ color: '#94a3b8', fontSize: '0.8rem' }}>{src.refresh_time || 'Daily 6:00 AM'}</td>
                          <td>
                            <span className={`load-badge ${src.type_of_load === 'Append' ? 'append' : 'truncate'}`}>
                              {src.type_of_load || 'Truncate and load'}
                            </span>
                          </td>
                          <td>
                            <button
                              className="btn-fetch-schema"
                              onClick={() => handleFetchTableSchema(src)}
                              disabled={isFetching}
                              title="Fetch actual columns, types, and sample data from source DB"
                            >
                              <span>⚡</span>
                              <span>{isFetching ? 'Introspecting…' : 'Live Introspect'}</span>
                            </button>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── TAB 2: Filter & Balance Rules ── */}
          {activeTab === 'rules' && (
            <div className="tab-card-panel">
              {inputStreams.length > 0 && (
                <div className="rules-category-block">
                  <div className="category-title-bar">
                    <span>📥</span> 1. Input Data Stream Ingestors
                  </div>
                  <div className="rules-cards-grid">
                    {inputStreams.map((item, idx) => (
                      <div key={idx} className="rule-card">
                        <div className="rule-card-top">
                          <span className="rule-id-pill input">{item.rule_id || `I${idx+1}`}</span>
                          <span className="rule-stream-tag">{item.data_stream}</span>
                        </div>
                        <p className="rule-statement-text">{item.rule_statement}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {filterRules.length > 0 && (
                <div className="rules-category-block">
                  <div className="category-title-bar">
                    <span>🎯</span> 2. Pre-Execution Filter Dataset Rules (R1–R10)
                  </div>
                  <div className="rules-cards-grid">
                    {filterRules.map((rule, idx) => (
                      <div key={idx} className="rule-card">
                        <div className="rule-card-top">
                          <span className="rule-id-pill filter">{rule.rule_id || `R${idx+1}`}</span>
                          <span className="rule-stream-tag">{rule.data_stream || 'Filter Rule'}</span>
                        </div>
                        <p className="rule-statement-text">{rule.rule_statement}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {(balanceRules.length > 0 || reconciliationFlows.length > 0) && (
                <div className="rules-category-block">
                  <div className="category-title-bar">
                    <span>⚖️</span> 3. Balance Node (R11) & Reconciliation Buckets
                  </div>
                  <div className="rules-cards-grid">
                    {balanceRules.concat(reconciliationFlows).map((rule, idx) => (
                      <div key={idx} className="rule-card balance-card">
                        <div className="rule-card-top">
                          <span className="rule-id-pill balance">{rule.rule_id || `R11`}</span>
                          <span className="rule-stream-tag">{rule.data_stream || rule.category || 'Balance Node'}</span>
                        </div>
                        <p className="rule-statement-text">{rule.rule_statement}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── TAB 3: Attribute Mapping Matrix ── */}
          {activeTab === 'mappings' && (
            <div className="tab-card-panel">
              <div className="mapping-toolbar">
                <div className="mapping-filters-row">
                  <span style={{ fontSize: '0.78rem', color: '#64748b', fontWeight: 700, textTransform: 'uppercase' }}>Type:</span>
                  <button
                    className={`map-filter-btn ${mappingFilter === 'all' ? 'active' : ''}`}
                    onClick={() => setMappingFilter('all')}
                  >
                    All ({mappings.length})
                  </button>
                  <button
                    className={`map-filter-btn ${mappingFilter === 'direct' ? 'active' : ''}`}
                    onClick={() => setMappingFilter('direct')}
                  >
                    Direct Only ({summaryCounts.direct_attributes || 0})
                  </button>
                  <button
                    className={`map-filter-btn ${mappingFilter === 'derived' ? 'active' : ''}`}
                    onClick={() => setMappingFilter('derived')}
                  >
                    Derived Only ({summaryCounts.derived_attributes || 0})
                  </button>
                </div>

                <div className="search-wrap">
                  <span style={{ fontSize: '0.85rem', opacity: 0.6 }}>🔍</span>
                  <input
                    type="text"
                    placeholder="Filter by target column or source field…"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="map-search-input"
                  />
                  {searchQuery && (
                    <button className="clear-btn" onClick={() => setSearchQuery('')}>✕</button>
                  )}
                </div>
              </div>

              <div className="table-responsive-wrapper">
                <table className="analysis-table" id="mappings-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Target Column</th>
                      <th>Mapping Type</th>
                      <th>Source Table</th>
                      <th>Source Field</th>
                      <th>Transformation / Remark</th>
                    </tr>
                  </thead>
                  <tbody>
                    {filteredMappings.map((m, idx) => (
                      <tr key={idx}>
                        <td style={{ color: '#64748b', fontSize: '0.76rem' }}>{idx + 1}</td>
                        <td className="table-code-cell">
                          <strong>{m.target_column}</strong>
                        </td>
                        <td>
                          <span className={`mapping-pill ${m.mapping_type?.toLowerCase()}`}>
                            {m.mapping_type || 'Direct'}
                          </span>
                        </td>
                        <td style={{ color: '#94a3b8', fontFamily: 'JetBrains Mono', fontSize: '0.78rem' }}>
                          {m.source_table || '-'}
                        </td>
                        <td style={{ color: '#38bdf8', fontFamily: 'JetBrains Mono', fontSize: '0.78rem' }}>
                          {m.source_field || '-'}
                        </td>
                        <td style={{ color: '#cbd5e1', fontSize: '0.8rem' }}>
                          {m.derivation_logic || m.remark || '-'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── TAB 4: Architecture Synthesis & Code ── */}
          {activeTab === 'synthesis' && (
            <div className="tab-card-panel">
              <div className="synthesis-card">
                <div className="synthesis-badge">AI EXECUTIVE SUMMARY</div>
                <h4>Architecture Blueprint Synthesis</h4>
                <p className="synthesis-text">
                  {llmSynthesis.executive_summary ||
                    'This High-Level Architecture specification establishes automated ingestion pipelines across configured upstream source datasets. Pre-execution quality and deduplication rules cleanse telemetry feeds before convergence into the balance node for reconciliation matching.'}
                </p>
              </div>

              {llmSynthesis.pyspark_pipeline && (
                <div className="pyspark-code-card">
                  <div className="code-header-strip">
                    <span style={{ fontWeight: 700, color: '#f8fafc', fontSize: '0.85rem' }}>
                      Generated Production PySpark / SQL Ingestion Script
                    </span>
                    <button
                      className="btn-secondary"
                      style={{ fontSize: '0.74rem', padding: '0.3rem 0.65rem' }}
                      onClick={() => {
                        navigator.clipboard.writeText(llmSynthesis.pyspark_pipeline)
                        alert('PySpark code copied to clipboard!')
                      }}
                    >
                      📋 Copy Script
                    </button>
                  </div>
                  <pre className="pyspark-code-block">
                    <code>{llmSynthesis.pyspark_pipeline}</code>
                  </pre>
                </div>
              )}
            </div>
          )}

          {/* ── TAB 5: Solution Design Specs & Governance (13 Standard Tables) ── */}
          {activeTab === 'template' && (
            <div className="tab-card-panel">
              <div className="panel-header-strip">
                <div>
                  <h4 style={{ margin: '0 0 0.2rem 0', color: '#ffffff' }}>
                    HLA Solution Design Template Conformance & Specifications
                  </h4>
                  <p style={{ margin: 0, fontSize: '0.82rem', color: '#94a3b8' }}>
                    Standard 13-table client architecture specification including extraction policies, configuration parameters, and report dependencies.
                  </p>
                </div>
                {templateCompliance.compliance_score !== undefined && (
                  <span
                    style={{
                      background: templateCompliance.is_compliant ? 'rgba(5, 213, 179, 0.15)' : 'rgba(255, 184, 0, 0.15)',
                      color: templateCompliance.is_compliant ? '#05d5b3' : '#ffb800',
                      border: `1px solid ${templateCompliance.is_compliant ? 'rgba(5, 213, 179, 0.4)' : 'rgba(255, 184, 0, 0.4)'}`,
                      padding: '0.35rem 0.85rem',
                      borderRadius: '8px',
                      fontWeight: '700',
                      fontSize: '0.82rem'
                    }}
                  >
                    {templateCompliance.is_compliant ? '✓ 100% Compliant' : `${templateCompliance.compliance_score}% Compliant`}
                  </span>
                )}
              </div>

              {/* Control Overview Banner (Table 3) */}
              {ctrlId.control_number && (
                <div style={{
                  background: 'rgba(15, 23, 42, 0.6)',
                  border: '1px solid rgba(0, 242, 254, 0.2)',
                  borderRadius: '12px',
                  padding: '1rem 1.25rem',
                  marginBottom: '1.25rem'
                }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                    <span style={{ fontWeight: 800, color: '#00f2fe', fontSize: '0.9rem' }}>
                      CONTROL IDENTIFICATION (TABLE 3)
                    </span>
                    <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>Owner: {ctrlId.control_owner || 'N/A'}</span>
                  </div>
                  <h3 style={{ margin: '0 0 0.4rem 0', color: '#ffffff', fontSize: '1.1rem' }}>
                    {ctrlId.control_number}: {ctrlId.control_title}
                  </h3>
                  <p style={{ margin: 0, fontSize: '0.85rem', color: '#cbd5e1' }}>
                    <strong>Objective:</strong> {ctrlId.purpose || 'Reconciliation solution and automated exception classification.'}
                  </p>
                </div>
              )}

              {/* Extraction Requirements (Table 7) */}
              {extractionRequirements.length > 0 && (
                <div style={{ marginBottom: '1.5rem' }}>
                  <h5 style={{ color: '#00f2fe', margin: '0 0 0.6rem 0', fontSize: '0.9rem' }}>
                    📥 Section 3: Data Extraction Requirements (Table 7)
                  </h5>
                  <div className="table-responsive-wrapper">
                    <table className="analysis-table">
                      <thead>
                        <tr>
                          <th>Source Table</th>
                          <th>Extraction Type</th>
                          <th>Logic / Window</th>
                          <th>Justification</th>
                        </tr>
                      </thead>
                      <tbody>
                        {extractionRequirements.map((ext, idx) => (
                          <tr key={idx}>
                            <td><code>{ext.source_table}</code></td>
                            <td><span className="load-badge truncate">{ext.extraction_type}</span></td>
                            <td>{ext.extraction_logic || '-'}</td>
                            <td style={{ color: '#94a3b8', fontSize: '0.8rem' }}>{ext.justification || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Filtration Steps (Table 9) */}
              {filtrationSteps.length > 0 && (
                <div style={{ marginBottom: '1.5rem' }}>
                  <h5 style={{ color: '#00f2fe', margin: '0 0 0.6rem 0', fontSize: '0.9rem' }}>
                    ⚙️ Section 6: Filtration Technical Procedure (Table 9)
                  </h5>
                  <div className="table-responsive-wrapper">
                    <table className="analysis-table">
                      <thead>
                        <tr>
                          <th>Step</th>
                          <th>Description</th>
                          <th>Rule Reference</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtrationSteps.map((st, idx) => (
                          <tr key={idx}>
                            <td style={{ fontWeight: 700, color: '#05d5b3' }}>{st.step || idx + 1}</td>
                            <td>{st.description}</td>
                            <td><code>{st.logic_reference || '-'}</code></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Configuration Tables (Table 12) */}
              {configTables.length > 0 && (
                <div style={{ marginBottom: '1.5rem' }}>
                  <h5 style={{ color: '#00f2fe', margin: '0 0 0.6rem 0', fontSize: '0.9rem' }}>
                    🎛️ Section 9: Dedicated Configuration Tables (Table 12)
                  </h5>
                  <div className="table-responsive-wrapper">
                    <table className="analysis-table">
                      <thead>
                        <tr>
                          <th>Config Table</th>
                          <th>Purpose</th>
                          <th>Sample Fields</th>
                          <th>Consumed By</th>
                        </tr>
                      </thead>
                      <tbody>
                        {configTables.map((cfg, idx) => (
                          <tr key={idx}>
                            <td><code>{cfg.config_table_name}</code></td>
                            <td>{cfg.purpose}</td>
                            <td style={{ color: '#94a3b8', fontSize: '0.8rem' }}>{cfg.sample_fields}</td>
                            <td><span className="badge-db-source">{cfg.consumed_by}</span></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Report Inventory & Sequence (Table 13) */}
              {reportInventory.length > 0 && (
                <div>
                  <h5 style={{ color: '#00f2fe', margin: '0 0 0.6rem 0', fontSize: '0.9rem' }}>
                    📊 Section 10: Report Inventory & Generation Sequence (Table 13)
                  </h5>
                  <div className="table-responsive-wrapper">
                    <table className="analysis-table">
                      <thead>
                        <tr>
                          <th>Seq #</th>
                          <th>Report Name</th>
                          <th>Dependencies</th>
                          <th>Notes</th>
                        </tr>
                      </thead>
                      <tbody>
                        {reportInventory.map((item, idx) => (
                          <tr key={idx}>
                            <td style={{ fontWeight: 700, color: '#05d5b3' }}>#{item.sequence}</td>
                            <td style={{ fontWeight: 600 }}>{item.report_name}</td>
                            <td><code>{item.depends_on || 'None'}</code></td>
                            <td style={{ color: '#94a3b8', fontSize: '0.8rem' }}>{item.notes || '-'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* ── TAB: Enterprise Data Model (24 Tables) ── */}
          {activeTab === 'datamodel' && (
            <div className="tab-card-panel">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                <div>
                  <h3 style={{ margin: '0 0 0.25rem 0', color: '#f8fafc', fontSize: '1.15rem' }}>
                    Enterprise Data Model ({dataModel.length} Target Entities)
                  </h3>
                  <p style={{ margin: 0, color: '#94a3b8', fontSize: '0.85rem' }}>
                    Staging, Pre-Execution, Post-Execution, and Master Config datasets defined in solution specification.
                  </p>
                </div>
                <span className="badge-pill cyan">{dataModel.length} Tables Modeled</span>
              </div>

              <div className="table-responsive-wrapper">
                <table className="analysis-table" id="data-model-table">
                  <thead>
                    <tr>
                      <th>#</th>
                      <th>Stage</th>
                      <th>Table / Entity Name</th>
                      <th>Architecture Standard</th>
                      <th>Load Type</th>
                      <th>Description</th>
                    </tr>
                  </thead>
                  <tbody>
                    {dataModel.map((item, idx) => (
                      <tr key={idx}>
                        <td style={{ color: '#64748b', fontSize: '0.8rem' }}>{idx + 1}</td>
                        <td>
                          <span className={`stage-step-tag ${item.stage?.toLowerCase().replace(/[^a-z0-9]/g, '')}`}>
                            {item.stage}
                          </span>
                        </td>
                        <td>
                          <code style={{ color: '#38bdf8', fontWeight: 700, fontSize: '0.88rem' }}>
                            {item.table_name}
                          </code>
                        </td>
                        <td>
                          <span style={{
                            fontSize: '0.75rem',
                            padding: '3px 8px',
                            borderRadius: '6px',
                            fontWeight: 600,
                            background: item.standard_status?.toLowerCase().includes('standard') ? 'rgba(56, 189, 248, 0.12)' : 'rgba(245, 158, 11, 0.12)',
                            color: item.standard_status?.toLowerCase().includes('standard') ? '#38bdf8' : '#fbbf24',
                            border: item.standard_status?.toLowerCase().includes('standard') ? '1px solid rgba(56, 189, 248, 0.3)' : '1px solid rgba(245, 158, 11, 0.3)'
                          }}>
                            {item.standard_status || 'Standard'}
                          </span>
                        </td>
                        <td>
                          <span className={`load-badge ${item.load_type?.toLowerCase().includes('truncate') ? 'truncate' : 'append'}`}>
                            {item.load_type || 'Truncate & Load'}
                          </span>
                        </td>
                        <td style={{ color: '#cbd5e1', fontSize: '0.85rem' }}>{item.description}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* ── TAB: Resultant Buckets & KRI Rules ── */}
          {activeTab === 'buckets' && (
            <div className="tab-card-panel">
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
                <div>
                  <h3 style={{ margin: '0 0 0.25rem 0', color: '#f8fafc', fontSize: '1.15rem' }}>
                    Resultant Buckets & KRI Exception Rating ({buckets.length} Buckets)
                  </h3>
                  <p style={{ margin: 0, color: '#94a3b8', fontSize: '0.85rem' }}>
                    Automated bucket classification (FB1–FB7, B1–B6, B4.1, B5.1–B5.6) with revenue and Capex impact logic.
                  </p>
                </div>
                <span className="badge-pill purple">{buckets.length} Buckets</span>
              </div>

              <div className="table-responsive-wrapper" style={{ marginBottom: '2rem' }}>
                <table className="analysis-table" id="buckets-table">
                  <thead>
                    <tr>
                      <th>Bucket</th>
                      <th>KRI ID</th>
                      <th>Description</th>
                      <th>Logic</th>
                      <th>Impact Formula (USD)</th>
                      <th>Remarks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {buckets.map((b, idx) => (
                      <tr key={idx}>
                        <td>
                          <span className={`rule-id-pill ${b.bucket_id?.startsWith('FB') ? 'filter' : 'balance'}`}>
                            {b.bucket_id}
                          </span>
                        </td>
                        <td style={{ fontWeight: 600, color: b.kri_id && b.kri_id !== '-' ? '#f43f5e' : '#94a3b8' }}>
                          {b.kri_id || '-'}
                        </td>
                        <td style={{ color: '#f1f5f9', fontWeight: 500 }}>{b.description}</td>
                        <td style={{ color: '#94a3b8', fontSize: '0.82rem' }}>{b.logic || '-'}</td>
                        <td style={{ color: '#38bdf8', fontSize: '0.82rem', fontFamily: 'monospace' }}>
                          {b.impact_calculation || '-'}
                        </td>
                        <td style={{ color: '#64748b', fontSize: '0.8rem' }}>{b.remarks || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {derivedFields.length > 0 && (
                <div>
                  <h4 style={{ color: '#38bdf8', margin: '0 0 0.75rem 0', fontSize: '1rem' }}>
                    ⚡ Derived Ageing & Financial Impact Formulas (Final Workitem)
                  </h4>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: '1rem' }}>
                    {derivedFields.map((df, idx) => (
                      <div key={idx} className="rule-card" style={{ background: 'rgba(15, 23, 42, 0.7)', border: '1px solid rgba(56, 189, 248, 0.2)' }}>
                        <div className="rule-card-top">
                          <code style={{ color: '#38bdf8', fontWeight: 700, fontSize: '0.95rem' }}>{df.field_name}</code>
                          <span className="rule-stream-tag">Derived Column</span>
                        </div>
                        <pre style={{
                          margin: '0.5rem 0 0 0',
                          fontSize: '0.8rem',
                          color: '#cbd5e1',
                          whiteSpace: 'pre-wrap',
                          fontFamily: 'inherit',
                          lineHeight: 1.4
                        }}>
                          {df.derivation_logic}
                        </pre>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}

      {/* ── Source DB Configuration Drawer / Modal ── */}
      {showDBManager && (
        <SourceDBManager
          projectId={projectId || doc.project_id || 1}
          distinctSourceDBs={distinctSourceDBs}
          onClose={() => setShowDBManager(false)}
        />
      )}

      {/* ── Table Schema Inspection Modal ── */}
      {selectedTableSchema && (
        <TableSchemaModal
          schemaData={selectedTableSchema}
          onClose={() => setSelectedTableSchema(null)}
        />
      )}
    </section>
  )
}
