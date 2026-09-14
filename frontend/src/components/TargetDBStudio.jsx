import React, { useState, useEffect } from 'react'
import api from '../services/api'
import { copyToClipboard } from '../utils/clipboard'
import './TargetDBStudio.css'

function formatSchemaString(schema) {
  if (!schema) return 'public'
  if (typeof schema === 'object') return schema.schema_name || 'public'
  return String(schema)
}

export default function TargetDBStudio({ projectId, documentId, projectDocs = [], currentUser, onRefreshProject }) {
  const isViewer = currentUser?.role?.toLowerCase() === 'viewer'
  const [activeEnv, setActiveEnv] = useState('dev') // 'dev' | 'prod'
  const [selectedDocId, setSelectedDocId] = useState(documentId || (projectDocs[0]?.id || null))
  const [codeTab, setCodeTab] = useState('ddl') // 'ddl' | 'sql' | 'pyspark' | 'reasoning'

  // Target Database Configurations (Dev and Prod)
  const [targetConfigs, setTargetConfigs] = useState({ dev: null, prod: null })
  const [targetForm, setTargetForm] = useState({
    db_type: 'postgresql',
    host: 'localhost',
    port: '5432',
    database_name: 'hla_db',
    username: 'postgres',
    password: '',
    schema_name: 'public',
    connection_string: '',
  })
  const [showConfigModal, setShowConfigModal] = useState(false)
  const [configMode, setConfigMode] = useState('manual') // 'manual' | 'vault'
  const [testingConn, setTestingConn] = useState(false)
  const [testResult, setTestResult] = useState(null)
  const [savingConfig, setSavingConfig] = useState(false)
  const [applyToBoth, setApplyToBoth] = useState(true)
  const [saveSuccessMsg, setSaveSuccessMsg] = useState('')

  // Target .kdb Vault State
  const [vaultText, setVaultText] = useState('')
  const [vaultFile, setVaultFile] = useState(null)
  const [uploadingVault, setUploadingVault] = useState(false)
  const [vaultFeedback, setVaultFeedback] = useState(null)
  const [vaultScope, setVaultScope] = useState('both') // 'both' (Source+Target) | 'target'
  const [projectConns, setProjectConns] = useState([])
  const [kdbRequirementMessage, setKdbRequirementMessage] = useState(null)

  // Target Artifacts
  const [artifacts, setArtifacts] = useState({})
  const [building, setBuilding] = useState(false)
  const [buildStep, setBuildStep] = useState('')
  const [deploying, setDeploying] = useState(false)
  const [deployAction, setDeployAction] = useState('') // 'validate' | 'deploy'
  const [deployResult, setDeployResult] = useState(null)
  const [copied, setCopied] = useState(false)

  // Source DB Scanning & Table Verification State
  const [scanResult, setScanResult] = useState(null)
  const [scanningSource, setScanningSource] = useState(false)
  const [deletingDoc, setDeletingDoc] = useState(false)

  const handleDeleteDoc = async (docIdToDelete, docName) => {
    if (!docIdToDelete) return
    const displayName = docName || `Document #${docIdToDelete}`
    if (
      !window.confirm(
        `Are you sure you want to remove HLA document "${displayName}"?\n\nThis will delete the uploaded workbook, extracted source tables, filter rules, and reconciliation models.`
      )
    ) {
      return
    }

    setDeletingDoc(true)
    try {
      await axios.delete(`/api/documents/${docIdToDelete}`)
      if (onRefreshProject) {
        await onRefreshProject()
      }
      const remaining = projectDocs.filter((d) => d.id !== docIdToDelete)
      if (remaining.length > 0) {
        setSelectedDocId(remaining[0].id)
      } else {
        setSelectedDocId(null)
      }
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to remove HLA document.'
      alert(msg)
    } finally {
      setDeletingDoc(false)
    }
  }

  // Close config modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && showConfigModal) {
        setShowConfigModal(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [showConfigModal])

  // Sync selectedDocId when documentId prop updates
  useEffect(() => {
    if (documentId) {
      setSelectedDocId(documentId)
    } else if (projectDocs.length > 0 && !selectedDocId) {
      setSelectedDocId(projectDocs[0].id)
    }
  }, [documentId, projectDocs])

  const fetchProjectInfo = async () => {
    try {
      const res = await api.get(`/api/projects/${projectId}`)
      setProjectConns(res.data?.db_connections || [])
    } catch (err) {
      console.error('Failed to load project details:', err)
    }
  }

  const handleScanSourceDB = async (docIdToScan = selectedDocId) => {
    if (!docIdToScan) return
    setScanningSource(true)
    try {
      const res = await api.post(`/api/documents/${docIdToScan}/scan-source-db`)
      setScanResult(res.data)
    } catch (err) {
      console.error('Source DB scan failed:', err)
    } finally {
      setScanningSource(false)
    }
  }

  // Load target configs, project details, and artifacts
  useEffect(() => {
    if (projectId) {
      fetchTargetConfigs()
      fetchProjectInfo()
    }
  }, [projectId])

  useEffect(() => {
    if (selectedDocId) {
      fetchTargetArtifacts(selectedDocId)
      handleScanSourceDB(selectedDocId)
    }
  }, [selectedDocId])

  // Update targetForm when activeEnv, targetConfigs, or activeDoc changes
  useEffect(() => {
    const current = targetConfigs[activeEnv]
    const activeDoc = projectDocs.find((d) => d.id === selectedDocId) || projectDocs[0]
    const co = activeDoc?.analysis_data?.control_overview
    const rawTargetSchema = co?.target_schema
    const dynamicSchema = (typeof rawTargetSchema === 'object' ? rawTargetSchema?.schema_name : rawTargetSchema) || 'public'

    if (current) {
      const savedSchema = current.schema_name
      const effSchema = savedSchema !== undefined && savedSchema !== null && String(savedSchema).trim() !== ''
        ? String(savedSchema).trim()
        : (dynamicSchema || 'public')
      setTargetForm({
        db_type: current.db_type || 'postgresql',
        host: current.host || 'localhost',
        port: current.port ? String(current.port) : '5432',
        database_name: current.database_name || 'hla_db',
        username: current.username || 'postgres',
        password: '',
        schema_name: effSchema,
        connection_string: current.connection_string || '',
      })
      setTestResult(current.status === 'connected' ? { success: true, message: 'Connected & Verified' } : null)
    } else {
      setTargetForm({
        db_type: 'postgresql',
        host: 'localhost',
        port: '5432',
        database_name: 'hla_db',
        username: 'postgres',
        password: '',
        schema_name: dynamicSchema || 'public',
        connection_string: '',
      })
      setTestResult(null)
    }
  }, [activeEnv, targetConfigs, selectedDocId, projectDocs])

  const fetchTargetConfigs = async () => {
    try {
      const res = await api.get(`/api/projects/${projectId}/targets`)
      setTargetConfigs(res.data || { dev: null, prod: null })
    } catch (err) {
      console.error('Failed to load target database configs:', err)
    }
  }

  const fetchTargetArtifacts = async (docId) => {
    try {
      const res = await api.get(`/api/documents/${docId}/target-artifacts`)
      const list = res.data || []
      const map = {}
      list.forEach((a) => {
        map[a.environment] = a
      })
      setArtifacts(map)
    } catch (err) {
      console.error('Failed to load target artifacts:', err)
    }
  }

  const handleTestTargetConnection = async () => {
    setTestingConn(true)
    setTestResult(null)
    try {
      const res = await api.post(`/api/projects/${projectId}/connections/test`, targetForm)
      setTestResult(res.data)
    } catch (err) {
      setTestResult({
        success: false,
        message: err.response?.data?.error || 'Connection failed',
      })
    } finally {
      setTestingConn(false)
    }
  }

  const handleSaveTargetConfig = async (e) => {
    e.preventDefault()
    setSavingConfig(true)
    try {
      const payload = {
        target_env: activeEnv,
        apply_to_both: applyToBoth,
        ...targetForm,
      }
      const res = await api.post(`/api/projects/${projectId}/targets`, payload)
      setTestResult({ success: res.data?.success, message: res.data?.message })
      
      // Update targetConfigs state immediately with returned payload
      if (res.data?.targets) {
        setTargetConfigs(res.data.targets)
      } else if (res.data?.target) {
        setTargetConfigs(prev => ({
          ...prev,
          [activeEnv]: res.data.target,
          ...(applyToBoth ? { [activeEnv === 'dev' ? 'prod' : 'dev']: res.data.target } : {})
        }))
      }

      await fetchTargetConfigs()
      await fetchProjectInfo()
      if (onRefreshProject) onRefreshProject()

      setShowConfigModal(false)
      const envLabel = applyToBoth ? 'DEV & PROD' : activeEnv.toUpperCase()
      setSaveSuccessMsg(`Target database (${envLabel}) credentials & configuration saved and verified successfully!`)
      setTimeout(() => setSaveSuccessMsg(''), 8000)
    } catch (err) {
      setTestResult({
        success: false,
        message: err.response?.data?.error || 'Failed to save target config',
      })
    } finally {
      setSavingConfig(false)
    }
  }

  const hasSourceCreds = projectConns.some(
    (c) => c.conn_role === 'source' && (c.has_password || c.connection_string || c.vault_profile || c.status === 'connected')
  )

  const handleTargetVaultUpload = async (e) => {
    e.preventDefault()
    setUploadingVault(true)
    setVaultFeedback(null)

    try {
      if (vaultScope === 'both') {
        let res
        if (vaultFile) {
          const data = new FormData()
          data.append('file', vaultFile)
          res = await api.post(`/api/projects/${projectId}/upload-vault`, data, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
        } else if (vaultText.trim()) {
          res = await api.post(`/api/projects/${projectId}/upload-vault`, {
            content: vaultText,
            filename: 'credentials.kdb',
          })
        } else {
          alert('Please select a .kdb / vault file or paste configuration text.')
          setUploadingVault(false)
          return
        }

        setVaultFeedback({
          success: true,
          message: res.data?.message || 'Master vault imported successfully.',
        })
        await fetchProjectInfo()
        await fetchTargetConfigs()
        if (onRefreshProject) onRefreshProject()
      } else {
        let res
        if (vaultFile) {
          const data = new FormData()
          data.append('file', vaultFile)
          data.append('target_env', activeEnv)
          res = await api.post(`/api/projects/${projectId}/targets/vault-upload`, data, {
            headers: { 'Content-Type': 'multipart/form-data' },
          })
        } else if (vaultText.trim()) {
          res = await api.post(`/api/projects/${projectId}/targets/vault-upload`, {
            raw_content: vaultText,
            filename: 'target_credentials.kdb',
            target_env: activeEnv,
          })
        } else {
          alert('Please select a .kdb / vault file or paste target configuration text.')
          setUploadingVault(false)
          return
        }

        setVaultFeedback({
          success: true,
          message: res.data?.message,
          targets: res.data?.targets,
          configured_envs: res.data?.configured_envs,
        })

        if (res.data?.targets) {
          setTargetConfigs(res.data.targets)
        } else {
          await fetchTargetConfigs()
        }
        await fetchProjectInfo()
        if (onRefreshProject) onRefreshProject()
      }
    } catch (err) {
      setVaultFeedback({
        success: false,
        message: err.response?.data?.error || 'Failed to parse credential vault.',
      })
    } finally {
      setUploadingVault(false)
    }
  }

  const handleLoadSampleTargetTemplate = () => {
    const template = vaultScope === 'both' ? `# Master Credential Vault (.kdb)
# Configures Upstream Source Databases and Target Environments

[source.primary_stream]
db_type = postgresql
host = localhost
port = 5432
database = hla_db
username = postgres
password = your_password_here
schema = public

[source.reference_stream]
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
schema = target_prod` : `[target.dev]
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

  const handleDownloadSampleTargetKdb = () => {
    const template = vaultScope === 'both' ? `# Master Credential Vault (.kdb)
[source.primary_stream]
db_type = postgresql
host = localhost
port = 5432
database = hla_db
username = postgres
password = your_password_here
schema = public

[source.reference_stream]
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
schema = target_dev` : `[target.dev]
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
    const blob = new Blob([template], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = vaultScope === 'both' ? 'master_credentials.kdb' : 'target_credentials.kdb'
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const handleRunTargetBuilder = async () => {
    if (!selectedDocId) {
      alert('Please select an active HLA document first.')
      return
    }

    setBuilding(true)
    setBuildStep('1/4 Ingesting complete HLA specifications...')
    setDeployResult(null)
    setKdbRequirementMessage(null)

    try {
      setTimeout(() => setBuildStep('2/4 Scanning source DB table structures (identifying HLA logic columns alone)...'), 600)
      setTimeout(() => setBuildStep(`3/4 LLM synthesizing Target Architecture for [${activeEnv.toUpperCase()}]...`), 1400)

      const res = await api.post(`/api/documents/${selectedDocId}/build-target-logic`, {
        environment: activeEnv,
        target_config: targetForm,
      }, { timeout: 120000 })

      setBuildStep('4/4 Target DDL (logic columns alone), SQL & PySpark logic ready!')
      await fetchTargetArtifacts(selectedDocId)
      handleScanSourceDB(selectedDocId)
      if (onRefreshProject) onRefreshProject()

      if (res.data?.preview_mode) {
        setKdbRequirementMessage('ℹ️ Target architecture generated in Preview Mode from extracted HLA logic tokens. Upload a .kdb vault or configure source DB connections for live production deployment.')
      }
    } catch (err) {
      if (err.response?.data?.requires_kdb) {
        setKdbRequirementMessage(err.response.data.error)
        setConfigMode('vault')
        setShowConfigModal(true)
      } else {
        alert(err.response?.data?.error || 'Target Logic Builder failed.')
      }
    } finally {
      setTimeout(() => {
        setBuilding(false)
        setBuildStep('')
      }, 800)
    }
  }

  const handleDeployAction = async (action) => {
    if (!selectedDocId) return

    if (scanResult && scanResult.tables_missing_count > 0) {
      setDeployResult({
        success: false,
        message: `Cannot ${action === 'validate' ? 'validate' : 'deploy'}: ${scanResult.tables_missing_count} upstream source table(s) not found in source database. Dry-run validation and deployment are blocked until source tables exist in the source DB.`
      })
      return
    }

    setDeploying(true)
    setDeployAction(action)
    setDeployResult(null)

    try {
      const res = await api.post(`/api/documents/${selectedDocId}/deploy-target`, {
        environment: activeEnv,
        action: action, // 'validate' | 'deploy'
        target_config: targetForm,
      })

      setDeployResult(res.data)
      await fetchTargetArtifacts(selectedDocId)
      if (onRefreshProject) onRefreshProject()
    } catch (err) {
      setDeployResult({
        success: false,
        message: err.response?.data?.message || err.response?.data?.error || `Action '${action}' failed.`,
      })
    } finally {
      setDeploying(false)
      setDeployAction('')
    }
  }

  const currentArtifact = artifacts[activeEnv] || null
  const [switchingSchema, setSwitchingSchema] = useState(false)

  const handleAutoSwitchToPublicSchema = async () => {
    if (!selectedDocId) return
    setSwitchingSchema(true)
    try {
      const updatedForm = { ...targetForm, schema_name: 'public' }
      setTargetForm(updatedForm)
      // Save configuration with public schema
      await api.post(`/api/projects/${projectId}/targets`, {
        target_env: activeEnv,
        ...updatedForm,
      })
      await fetchTargetConfigs()
      // Rebuild target logic targeting public schema
      setBuilding(true)
      setBuildStep('Rebuilding Target Architecture with "public" schema...')
      await api.post(`/api/documents/${selectedDocId}/build-target-logic`, {
        environment: activeEnv,
        target_config: updatedForm,
      })
      await fetchTargetArtifacts(selectedDocId)
      if (onRefreshProject) onRefreshProject()
      setDeployResult({
        success: true,
        message: 'Successfully switched Target Schema to "public" and rebuilt DDL. You can now click "Validate & Dry-Run" or "Deploy to Target"!',
      })
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to switch schema.')
    } finally {
      setSwitchingSchema(false)
      setBuilding(false)
      setBuildStep('')
    }
  }

  const getCodeContent = () => {
    if (!currentArtifact) return ''
    if (codeTab === 'ddl' || codeTab === 'source_ddl') return currentArtifact.generated_ddl || currentArtifact.source_tables_ddl || ''
    if (codeTab === 'sql') return currentArtifact.generated_transformation_sql || ''
    if (codeTab === 'pyspark') return currentArtifact.generated_pyspark_code || ''
    if (codeTab === 'reasoning') return currentArtifact.llm_reasoning || ''
    return ''
  }

  const handleCopyCode = async () => {
    const code = getCodeContent()
    if (!code) return
    const success = await copyToClipboard(code)
    if (success) {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    }
  }

  const handleDownloadCode = () => {
    const code = getCodeContent()
    if (!code) return
    const ext = codeTab === 'pyspark' ? 'py' : codeTab === 'reasoning' ? 'md' : 'sql'
    const filename = codeTab === 'source_ddl'
      ? `target_${activeEnv}_scanned_source_tables.sql`
      : `target_${activeEnv}_${codeTab}.${ext}`
    const blob = new Blob([code], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = filename
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  }

  const activeDoc = projectDocs.find((d) => d.id === selectedDocId)

  return (
    <div className="target-studio-container">
      {/* ── Studio Banner & Environment Switcher ── */}
      <div className="target-header-card">
        <div className="target-header-left">
          <div className="target-title-wrap">
            <span className="target-title-icon">🎯</span>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                <h3 className="target-title">Target Database & ETL Studio</h3>
                <span className={`badge-pill ${activeEnv === 'prod' ? 'amber' : 'cyan'}`}>
                  {activeEnv === 'prod' ? 'PRODUCTION GATEWAY' : 'DEVELOPMENT ENVIRONMENT'}
                </span>
              </div>
              <p className="target-subtitle">
                <strong>End-to-End Workflow:</strong> HLA parsed completely → Source DB credentials / .kdb connected → Upstream source tables scanned for DDL → Replicated in target schema → HLA business & ETL logics (R1–R15) applied into target.
              </p>
            </div>
          </div>
        </div>

        {/* Dual Environment Toggle */}
        <div className="env-switcher-group">
          <button
            className={`env-toggle-btn dev ${activeEnv === 'dev' ? 'active' : ''}`}
            onClick={() => setActiveEnv('dev')}
          >
            <span className="env-dot" />
            <span>Development (Dev)</span>
          </button>
          <button
            className={`env-toggle-btn prod ${activeEnv === 'prod' ? 'active' : ''}`}
            onClick={() => setActiveEnv('prod')}
          >
            <span className="env-dot" />
            <span>Production (Prod)</span>
          </button>
        </div>
      </div>

      {/* Save Success Banner */}
      {saveSuccessMsg && (
        <div style={{
          margin: '0.75rem 0',
          padding: '0.75rem 1.25rem',
          background: 'rgba(34, 197, 94, 0.12)',
          border: '1px solid rgba(34, 197, 94, 0.4)',
          borderRadius: '8px',
          color: '#4ade80',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          fontSize: '0.88rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <span style={{ fontSize: '1.2rem' }}>✓</span>
            <span>{saveSuccessMsg}</span>
          </div>
          <button
            onClick={() => setSaveSuccessMsg('')}
            style={{ background: 'transparent', border: 'none', color: '#4ade80', cursor: 'pointer', fontSize: '1rem' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* ── Active HLA Document & Target DB Status Strip ── */}
      <div className="target-status-strip">
        <div className="status-strip-item">
          <span className="strip-label">HLA Document:</span>
          {projectDocs.length > 0 ? (
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
              <select
                value={selectedDocId || ''}
                onChange={(e) => setSelectedDocId(Number(e.target.value))}
                className="target-select-input"
              >
                {projectDocs.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.original_name || d.filename} ({d.file_type})
                  </option>
                ))}
              </select>
              {!isViewer && (
                <button
                  type="button"
                  className="btn-remove-hla-target"
                  onClick={() => {
                    const docObj = projectDocs.find((d) => d.id === selectedDocId) || projectDocs[0]
                    if (docObj) handleDeleteDoc(docObj.id, docObj.original_name || docObj.filename)
                  }}
                  disabled={deletingDoc}
                  title="Remove this uploaded HLA document"
                >
                  {deletingDoc ? 'Removing…' : '🗑️ Remove'}
                </button>
              )}
            </div>
          ) : (
            <span style={{ color: 'var(--amber-400)', fontSize: '0.84rem' }}>No document uploaded</span>
          )}
        </div>

        <div className="status-strip-item">
          <span className="strip-label">Source DBs & .kdb:</span>
          <span className={`status-pill ${hasSourceCreds ? 'connected' : 'warning'}`}>
            {hasSourceCreds ? 'Credentials Active ✓' : 'Awaiting .kdb / Credentials ⚠️'}
          </span>
          {!isViewer && (
            <button
              className="btn-kdb-target"
              onClick={() => {
                setVaultScope('both')
                setConfigMode('vault')
                setShowConfigModal(true)
              }}
              title="Upload or paste .kdb / Credential Vault file for Source & Target DBs"
            >
              🔐 Insert .kdb
            </button>
          )}
        </div>

        <div className="status-strip-item">
          <span className="strip-label">Target DB ({activeEnv.toUpperCase()}):</span>
          <span className="strip-val">
            {(targetConfigs[activeEnv]?.db_type || targetForm.db_type).toUpperCase()} • {targetConfigs[activeEnv]?.host || targetForm.host}:{targetConfigs[activeEnv]?.port || targetForm.port}/{targetConfigs[activeEnv]?.database_name || targetForm.database_name}
          </span>
          <span className="strip-schema">[{targetConfigs[activeEnv]?.schema_name || targetForm.schema_name || 'public'}]</span>
          <span className={`status-pill ${targetConfigs[activeEnv]?.status === 'connected' ? 'connected' : 'warning'}`}>
            {targetConfigs[activeEnv]?.status === 'connected' ? 'Verified ✓' : (targetConfigs[activeEnv]?.status || 'Configured')}
          </span>
          {!isViewer && (
            <div className="target-strip-btns">
              <button
                className="btn-edit-target"
                onClick={() => {
                  setConfigMode('manual')
                  setShowConfigModal(true)
                }}
                title="Configure Target DB credentials manually"
              >
                ⚙️ Manual Form
              </button>
              <button
                className="btn-kdb-target"
                onClick={() => {
                  setVaultScope('target')
                  setConfigMode('vault')
                  setShowConfigModal(true)
                }}
                title="Upload or paste .kdb / Credential Vault file for Target DB"
              >
                🔐 Target .kdb
              </button>
            </div>
          )}
        </div>

        <div className="status-strip-actions">
          {!isViewer && (
            <button
              className="btn-run-builder"
              onClick={handleRunTargetBuilder}
              disabled={building || !selectedDocId}
            >
              <span>⚡</span> {building ? 'Synthesizing Target Logic…' : 'Build Target Logic with LLM'}
            </button>
          )}
        </div>
      </div>

      {/* ── Custom Source DB to Target Schema Architecture Strip ── */}
      {activeDoc?.analysis_data && (
        <div style={{
          margin: '0.75rem 0',
          padding: '0.85rem 1.25rem',
          background: 'linear-gradient(90deg, rgba(14, 25, 45, 0.9), rgba(15, 23, 42, 0.95))',
          borderRadius: '10px',
          border: '1px solid rgba(56, 189, 248, 0.3)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '0.85rem'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.74rem', fontWeight: 'bold', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Upstream Source:
            </span>
            <span style={{
              padding: '4px 12px',
              borderRadius: '6px',
              background: 'rgba(56, 189, 248, 0.12)',
              border: '1px solid rgba(56, 189, 248, 0.35)',
              color: '#38bdf8',
              fontSize: '0.85rem',
              fontWeight: '600',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '0.4rem'
            }}>
              🗄️ Custom Source DB ({activeDoc.analysis_data.sources?.length || 0} tables in HLA)
            </span>
            <button
              onClick={() => handleScanSourceDB()}
              disabled={scanningSource}
              style={{
                padding: '4px 12px',
                borderRadius: '6px',
                background: 'rgba(56, 189, 248, 0.2)',
                border: '1px solid rgba(56, 189, 248, 0.5)',
                color: '#e0f2fe',
                fontSize: '0.78rem',
                fontWeight: '600',
                cursor: 'pointer',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '0.35rem'
              }}
              title="Scan source database across all schemas to verify whether tables exist and pull DDL"
            >
              {scanningSource ? '🔍 Scanning DB…' : '🔍 Scan Source Tables'}
            </button>
            <span style={{ color: '#38bdf8', fontWeight: 'bold', fontSize: '1.15rem' }}>──▶</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ fontSize: '0.74rem', fontWeight: 'bold', color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
              Target Schema:
            </span>
            <span style={{
              padding: '5px 14px',
              borderRadius: '6px',
              background: 'rgba(16, 185, 129, 0.15)',
              border: '1px solid rgba(16, 185, 129, 0.45)',
              color: '#34d399',
              fontSize: '0.9rem',
              fontWeight: '700',
              fontFamily: 'monospace'
            }}>
              🎯 "{formatSchemaString(targetForm.schema_name || activeDoc?.analysis_data?.control_overview?.target_schema)}"
            </span>
            {activeDoc?.analysis_data?.control_overview?.identification?.control_number && (
              <span style={{ fontSize: '0.78rem', color: '#cbd5e1' }}>
                ({activeDoc.analysis_data.control_overview.identification.control_number})
              </span>
            )}
          </div>
        </div>
      )}

      {/* ── Source DB Scan & Table Verification Inventory Card ── */}
      {scanResult && scanResult.table_audit && scanResult.table_audit.length > 0 && (
        <div style={{
          margin: '0.75rem 0 1rem 0',
          padding: '1rem 1.25rem',
          background: 'rgba(15, 23, 42, 0.85)',
          borderRadius: '10px',
          border: '1px solid rgba(56, 189, 248, 0.25)',
          boxShadow: '0 4px 20px rgba(0, 0, 0, 0.25)'
        }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.85rem', flexWrap: 'wrap', gap: '0.6rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <span style={{ fontSize: '1.1rem' }}>🔎</span>
              <div>
                <h4 style={{ margin: 0, fontSize: '0.95rem', color: '#f8fafc', fontWeight: '600' }}>
                  Source Database Scan & Table Verification
                </h4>
                <p style={{ margin: 0, fontSize: '0.78rem', color: '#94a3b8' }}>
                  DDL is pulled <strong>only when table is found</strong> in source DB. Target tables are created with <strong>required columns alone</strong>.
                </p>
              </div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <span style={{
                padding: '3px 10px',
                borderRadius: '12px',
                background: scanResult.tables_found_count > 0 ? 'rgba(34, 197, 94, 0.15)' : 'rgba(148, 163, 184, 0.15)',
                border: scanResult.tables_found_count > 0 ? '1px solid rgba(34, 197, 94, 0.4)' : '1px solid rgba(148, 163, 184, 0.3)',
                color: scanResult.tables_found_count > 0 ? '#4ade80' : '#94a3b8',
                fontSize: '0.78rem',
                fontWeight: '600'
              }}>
                ✓ {scanResult.tables_found_count} Found in Source DB (DDL Pulled)
              </span>
              {scanResult.tables_missing_count > 0 && (
                <span style={{
                  padding: '3px 10px',
                  borderRadius: '12px',
                  background: 'rgba(245, 158, 11, 0.12)',
                  border: '1px solid rgba(245, 158, 11, 0.35)',
                  color: '#fbbf24',
                  fontSize: '0.78rem',
                  fontWeight: '600'
                }}>
                  ⚠️ {scanResult.tables_missing_count} Not Found (DDL Omitted)
                </span>
              )}
            </div>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(360px, 1fr))', gap: '0.75rem' }}>
            {scanResult.table_audit.map((t, idx) => (
              <div key={idx} style={{
                padding: '0.85rem 1rem',
                borderRadius: '8px',
                background: t.table_found ? 'rgba(34, 197, 94, 0.04)' : 'rgba(239, 68, 68, 0.05)',
                border: t.table_found ? '1px solid rgba(34, 197, 94, 0.25)' : '1px solid rgba(239, 68, 68, 0.35)',
                display: 'flex',
                flexDirection: 'column',
                gap: '0.45rem'
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '0.5rem' }}>
                  <span style={{ fontFamily: 'monospace', fontWeight: '600', color: '#e2e8f0', fontSize: '0.86rem' }}>
                    {t.source_schema ? `${t.source_schema}.${t.table_name}` : t.table_name}
                  </span>
                  <span style={{
                    padding: '2px 8px',
                    borderRadius: '4px',
                    fontSize: '0.72rem',
                    fontWeight: '600',
                    background: t.table_found ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)',
                    color: t.table_found ? '#4ade80' : '#f87171'
                  }}>
                    {t.table_found ? `✓ Found in ${t.found_in_db || 'Source DB'}` : '❌ Table Not Found'}
                  </span>
                </div>

                {t.table_found ? (
                  <div>
                    <div style={{ fontSize: '0.76rem', color: '#38bdf8', marginBottom: '0.3rem' }}>
                      🎯 <strong>{t.target_required_columns_count} Required Columns</strong> created in Target (filtered from {t.source_columns_count} columns in source DB)
                    </div>
                    {t.target_required_columns && t.target_required_columns.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px' }}>
                        {t.target_required_columns.map((colName, cIdx) => (
                          <span key={cIdx} style={{
                            padding: '1px 7px',
                            borderRadius: '3px',
                            background: 'rgba(56, 189, 248, 0.15)',
                            border: '1px solid rgba(56, 189, 248, 0.3)',
                            color: '#7dd3fc',
                            fontSize: '0.72rem',
                            fontFamily: 'monospace'
                          }}>
                            {colName}
                          </span>
                        ))}
                      </div>
                    )}
                    {t.source_columns_count > t.target_required_columns_count && (
                      <div style={{ fontSize: '0.71rem', color: '#94a3b8', marginTop: '0.25rem' }}>
                        Excluded {t.source_columns_count - t.target_required_columns_count} unused operational columns.
                      </div>
                    )}
                  </div>
                ) : (
                  <div style={{ fontSize: '0.76rem', color: '#fca5a5' }}>
                    ❌ <strong>Table Not Found</strong>: {t.message || `Table and schema were not found in source database.`}
                    <div style={{ color: '#94a3b8', fontSize: '0.72rem', marginTop: '0.25rem' }}>
                      DDL was NOT pulled. Target table creation omitted.
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Awaiting .kdb / Source Credentials Banner */}
      {kdbRequirementMessage && (
        <div style={{
          background: 'rgba(245, 158, 11, 0.08)',
          border: '1px solid rgba(245, 158, 11, 0.4)',
          borderRadius: '8px',
          padding: '0.85rem 1.25rem',
          margin: '0.8rem 0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          color: '#fef3c7',
          fontSize: '0.86rem',
        }}>
          <div>
            <strong>⚠️ Notice: </strong>{kdbRequirementMessage}
          </div>
          <button
            className="btn-run-builder"
            style={{ padding: '0.4rem 1rem', fontSize: '0.8rem' }}
            onClick={() => {
              setVaultScope('both')
              setConfigMode('vault')
              setShowConfigModal(true)
            }}
          >
            🔐 Import .kdb Now
          </button>
        </div>
      )}

      {/* Progressive LLM Building Banner */}
      {building && (
        <div className="building-progress-card">
          <div className="spinner-cyan" />
          <div className="building-text-wrap">
            <span className="building-step-label">{buildStep}</span>
            <span className="building-sub">
              Reading sources, R1–R10 cleansing filters, R11 balance dataset staging, and derived column CASE expressions.
            </span>
          </div>
        </div>
      )}

      {/* ── Main Architecture Studio Workspace ── */}
      {currentArtifact ? (
        <div className="target-workspace-grid">
          {/* Left: Code & Logic Viewer */}
          <div className="target-editor-panel">
            {/* Sub-tabs header */}
            <div className="target-tabs-bar">
              <div className="target-tabs-left">
                <button
                  className={`target-tab-item ${codeTab === 'ddl' ? 'active' : ''}`}
                  onClick={() => setCodeTab('ddl')}
                  title="Target tables created taking structure from source with logic columns alone"
                >
                  <span>🏛️</span> Target Tables DDL (Source Structure & Logic Columns Alone)
                </button>
                <button
                  className={`target-tab-item ${codeTab === 'sql' ? 'active' : ''}`}
                  onClick={() => setCodeTab('sql')}
                  title="Executable SQL transformations implementing HLA business rules R1-R15"
                >
                  <span>⚡</span> Transformation SQL (HLA Logic)
                </button>
                <button
                  className={`target-tab-item ${codeTab === 'pyspark' ? 'active' : ''}`}
                  onClick={() => setCodeTab('pyspark')}
                >
                  <span>🐍</span> PySpark ETL Pipeline
                </button>
                <button
                  className={`target-tab-item ${codeTab === 'reasoning' ? 'active' : ''}`}
                  onClick={() => setCodeTab('reasoning')}
                >
                  <span>🧠</span> Architectural Reasoning
                </button>
              </div>

              <div className="target-tabs-actions">
                <button className="btn-action-small" onClick={handleCopyCode} title="Copy code to clipboard">
                  {copied ? '✓ Copied' : '📋 Copy'}
                </button>
                <button className="btn-action-small" onClick={handleDownloadCode} title="Download file">
                  💾 Download
                </button>
              </div>
            </div>

            {/* Code Body */}
            <div className="target-code-viewer">
              <pre className="code-content-block">
                <code>{getCodeContent()}</code>
              </pre>
            </div>
          </div>

          {/* Right: Deployment & Verification Control Center */}
          <div className="target-deploy-panel">
            {/* Deployment Status Card */}
            <div className="deploy-control-card">
              <div className="deploy-card-header">
                <h4>🚀 Target DB Deployment Center</h4>
                <span className={`status-pill ${currentArtifact.deployment_status}`}>
                  {currentArtifact.deployment_status.toUpperCase()}
                </span>
              </div>

              <div className="deploy-meta-grid">
                <div className="deploy-meta-cell">
                  <span className="meta-k">Source Status</span>
                  <span className="meta-v" style={{ color: (scanResult && scanResult.tables_missing_count > 0) ? '#f87171' : 'var(--cyan-400)' }}>
                    {(scanResult && scanResult.tables_missing_count > 0) ? 'Sources Missing ⚠️' : 'Sources Verified ✓'}
                  </span>
                </div>
                <div className="deploy-meta-cell">
                  <span className="meta-k">Dialect</span>
                  <span className="meta-v">{currentArtifact.target_dialect?.toUpperCase()}</span>
                </div>
                <div className="deploy-meta-cell">
                  <span className="meta-k">Target Schema</span>
                  <span className="meta-v">{formatSchemaString(currentArtifact.target_schema)}</span>
                </div>
                <div className="deploy-meta-cell">
                  <span className="meta-k">Last Deployed</span>
                  <span className="meta-v">
                    {currentArtifact.deployed_at ? new Date(currentArtifact.deployed_at).toLocaleTimeString() : 'Never'}
                  </span>
                </div>
              </div>

              {/* Missing Sources Warning Banner & Quality Gate Details */}
              {scanResult && scanResult.tables_missing_count > 0 && (
                <div style={{
                  margin: '0.75rem 0',
                  padding: '0.85rem 1rem',
                  borderRadius: '8px',
                  background: 'rgba(239, 68, 68, 0.1)',
                  border: '1px solid rgba(239, 68, 68, 0.35)',
                  color: '#fca5a5',
                  fontSize: '0.78rem',
                  lineHeight: 1.45
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', fontWeight: 800, color: '#ef4444', marginBottom: '0.35rem', fontSize: '0.84rem' }}>
                    <span>⛔</span> Quality Gate: Upstream Sources Missing ({scanResult.tables_missing_count})
                  </div>
                  <div style={{ color: '#fca5a5', marginBottom: '0.5rem' }}>
                    Dry-Run Validation and Target Deployment are strictly <strong>blocked</strong> until upstream source tables exist in the source database.
                  </div>
                  <div style={{ background: 'rgba(0,0,0,0.35)', padding: '0.55rem 0.75rem', borderRadius: '6px', fontSize: '0.75rem', fontFamily: 'var(--font-mono)' }}>
                    <div style={{ marginBottom: '0.2rem' }}>
                      <strong style={{ color: '#93c5fd' }}>Source Database:</strong> {scanResult.configured_databases?.join(', ') || 'hla (hla_db)'}
                    </div>
                    <div style={{ marginBottom: '0.35rem' }}>
                      <strong style={{ color: '#93c5fd' }}>Validated Schemas:</strong> {[...new Set(scanResult.table_audit?.map((t) => t.source_schema || 'public'))].join(', ') || 'public'}
                    </div>
                    <div style={{ color: '#f87171', fontWeight: 700, marginBottom: '0.25rem' }}>Missing Source Objects:</div>
                    <ul style={{ margin: 0, paddingLeft: '1.2rem', color: '#cbd5e1' }}>
                      {scanResult.table_audit?.filter((t) => !t.table_found).map((t) => (
                        <li key={t.table_name} style={{ marginBottom: '0.15rem' }}>
                          <code style={{ color: '#fca5a5', fontWeight: 600 }}>
                            {t.source_schema ? `${t.source_schema}.${t.table_name}` : t.table_name}
                          </code>
                          {t.source_system ? <span style={{ color: '#94a3b8', marginLeft: '0.4rem' }}>({t.source_system})</span> : null}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              {!isViewer ? (
                <div className="deploy-btn-group">
                  <button
                    className="btn-validate"
                    onClick={() => handleDeployAction('validate')}
                    disabled={deploying || (scanResult && scanResult.tables_missing_count > 0)}
                    title={scanResult && scanResult.tables_missing_count > 0 ? "Blocked: Upstream source tables not found in source database" : "Test DDL syntax in rollback transaction"}
                  >
                    <span>🧪</span> {deploying && deployAction === 'validate' ? 'Validating…' : 'Validate & Dry-Run'}
                  </button>

                  <button
                    className={`btn-deploy-live ${activeEnv === 'prod' ? 'prod' : 'dev'}`}
                    onClick={() => handleDeployAction('deploy')}
                    disabled={deploying || (scanResult && scanResult.tables_missing_count > 0)}
                    title={scanResult && scanResult.tables_missing_count > 0 ? "Blocked: Upstream source tables not found in source database" : "Deploy tables into target database"}
                  >
                    <span>🚀</span> {deploying && deployAction === 'deploy' ? 'Deploying Tables…' : 'Deploy to Target'}
                  </button>
                </div>
              ) : (
                <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '0.5rem 0 0' }}>
                  Viewer accounts have read-only access. Deployment requires Admin or Architect privileges.
                </p>
              )}
            </div>

            {/* Live Deployment Console / Log */}
            <div className="deploy-terminal-card">
              <div className="terminal-bar">
                <div className="term-dots">
                  <span className="dot red" />
                  <span className="dot yellow" />
                  <span className="dot green" />
                </div>
                <span className="term-title">Target DB Deployment Console</span>
              </div>

              <div className="terminal-body">
                {deployResult ? (
                  <div>
                    <div className={`log-line ${deployResult.success ? 'success' : 'error'}`}>
                      {deployResult.success ? '✓ SUCCESS:' : '✕ ERROR:'} {deployResult.message}
                    </div>
                    {deployResult.deployed_tables && deployResult.deployed_tables.length > 0 && (
                      <div style={{ marginTop: '0.6rem' }}>
                        <div style={{ color: 'var(--cyan-400)', marginBottom: '0.4rem' }}>Verified Provisioned Tables in Target DB:</div>
                        <div className="tables-tag-wrap">
                          {deployResult.deployed_tables.map((t) => (
                            <span key={t} className="table-tag-pill">
                              {formatSchemaString(targetForm.schema_name)}.{t}
                            </span>
                          ))}
                        </div>
                      </div>
                    )}

                    {!deployResult.success && (deployResult.message?.includes('schema') || deployResult.message?.includes('does not exist') || deployResult.message?.includes('privilege')) && (
                      <div style={{
                        marginTop: '0.85rem',
                        padding: '0.75rem 1rem',
                        background: 'rgba(14, 165, 233, 0.1)',
                        border: '1px solid rgba(56, 189, 248, 0.35)',
                        borderRadius: '6px',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '1rem',
                        flexWrap: 'wrap',
                      }}>
                        <div style={{ fontSize: '0.82rem', color: '#bae6fd' }}>
                          💡 <strong>One-Click Fix:</strong> Switch Target Schema to standard <strong>public</strong> and rebuild target DDL:
                        </div>
                        <button
                          type="button"
                          className="btn-primary"
                          style={{ padding: '0.4rem 0.9rem', fontSize: '0.78rem', whiteSpace: 'nowrap' }}
                          onClick={handleAutoSwitchToPublicSchema}
                          disabled={switchingSchema || building}
                        >
                          {switchingSchema ? 'Switching & Rebuilding…' : '🔄 Auto-Switch to "public" & Rebuild'}
                        </button>
                      </div>
                    )}
                  </div>
                ) : currentArtifact.deployment_log ? (
                  <div className="log-line">
                    <span style={{ color: 'var(--text-muted)' }}>Previous log: </span>
                    {currentArtifact.deployment_log}
                  </div>
                ) : (
                  <div className="log-placeholder">
                    Ready to validate or deploy. Click "Validate & Dry-Run" to test DDL syntax in a rollback transaction, or "Deploy to Target" to provision tables.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      ) : (
        /* Empty State: Step-aware prompt */
        !hasSourceCreds ? (
          <div className="target-empty-card" style={{ borderColor: 'rgba(245, 158, 11, 0.4)', background: 'rgba(245, 158, 11, 0.03)' }}>
            <span style={{ fontSize: '2.8rem', display: 'block', marginBottom: '0.8rem' }}>🔐</span>
            <h3 style={{ color: '#ffffff', fontSize: '1.25rem', marginBottom: '0.5rem' }}>
              Step 2: Insert DB Credentials or Upload .kdb Vault File
            </h3>
            <p style={{ color: 'var(--text-dim)', maxWidth: '640px', margin: '0 auto 1.25rem', fontSize: '0.88rem', lineHeight: 1.6 }}>
              The HLA document has been scanned completely. Per architecture requirements, the target tables will be created in the target schema taking their structure from the upstream source tables with the <strong>HLA logic columns alone</strong>.
              <br /><br />
              Please insert your database credentials or upload a <code>.kdb</code> vault file so the engine can scan the source tables before creating the target tables.
            </p>
            {!isViewer && (
              <div style={{ display: 'flex', gap: '0.8rem', justifyContent: 'center', flexWrap: 'wrap' }}>
                <button
                  className="btn-run-builder"
                  style={{ padding: '0.75rem 1.6rem', background: 'linear-gradient(135deg, #0ea5e9, #0284c7)' }}
                  onClick={() => {
                    setVaultScope('both')
                    setConfigMode('vault')
                    setShowConfigModal(true)
                  }}
                >
                  <span>🔐</span> Import .kdb Vault File
                </button>
                <button
                  className="btn-edit-target"
                  style={{ padding: '0.75rem 1.4rem', border: '1px solid var(--border-color)', borderRadius: '8px', color: 'var(--text-bright)' }}
                  onClick={() => {
                    setConfigMode('manual')
                    setShowConfigModal(true)
                  }}
                >
                  <span>⚙️</span> Enter DB Credentials
                </button>
              </div>
            )}
          </div>
        ) : (
          <div className="target-empty-card">
            <span style={{ fontSize: '2.8rem', display: 'block', marginBottom: '0.8rem' }}>⚡</span>
            <h3 style={{ color: '#ffffff', fontSize: '1.25rem', marginBottom: '0.5rem' }}>
              Source Credentials Verified • Ready to Create Target Tables
            </h3>
            <p style={{ color: 'var(--text-dim)', maxWidth: '600px', margin: '0 auto 1.25rem', fontSize: '0.86rem', lineHeight: 1.5 }}>
              Source database credentials have been configured. Click below to scan the upstream source tables, extract their column structures for the <strong>HLA logic columns alone</strong>, and create the target tables and transformation logic.
            </p>
            {!isViewer && (
              <button
                className="btn-run-builder"
                style={{ margin: '0 auto', fontSize: '0.9rem', padding: '0.75rem 1.6rem' }}
                onClick={handleRunTargetBuilder}
                disabled={building || !selectedDocId}
              >
                <span>⚡</span> Build Target Logic with LLM
              </button>
            )}
          </div>
        )
      )}

      {/* ── Modal: Configure Target DB Credentials ── */}
      {showConfigModal && (
        <div className="modal-backdrop" onClick={() => setShowConfigModal(false)}>
          <div className="target-config-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>
                <span>🎯</span> Configure Credentials & Vault ({activeEnv.toUpperCase()})
              </h3>
              <button className="btn-close-modal" onClick={() => setShowConfigModal(false)}>✕</button>
            </div>

            {/* Mode Switcher Tabs */}
            <div className="target-mode-selector">
              <button
                type="button"
                className={`target-mode-tab ${configMode === 'manual' ? 'active' : ''}`}
                onClick={() => setConfigMode('manual')}
              >
                <span>✍️</span> Manual Target Form ({activeEnv.toUpperCase()})
              </button>
              <button
                type="button"
                className={`target-mode-tab ${configMode === 'vault' ? 'active' : ''}`}
                onClick={() => setConfigMode('vault')}
              >
                <span>🔐</span> Import .kdb Vault File
              </button>
            </div>

            {configMode === 'vault' && (
              <div style={{
                display: 'flex',
                gap: '1.2rem',
                padding: '0.6rem 1rem',
                margin: '0.5rem 1rem 0',
                background: 'var(--bg-card-secondary, rgba(255,255,255,0.03))',
                borderRadius: '6px',
                border: '1px solid var(--border-color)'
              }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.84rem' }}>
                  <input
                    type="radio"
                    name="vaultScope"
                    value="both"
                    checked={vaultScope === 'both'}
                    onChange={() => setVaultScope('both')}
                  />
                  <span>Master Vault (.kdb for Sources & Target)</span>
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', cursor: 'pointer', fontSize: '0.84rem' }}>
                  <input
                    type="radio"
                    name="vaultScope"
                    value="target"
                    checked={vaultScope === 'target'}
                    onChange={() => setVaultScope('target')}
                  />
                  <span>Target DB Only ({activeEnv.toUpperCase()})</span>
                </label>
              </div>
            )}

            {/* Mode 1: Manual Form */}
            {configMode === 'manual' && (
              <form onSubmit={handleSaveTargetConfig}>
                <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '0.45rem' }}>
                  <p style={{ margin: '0 0 0.2rem', fontSize: '0.80rem', color: 'var(--text-dim)', lineHeight: 1.35 }}>
                    Configure target connection credentials for environment <strong style={{ color: activeEnv === 'prod' ? 'var(--amber-400)' : 'var(--cyan-400)' }}>{activeEnv.toUpperCase()}</strong>.
                    DDL & transformation scripts will deploy to this database and schema.
                  </p>

                  {/* Engine / Dialect row */}
                  <div className="form-group" style={{ marginBottom: '0.15rem' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem', flexWrap: 'wrap', gap: '0.25rem' }}>
                      <label style={{ margin: 0, fontSize: '0.82rem', fontWeight: 600 }}>Target Database Engine / Cloud Dialect</label>
                      {/* Quick Cloud Presets as compact chips */}
                      <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ padding: '0.12rem 0.45rem', fontSize: '0.74rem', background: targetForm.db_type === 'postgresql' ? 'rgba(59, 130, 246, 0.25)' : 'rgba(59, 130, 246, 0.1)', border: '1px solid rgba(59, 130, 246, 0.35)' }}
                          onClick={() => setTargetForm(prev => ({
                            ...prev,
                            db_type: 'postgresql',
                            port: '5432',
                            schema_name: prev.schema_name || 'ra_ctrl.ctrl_23'
                          }))}
                        >
                          🐘 PostgreSQL
                        </button>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ padding: '0.12rem 0.45rem', fontSize: '0.74rem', background: targetForm.db_type === 'azure_sql' ? 'rgba(14, 165, 233, 0.25)' : 'rgba(14, 165, 233, 0.1)', border: '1px solid rgba(14, 165, 233, 0.35)' }}
                          onClick={() => setTargetForm(prev => ({
                            ...prev,
                            db_type: 'azure_sql',
                            port: '1433',
                            schema_name: 'dbo'
                          }))}
                        >
                          ☁️ Azure SQL
                        </button>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ padding: '0.12rem 0.45rem', fontSize: '0.74rem', background: targetForm.db_type === 'mysql' ? 'rgba(234, 88, 12, 0.25)' : 'rgba(234, 88, 12, 0.1)', border: '1px solid rgba(234, 88, 12, 0.35)' }}
                          onClick={() => setTargetForm(prev => ({
                            ...prev,
                            db_type: 'mysql',
                            port: '3306',
                            schema_name: 'target_db'
                          }))}
                        >
                          🐬 MySQL
                        </button>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ padding: '0.12rem 0.45rem', fontSize: '0.74rem', background: targetForm.db_type === 'snowflake' ? 'rgba(56, 189, 248, 0.25)' : 'rgba(56, 189, 248, 0.1)', border: '1px solid rgba(56, 189, 248, 0.35)' }}
                          onClick={() => setTargetForm(prev => ({
                            ...prev,
                            db_type: 'snowflake',
                            host: prev.host && prev.host !== 'localhost' ? prev.host : 'xy12345.us-east-1',
                            port: 'COMPUTE_WH',
                            schema_name: 'PUBLIC'
                          }))}
                        >
                          ❄️ Snowflake
                        </button>
                        <button
                          type="button"
                          className="btn-secondary"
                          style={{ padding: '0.12rem 0.45rem', fontSize: '0.74rem', background: targetForm.db_type === 'redshift' ? 'rgba(239, 68, 68, 0.25)' : 'rgba(239, 68, 68, 0.1)', border: '1px solid rgba(239, 68, 68, 0.35)' }}
                          onClick={() => setTargetForm(prev => ({
                            ...prev,
                            db_type: 'redshift',
                            port: '5439',
                            schema_name: 'public'
                          }))}
                        >
                          🔴 Redshift
                        </button>
                      </div>
                    </div>

                    <select
                      value={targetForm.db_type}
                      onChange={(e) => setTargetForm({
                        ...targetForm,
                        db_type: e.target.value,
                        port: e.target.value === 'snowflake' ? (targetForm.port && isNaN(Number(targetForm.port)) ? targetForm.port : 'COMPUTE_WH') : (targetForm.port && !isNaN(Number(targetForm.port)) ? targetForm.port : '5432'),
                        schema_name: e.target.value === 'snowflake' ? (targetForm.schema_name === 'ra_ctrl.ctrl_23' ? 'PUBLIC' : targetForm.schema_name) : targetForm.schema_name
                      })}
                      className="form-control"
                      style={{ padding: '0.4rem 0.65rem' }}
                    >
                      <optgroup label="Cloud Data Warehouses & Big Data">
                        <option value="snowflake">Snowflake Data Cloud</option>
                        <option value="redshift">AWS Redshift</option>
                        <option value="bigquery">Google Cloud BigQuery</option>
                      </optgroup>
                      <optgroup label="AWS Cloud Databases">
                        <option value="rds_postgres">AWS RDS PostgreSQL / Aurora</option>
                        <option value="rds_mysql">AWS RDS MySQL / Aurora</option>
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
                      </optgroup>
                      <optgroup label="Standard Enterprise Relational">
                        <option value="postgresql">PostgreSQL</option>
                        <option value="mssql">Microsoft SQL Server (MSSQL)</option>
                        <option value="mysql">MySQL / MariaDB</option>
                        <option value="oracle">Oracle Database</option>
                        <option value="sqlite">SQLite / DuckDB</option>
                        <option value="sandbox">Sandbox (Simulated Cluster)</option>
                      </optgroup>
                    </select>
                  </div>

                  {/* Row 2: Schema + Host */}
                  <div className="form-row-2col">
                    <div className="form-group">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                        <label style={{ margin: 0, fontSize: '0.82rem' }}>Target Schema Namespace</label>
                        <div style={{ display: 'flex', gap: '0.3rem' }}>
                          <button
                            type="button"
                            style={{ fontSize: '0.70rem', padding: '1px 6px', background: 'rgba(56, 189, 248, 0.15)', border: '1px solid rgba(56, 189, 248, 0.3)', borderRadius: '4px', color: '#38bdf8', cursor: 'pointer' }}
                            onClick={() => setTargetForm({ ...targetForm, schema_name: 'public' })}
                            title="Set schema to public"
                          >
                            public
                          </button>
                          <button
                            type="button"
                            style={{ fontSize: '0.70rem', padding: '1px 6px', background: 'rgba(16, 185, 129, 0.15)', border: '1px solid rgba(16, 185, 129, 0.3)', borderRadius: '4px', color: '#34d399', cursor: 'pointer' }}
                            onClick={() => setTargetForm({ ...targetForm, schema_name: '' })}
                            title="Deploy directly matching source table names (no schema prefix)"
                          >
                            Same as Source
                          </button>
                        </div>
                      </div>
                      <input
                        type="text"
                        value={targetForm.schema_name ?? ''}
                        onChange={(e) => setTargetForm({ ...targetForm, schema_name: e.target.value })}
                        placeholder={targetForm.db_type === 'snowflake' ? 'PUBLIC' : 'public (or blank)'}
                        className="form-control"
                        style={{ padding: '0.4rem 0.65rem' }}
                      />
                    </div>

                    <div className="form-group">
                      <label style={{ marginBottom: '0.25rem', fontSize: '0.82rem', display: 'block' }}>{targetForm.db_type === 'snowflake' ? 'Snowflake Account Identifier' : 'Host / Endpoint'}</label>
                      <input
                        type="text"
                        value={targetForm.host}
                        onChange={(e) => setTargetForm({ ...targetForm, host: e.target.value })}
                        placeholder={targetForm.db_type === 'snowflake' ? 'e.g. xy12345.us-east-1' : 'localhost or host IP'}
                        className="form-control"
                        style={{ padding: '0.4rem 0.65rem' }}
                        required
                      />
                    </div>
                  </div>

                  {/* Row 3: Database Name + Port */}
                  <div className="form-row-2col">
                    <div className="form-group">
                      <label style={{ marginBottom: '0.25rem', fontSize: '0.82rem', display: 'block' }}>Database Name</label>
                      <input
                        type="text"
                        value={targetForm.database_name}
                        onChange={(e) => setTargetForm({ ...targetForm, database_name: e.target.value })}
                        placeholder="hla_db"
                        className="form-control"
                        style={{ padding: '0.4rem 0.65rem' }}
                        required
                      />
                    </div>

                    <div className="form-group">
                      <label style={{ marginBottom: '0.25rem', fontSize: '0.82rem', display: 'block' }}>{targetForm.db_type === 'snowflake' ? 'Warehouse (Compute Cluster)' : 'Port'}</label>
                      <input
                        type="text"
                        value={targetForm.port}
                        onChange={(e) => setTargetForm({ ...targetForm, port: e.target.value })}
                        placeholder={targetForm.db_type === 'snowflake' ? 'COMPUTE_WH' : '5432'}
                        className="form-control"
                        style={{ padding: '0.4rem 0.65rem' }}
                      />
                    </div>
                  </div>

                  {/* Row 4: Username + Password */}
                  <div className="form-row-2col">
                    <div className="form-group">
                      <label style={{ marginBottom: '0.25rem', fontSize: '0.82rem', display: 'block' }}>Username</label>
                      <input
                        type="text"
                        value={targetForm.username}
                        onChange={(e) => setTargetForm({ ...targetForm, username: e.target.value })}
                        placeholder="postgres"
                        className="form-control"
                        style={{ padding: '0.4rem 0.65rem' }}
                        required
                      />
                    </div>

                    <div className="form-group">
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.25rem' }}>
                        <label style={{ margin: 0, fontSize: '0.82rem' }}>Password</label>
                        {targetConfigs[activeEnv]?.has_password && (
                          <span style={{ fontSize: '0.72rem', color: '#4ade80', fontWeight: '600' }}>
                            🔒 Saved in Vault
                          </span>
                        )}
                      </div>
                      <input
                        type="password"
                        value={targetForm.password}
                        onChange={(e) => setTargetForm({ ...targetForm, password: e.target.value })}
                        placeholder={targetConfigs[activeEnv]?.has_password ? "•••••••• (Saved — leave blank)" : "Enter password"}
                        className="form-control"
                        style={{ padding: '0.4rem 0.65rem' }}
                      />
                    </div>
                  </div>

                  {/* Sync to both environments toggle */}
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem',
                    padding: '0.35rem 0.65rem',
                    background: 'rgba(56, 189, 248, 0.08)',
                    borderRadius: '6px',
                    border: '1px solid rgba(56, 189, 248, 0.25)',
                    marginTop: '0.1rem'
                  }}>
                    <input
                      type="checkbox"
                      id="sync_both_targets_check"
                      checked={applyToBoth}
                      onChange={(e) => setApplyToBoth(e.target.checked)}
                      style={{ cursor: 'pointer', width: '14px', height: '14px' }}
                    />
                    <label htmlFor="sync_both_targets_check" style={{ fontSize: '0.80rem', color: 'var(--text-bright)', cursor: 'pointer', margin: 0 }}>
                      Sync these target settings to both <strong>DEV</strong> and <strong>PROD</strong> environments
                    </label>
                  </div>

                  {testResult && (
                    <div className={`test-feedback-box ${testResult.success ? 'success' : 'error'}`} style={{ padding: '0.35rem 0.65rem', fontSize: '0.82rem', marginTop: '0.15rem' }}>
                      <span>{testResult.success ? '✓' : '✕'}</span>
                      <span>{testResult.message}</span>
                    </div>
                  )}
                </div>

                <div className="modal-footer" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={handleTestTargetConnection}
                    disabled={testingConn}
                  >
                    {testingConn ? 'Testing…' : '🔍 Test Connection'}
                  </button>

                  <div style={{ display: 'flex', gap: '0.6rem' }}>
                    <button type="button" className="btn-secondary" onClick={() => setShowConfigModal(false)}>
                      Cancel
                    </button>
                    <button type="submit" className="btn-primary" disabled={savingConfig}>
                      {savingConfig ? 'Saving…' : 'Save Configuration'}
                    </button>
                  </div>
                </div>
              </form>
            )}

            {/* Mode 2: Upload or Paste .kdb / Credential Vault File */}
            {configMode === 'vault' && (
              <form onSubmit={handleTargetVaultUpload}>
                <div className="modal-body" style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem' }}>
                  <div className="target-vault-intro">
                    <p style={{ margin: 0, fontSize: '0.80rem', color: 'var(--text-dim)', lineHeight: 1.35 }}>
                      Upload or paste a <strong style={{ color: 'var(--primary)' }}>.kdb, .ini, .json, .yaml, or .xml</strong> vault file for Target DB.
                      Sections can specify <code style={{ color: '#38bdf8' }}>[target.dev]</code> and <code style={{ color: '#f59e0b' }}>[target.prod]</code>, or a unified block auto-assigned to <strong style={{ color: activeEnv === 'prod' ? 'var(--amber-400)' : 'var(--cyan-400)' }}>{activeEnv.toUpperCase()}</strong>.
                    </p>
                  </div>

                  {/* File Dropzone */}
                  <div className="vault-file-box" style={{ padding: '0.75rem 1rem' }}>
                    <input
                      type="file"
                      id="target-vault-file-input"
                      accept=".kdb,.ini,.json,.yaml,.yml,.xml,.txt"
                      onChange={(e) => setVaultFile(e.target.files[0] || null)}
                      style={{ display: 'none' }}
                    />
                    <label htmlFor="target-vault-file-input" className="vault-drop-label" style={{ gap: '0.65rem' }}>
                      <span style={{ fontSize: '1.4rem' }}>📁</span>
                      <div>
                        <span style={{ color: '#ffffff', fontWeight: 700, fontSize: '0.85rem' }}>
                          {vaultFile ? vaultFile.name : 'Choose a Target .kdb / Vault file or drag & drop'}
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
                        Or Paste .kdb Config Text:
                      </span>
                      <div style={{ display: 'flex', gap: '0.35rem' }}>
                        <button
                          type="button"
                          className="btn-template-hint"
                          onClick={handleLoadSampleTargetTemplate}
                          style={{ padding: '0.15rem 0.45rem', fontSize: '0.72rem' }}
                        >
                          Load Sample Template
                        </button>
                        <button
                          type="button"
                          className="btn-template-hint"
                          onClick={handleDownloadSampleTargetKdb}
                          title="Download sample target .kdb file"
                          style={{ padding: '0.15rem 0.45rem', fontSize: '0.72rem' }}
                        >
                          💾 Sample .kdb
                        </button>
                      </div>
                    </div>
                    <textarea
                      className="vault-textarea"
                      rows={4}
                      value={vaultText}
                      onChange={(e) => setVaultText(e.target.value)}
                      placeholder={`[target.dev]\nhost = localhost\nport = 5432\ndatabase = hla_db\nusername = postgres\npassword = your_password_here\nschema = target_dev\n\n[target.prod]\nhost = localhost\nport = 5432\ndatabase = hla_db\nusername = postgres\npassword = your_password_here\nschema = target_prod`}
                    />
                  </div>

                  {/* Feedback Box */}
                  {vaultFeedback && (
                    <div className={`test-feedback-box ${vaultFeedback.success ? 'success' : 'error'}`}>
                      <span>{vaultFeedback.success ? '✓' : '✕'}</span>
                      <div>
                        <div>{vaultFeedback.message}</div>
                        {vaultFeedback.configured_envs && (
                          <div style={{ marginTop: '0.3rem', fontSize: '0.76rem', opacity: 0.9 }}>
                            Configured Environments: {vaultFeedback.configured_envs.join(', ').toUpperCase()}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>

                <div className="modal-footer" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <button
                    type="button"
                    className="btn-secondary"
                    onClick={() => setShowConfigModal(false)}
                  >
                    Close
                  </button>

                  <div style={{ display: 'flex', gap: '0.6rem' }}>
                    <button
                      type="submit"
                      className="btn-primary"
                      disabled={uploadingVault}
                    >
                      {uploadingVault ? 'Parsing & Verifying…' : '⚡ Parse & Configure Target DB'}
                    </button>
                  </div>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
