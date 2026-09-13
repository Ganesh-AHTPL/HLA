import { useState, useEffect } from 'react'
import axios from 'axios'
import './ProjectExplorer.css'

export default function ProjectExplorer({ projects: initialProjects = [], onRefreshProjects, onSelectProject, currentUser }) {
  const [projects, setProjects] = useState(initialProjects || [])
  const [loading, setLoading] = useState(false)
  const [showModal, setShowModal] = useState(false)
  const [projectName, setProjectName] = useState('')
  const [projectDesc, setProjectDesc] = useState('')
  const [searchQuery, setSearchQuery] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [errorMsg, setErrorMsg] = useState('')

  const userRole = currentUser?.role?.toLowerCase() || 'viewer'
  const canCreate = ['admin', 'architect'].includes(userRole)
  const canDelete = userRole === 'admin'

  // Synchronize with parent projects prop whenever it updates
  useEffect(() => {
    if (initialProjects && initialProjects.length > 0) {
      setProjects(initialProjects)
    }
  }, [initialProjects])

  const fetchProjects = async () => {
    const token = localStorage.getItem('hla_token') || localStorage.getItem('access_token')
    if (!token || !currentUser) {
      // Unauthenticated: do not call /api/projects
      return
    }

    setLoading(true)
    setErrorMsg('')
    try {
      const config = { headers: { Authorization: `Bearer ${token}` } }
      const res = await axios.get('/api/projects', config)
      const list = res.data || []
      setProjects(list)
      if (onRefreshProjects) {
        onRefreshProjects()
      }
    } catch (err) {
      if (err.response?.status !== 401) {
        setErrorMsg(err.response?.data?.error || 'Failed to load projects.')
      }
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    const token = localStorage.getItem('hla_token') || localStorage.getItem('access_token')
    if (currentUser && token) {
      fetchProjects()
    }
  }, [currentUser])

  const handleCreateProject = async (e) => {
    e.preventDefault()
    if (!projectName.trim()) return

    setSubmitting(true)
    setErrorMsg('')
    try {
      const res = await axios.post('/api/projects', {
        name: projectName.trim(),
        description: projectDesc.trim(),
      })
      setShowModal(false)
      setProjectName('')
      setProjectDesc('')
      const newProj = res.data.project
      await fetchProjects()
      if (onRefreshProjects) await onRefreshProjects()
      if (newProj && onSelectProject) {
        onSelectProject(newProj)
      }
    } catch (err) {
      setErrorMsg(err.response?.data?.error || 'Failed to create project.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleDeleteProject = async (e, projectId, projectName) => {
    e.stopPropagation()
    if (!window.confirm(`Are you sure you want to delete folder '${projectName}' and all its uploaded HLA files?`)) {
      return
    }

    try {
      await axios.delete(`/api/projects/${projectId}`)
      await fetchProjects()
      if (onRefreshProjects) await onRefreshProjects()
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to delete project.')
    }
  }

  // Active projects: prioritize whichever is populated so 0 is never displayed when projects exist
  const activeProjects = (projects && projects.length > 0)
    ? projects
    : (initialProjects && initialProjects.length > 0 ? initialProjects : [])

  // Filter projects by search query
  const filteredProjects = activeProjects.filter(p => {
    if (!searchQuery.trim()) return true
    const q = searchQuery.toLowerCase()
    return (
      p.name.toLowerCase().includes(q) ||
      (p.description && p.description.toLowerCase().includes(q)) ||
      (p.created_by && p.created_by.toLowerCase().includes(q))
    )
  })

  // Calculate high-level stats
  const totalDocs = activeProjects.reduce((sum, p) => sum + (p.document_count || 0), 0)
  const totalDBs = activeProjects.reduce((sum, p) => sum + (p.connection_count || 0), 0)

  return (
    <div className="project-explorer" id="project-explorer">
      {/* ── Studio Hero & Search Strip ── */}
      <div className="explorer-hero-card">
        <div className="explorer-hero-left">
          <div
            className="explorer-badge"
            aria-hidden="true"
            style={{ userSelect: 'none', WebkitUserSelect: 'none', caretColor: 'transparent', pointerEvents: 'none' }}
          >
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <span style={{ userSelect: 'none', WebkitUserSelect: 'none', caretColor: 'transparent', pointerEvents: 'none' }}>Architecture Workspaces</span>
          </div>
          <h2>Solution Design Workspaces</h2>
          <p className="explorer-hero-desc">
            Isolated project workspaces for High-Level Architecture (HLA) specifications. Ingest architecture documents, configure source/target databases, and generate executable ETL pipelines.
          </p>

          <div className="explorer-quick-stats">
            <div className="stat-item">
              <span className="stat-num">{projects.length}</span>
              <span className="stat-lbl">Workspaces</span>
            </div>
            <div className="stat-divider" />
            <div className="stat-item">
              <span className="stat-num">{totalDocs}</span>
              <span className="stat-lbl">HLA Documents</span>
            </div>
            <div className="stat-divider" />
            <div className="stat-item">
              <span className="stat-num">{totalDBs}</span>
              <span className="stat-lbl">Connections</span>
            </div>
          </div>
        </div>

        <div className="explorer-hero-right">
          {canCreate ? (
            <button
              className="btn-primary"
              onClick={() => setShowModal(true)}
              id="btn-create-project"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19"/>
                <line x1="5" y1="12" x2="19" y2="12"/>
              </svg>
              <span>New Workspace</span>
            </button>
          ) : (
            <div className="viewer-mode-badge">
              <span>Viewer Access (Read-Only)</span>
            </div>
          )}
        </div>
      </div>

      {/* ── Search & Filter Toolbar ── */}
      <div className="explorer-toolbar">
        <div className="search-bar-wrap">
          <svg className="search-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8"/>
            <line x1="21" y1="21" x2="16.65" y2="16.65"/>
          </svg>
          <input
            type="text"
            placeholder="Search workspaces by name, description, or creator…"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="search-input"
          />
          {searchQuery && (
            <button className="clear-btn" onClick={() => setSearchQuery('')} aria-label="Clear search">✕</button>
          )}
        </div>

        <div className="toolbar-info">
          <span>{filteredProjects.length} {filteredProjects.length === 1 ? 'workspace' : 'workspaces'}</span>
        </div>
      </div>

      {errorMsg && (
        <div className="explorer-error-banner">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="12" cy="12" r="10"/>
            <line x1="12" y1="8" x2="12" y2="12"/>
            <line x1="12" y1="16" x2="12.01" y2="16"/>
          </svg>
          <span>{errorMsg}</span>
        </div>
      )}

      {/* ── Folders Grid ── */}
      {loading ? (
        <div className="explorer-loading-state">
          <div className="spinner-primary" />
          <span>Loading workspaces…</span>
        </div>
      ) : (
        <div className="folders-grid">
          {/* New Folder Quick Action Card */}
          {canCreate && !searchQuery && (
            <div
              className="folder-card new-folder-dash-card"
              onClick={() => setShowModal(true)}
            >
              <div className="dash-card-content">
                <div className="dash-icon-wrap">
                  <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19"/>
                    <line x1="5" y1="12" x2="19" y2="12"/>
                  </svg>
                </div>
                <h4>Create New Workspace</h4>
                <p>Add a new workspace to ingest architecture documents and extract ETL logic.</p>
              </div>
            </div>
          )}

          {filteredProjects.map((proj) => {
            return (
              <div
                key={proj.id}
                className="folder-card"
                onClick={() => onSelectProject(proj)}
                title={`Open workspace: ${proj.name}`}
              >
                <div className="folder-card-top">
                  <div className="folder-icon-wrap">
                    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                    </svg>
                  </div>
                  <div className="folder-title-block">
                    <h3 className="folder-title">{proj.name}</h3>
                    <p className="folder-desc">
                      {proj.description || 'Architecture design & ETL reconciliation workspace'}
                    </p>
                  </div>
                </div>

                <div className="folder-card-meta">
                  <div className="meta-badge-row">
                    <span className="meta-badge">
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                        <polyline points="14 2 14 8 20 8"/>
                      </svg>
                      {proj.document_count} {proj.document_count === 1 ? 'Doc' : 'Docs'}
                    </span>
                    {proj.connection_count > 0 && (
                      <span className="meta-badge">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <ellipse cx="12" cy="5" rx="9" ry="3"/>
                          <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
                          <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
                        </svg>
                        {proj.connection_count} DBs
                      </span>
                    )}
                    {proj.created_by && (
                      <span className="meta-badge">
                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/>
                          <circle cx="12" cy="7" r="4"/>
                        </svg>
                        {proj.created_by}
                      </span>
                    )}
                  </div>
                </div>

                <div className="folder-card-footer">
                  <span className="open-studio-link">
                    Open Workspace
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <line x1="5" y1="12" x2="19" y2="12"/>
                      <polyline points="12 5 19 12 12 19"/>
                    </svg>
                  </span>
                  {canDelete && (
                    <button
                      className="btn-trash-folder"
                      onClick={(e) => handleDeleteProject(e, proj.id, proj.name)}
                      title="Delete workspace (Admin only)"
                      aria-label="Delete workspace"
                      id={`btn-delete-proj-${proj.id}`}
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                        <polyline points="3 6 5 6 21 6"/>
                        <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                      </svg>
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* ── Modal: Create New Project Folder ── */}
      {showModal && (
        <div className="explorer-modal-overlay" onClick={() => setShowModal(false)}>
          <div className="explorer-modal" onClick={(e) => e.stopPropagation()}>
            <div className="explorer-modal-header">
              <div className="modal-title-wrap">
                <div className="modal-icon-badge">
                  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                  </svg>
                </div>
                <div>
                  <h3>New Workspace</h3>
                  <p>Create an isolated environment for your HLA project</p>
                </div>
              </div>
              <button
                className="close-modal-btn"
                onClick={() => setShowModal(false)}
                aria-label="Close"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleCreateProject}>
              <div className="explorer-modal-body">
                <div className="form-group">
                  <label htmlFor="modal-project-name">
                    Workspace Name <span style={{ color: 'var(--danger)' }}>*</span>
                  </label>
                  <input
                    id="modal-project-name"
                    type="text"
                    placeholder="e.g. Telecom Billing Reconciliation, Core ODS Modernization"
                    value={projectName}
                    onChange={(e) => setProjectName(e.target.value)}
                    required
                    autoFocus
                  />
                </div>

                <div className="form-group">
                  <label htmlFor="modal-project-desc">Description (Optional)</label>
                  <textarea
                    id="modal-project-desc"
                    rows="3"
                    placeholder="Brief description of the solution architecture, data lake sources, and target requirements…"
                    value={projectDesc}
                    onChange={(e) => setProjectDesc(e.target.value)}
                  />
                </div>
              </div>

              <div className="explorer-modal-footer">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={submitting || !projectName.trim()}
                  id="btn-submit-create-proj"
                >
                  {submitting ? 'Creating…' : 'Create Workspace'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
