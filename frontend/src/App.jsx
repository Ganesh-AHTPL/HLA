import { useState, useEffect } from 'react'
import axios from 'axios'
import Sidebar from './components/Sidebar'
import TopBar from './components/TopBar'
import ProjectExplorer from './components/ProjectExplorer'
import FileUpload from './components/FileUpload'
import DocumentAnalysis from './components/DocumentAnalysis'
import SourceDBManager from './components/SourceDBManager'
import TargetDBStudio from './components/TargetDBStudio'
import ControlScheduler from './components/ControlScheduler'
import HlaStudioWorkbench from './components/HlaStudioWorkbench'
import LoginModal from './components/LoginModal'
import UserManagementModal from './components/UserManagementModal'
import RulesModal from './components/RulesModal'
import GlobalIntrospectModal from './components/GlobalIntrospectModal'
import RoleInfoModal from './components/RoleInfoModal'
import './components/LoginModal.css'
import './components/UserManagementModal.css'
import './components/RulesModal.css'
import './components/GlobalIntrospectModal.css'
import './styles/hlaStudio.css'
import './index.css'

function App() {
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const saved = localStorage.getItem('hla_user')
      return saved ? JSON.parse(saved) : null
    } catch (e) {
      return null
    }
  })
  const [authToken, setAuthToken] = useState(() => {
    const t = localStorage.getItem('hla_token') || localStorage.getItem('access_token') || ''
    if (t) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${t}`
    }
    return t
  })
  const [showLoginModal, setShowLoginModal] = useState(false)
  const [showUserMgmt, setShowUserMgmt] = useState(false)
  const [showRulesModal, setShowRulesModal] = useState(false)
  const [showIntrospectModal, setShowIntrospectModal] = useState(false)
  const [showRoleInfoModal, setShowRoleInfoModal] = useState(false)

  // Navigation views: 'workspaces' | 'project-studio'
  const [activeView, setActiveView] = useState('workspaces')

  // Project and Document state
  const [projectsList, setProjectsList] = useState([])
  const [activeProject, setActiveProject] = useState(null)
  const [projectDocs, setProjectDocs] = useState([])
  const [selectedDocId, setSelectedDocId] = useState(null)
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [projectStudioTab, setProjectStudioTab] = useState('workbench') // 'workbench' | 'ingest' | 'connectors' | 'targetdb' | 'scheduler'
  const [sideSearch, setSideSearch] = useState('')
  const [toastMsg, setToastMsg] = useState('')
  const [cmdkOpen, setCmdkOpen] = useState(false)
  const [cmdkQuery, setCmdkQuery] = useState('')
  const [refreshing, setRefreshing] = useState(false)
  const [theme, setTheme] = useState(() => localStorage.getItem('hla_theme') || 'dark')

  const showToast = (msg) => {
    setToastMsg(msg)
    setTimeout(() => setToastMsg(''), 2600)
  }

  const doRefresh = async () => {
    setRefreshing(true)
    if (activeProject?.id) {
      await fetchProjectDetails(activeProject.id)
    }
    await fetchProjectsSummary()
    setRefreshing(false)
    showToast('Workspace refreshed')
  }

  useEffect(() => {
    const handleKeyDown = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCmdkOpen((prev) => !prev)
      }
      if (e.key === 'Escape') {
        setCmdkOpen(false)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
    localStorage.setItem('hla_theme', theme)
  }, [theme])

  const toggleTheme = () => {
    setTheme(prev => (prev === 'dark' ? 'light' : 'dark'))
  }

  // Initialize session: restore saved token and verify with backend, otherwise enforce login
  useEffect(() => {
    const initSession = async () => {
      let token = authToken || localStorage.getItem('hla_token') || localStorage.getItem('access_token')
      let user = currentUser
      if (!user) {
        try {
          const saved = localStorage.getItem('hla_user')
          if (saved) user = JSON.parse(saved)
        } catch (e) {}
      }

      if (!token || !user) {
        // No authenticated credentials stored -> enforce login
        setCurrentUser(null)
        setAuthToken('')
        setShowLoginModal(true)
        return
      }

      // Verify token with backend /api/auth/me
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`
      try {
        const meRes = await axios.get('/api/auth/me')
        if (meRes.data?.user) {
          const freshUser = meRes.data.user
          setCurrentUser(freshUser)
          localStorage.setItem('hla_user', JSON.stringify(freshUser))
          setShowLoginModal(false)
          fetchProjectsSummary()
        }
      } catch (err) {
        console.warn('Session verification failed, logging out:', err)
        handleLogout()
      }
    }

    initSession()

    const handleExpired = () => {
      handleLogout()
    }
    window.addEventListener('auth:session_expired', handleExpired)
    return () => window.removeEventListener('auth:session_expired', handleExpired)
  }, [])

  // Axios 401 interceptor
  useEffect(() => {
    const interceptor = axios.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response && error.response.status === 401) {
          handleLogout()
        }
        return Promise.reject(error)
      }
    )
    return () => axios.interceptors.response.eject(interceptor)
  }, [])

  // Load project details when activeProject changes
  useEffect(() => {
    if (activeProject?.id && authToken) {
      fetchProjectDetails(activeProject.id)
    } else {
      setProjectDocs([])
      setSelectedDocId(null)
    }
  }, [activeProject?.id, authToken])

  const fetchProjectsSummary = async () => {
    const token = authToken || localStorage.getItem('hla_token') || localStorage.getItem('access_token')
    if (!currentUser || !token) {
      return
    }
    try {
      const res = await axios.get('/api/projects', {
        headers: { Authorization: `Bearer ${token}` }
      })
      const list = res.data || []
      setProjectsList(list)
    } catch (err) {
      console.error('Failed to load projects count:', err)
    }
  }

  // Ensure projects are refreshed whenever viewing the workspaces explorer
  useEffect(() => {
    if (currentUser && authToken && activeView === 'workspaces') {
      fetchProjectsSummary()
    }
  }, [authToken, currentUser, activeView])

  const fetchProjectDetails = async (projectId) => {
    setLoadingDocs(true)
    try {
      const res = await axios.get(`/api/projects/${projectId}`)
      const proj = res.data || {}
      setActiveProject(proj)
      const docs = proj.documents || []
      setProjectDocs(docs)
      if (docs.length > 0) {
        setSelectedDocId((prev) => (prev && docs.some(d => d.id === prev) ? prev : docs[0].id))
      } else {
        setSelectedDocId(null)
      }
      fetchProjectsSummary()
    } catch (err) {
      console.error('Failed to load project details:', err)
    } finally {
      setLoadingDocs(false)
    }
  }

  const handleLoginSuccess = (user, token) => {
    setCurrentUser(user)
    setAuthToken(token)
    localStorage.setItem('hla_user', JSON.stringify(user))
    localStorage.setItem('hla_token', token)
    localStorage.setItem('access_token', token)
    axios.defaults.headers.common['Authorization'] = `Bearer ${token}`
    setShowLoginModal(false)
    setActiveProject(null)
    setSelectedDocId(null)
    setActiveView('workspaces')
    fetchProjectsSummary()
  }

  const handleLogout = () => {
    setCurrentUser(null)
    setAuthToken('')
    localStorage.removeItem('hla_user')
    localStorage.removeItem('hla_token')
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    delete axios.defaults.headers.common['Authorization']
    setActiveProject(null)
    setProjectDocs([])
    setSelectedDocId(null)
    setActiveView('workspaces')
    setShowLoginModal(true)
  }

  const handleUploadSuccess = (newDocId) => {
    if (activeProject?.id) {
      fetchProjectDetails(activeProject.id).then(() => {
        setSelectedDocId(newDocId)
        setProjectStudioTab('workbench')
        showToast('Document uploaded successfully')
      })
    }
  }

  const handleDeleteDocument = async (e, docId, docName) => {
    e.stopPropagation()
    if (!window.confirm(`Are you sure you want to delete '${docName}'?`)) return
    try {
      await axios.delete(`/api/documents/${docId}`)
      if (activeProject?.id) {
        await fetchProjectDetails(activeProject.id)
      }
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to delete document.')
    }
  }

  const handleGoHome = () => {
    setActiveProject(null)
    setActiveView('workspaces')
    setSelectedDocId(null)
    setShowRulesModal(false)
    setShowIntrospectModal(false)
    setShowRoleInfoModal(false)
    setShowUserMgmt(false)
    fetchProjectsSummary()
    window.scrollTo({ top: 0, behavior: 'smooth' })
  }

  const userRole = currentUser?.role?.toLowerCase() || 'viewer'
  const activeDoc = projectDocs.find((d) => d.id === selectedDocId) || projectDocs[0] || null

  const cmdItems = [
    { label: 'Go to Architecture Workbench', k: 'G W', action: () => { setActiveView('project-studio'); setProjectStudioTab('workbench'); } },
    { label: 'Go to Ingest Documents & Files', k: 'G I', action: () => { setActiveView('project-studio'); setProjectStudioTab('ingest'); } },
    { label: 'Go to Source Connectors & Vault', k: 'G C', action: () => { setActiveView('project-studio'); setProjectStudioTab('connectors'); } },
    { label: 'Go to Target DB Studio', k: 'G D', action: () => { setActiveView('project-studio'); setProjectStudioTab('targetdb'); } },
    { label: 'Go to Control Scheduler', k: 'G S', action: () => { setActiveView('project-studio'); setProjectStudioTab('scheduler'); } },
    { label: 'Switch to All Workspaces', k: 'G A', action: () => handleGoHome() },
    { label: 'Open Rules Catalog (R1–R11)', k: 'R C', action: () => setShowRulesModal(true) },
    { label: 'Open Live DB Introspector', k: 'D B', action: () => setShowIntrospectModal(true) },
    ...(userRole === 'admin' ? [{ label: 'Open User Management', k: 'U M', action: () => setShowUserMgmt(true) }] : []),
    { label: 'Log Out of HLA Studio', k: 'L O', action: handleLogout },
    { label: 'Refresh workspace', k: 'R', action: doRefresh },
  ]
  const filteredCmdItems = cmdItems.filter(it => !cmdkQuery || it.label.toLowerCase().includes(cmdkQuery.toLowerCase()))

  // Enforce authentication: if no authenticated user or token, render only the Login screen
  if (!currentUser || !authToken) {
    return (
      <LoginModal
        isOpen={true}
        onLoginSuccess={handleLoginSuccess}
        onClose={null}
        currentRole={null}
      />
    )
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg)', color: 'var(--text)', display: 'flex', flexDirection: 'column', width: '100%', overflowX: 'hidden' }}>
      {/* ===== Header Top ===== */}
      <div className="header-top">
        <div className="logo" onClick={handleGoHome}>
          HLA<span className="dot">.</span>studio
        </div>
        <div className="search-wrap">
          <select className="search-scope">
            <option>All workspaces</option>
            <option>Rules</option>
            <option>Tables</option>
          </select>
          <input
            className="search-input"
            placeholder="Search rules, tables, or documents…"
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                showToast(`Search query: ${e.target.value}`)
              }
            }}
          />
          <button className="search-btn" onClick={() => showToast('Search triggered')}>
            ⌕
          </button>
        </div>
        <div className="head-item" onClick={() => setShowRoleInfoModal(true)} title="View Account & RBAC Permissions Matrix" style={{ cursor: 'pointer' }}>
          <span className="top">👤 {currentUser?.username || 'Guest'}</span>
          <span className="bot">Role: <strong style={{ color: userRole === 'admin' ? '#f59e0b' : userRole === 'architect' ? '#63cab7' : '#94a3b8' }}>{userRole.toUpperCase()}</strong></span>
        </div>
        {userRole === 'admin' && (
          <div className="head-item" onClick={() => setShowUserMgmt(true)} title="Admin: Manage Users & Permissions" style={{ cursor: 'pointer' }}>
            <span className="top">👑 Admin Console</span>
            <span className="bot">Users &amp; Permissions</span>
          </div>
        )}
        <div className="head-item" onClick={handleLogout} title="Sign out of current account" style={{ cursor: 'pointer' }}>
          <span className="top" style={{ color: '#f87171' }}>Sign Out</span>
          <span className="bot">Log Out 🚪</span>
        </div>
        <button className="head-item cmdk-trigger" onClick={() => setCmdkOpen(true)}>
          <span className="top">Quick jump</span>
          <span className="bot">⌘K</span>
        </button>
      </div>

      {/* ===== Sub Nav ===== */}
      <div className="header-sub">
        <button className="sub-item hamburger" onClick={handleGoHome}>
          ☰ All Workspaces
        </button>
        <button
          className={`sub-item ${activeView === 'project-studio' ? 'active' : ''}`}
          onClick={() => {
            if (!activeProject && projectsList.length > 0) {
              setActiveProject(projectsList[0])
            }
            setActiveView('project-studio')
          }}
        >
          Project Studio
        </button>
        <button className="sub-item" onClick={() => setShowRulesModal(true)}>
          Rules Engine
        </button>
        <button className="sub-item" onClick={() => setShowIntrospectModal(true)}>
          DB Introspector
        </button>
        {userRole === 'admin' && (
          <button className="sub-item" onClick={() => setShowUserMgmt(true)}>
            👥 User Management
          </button>
        )}
      </div>

      {/* ===== Breadcrumb Strip ===== */}
      <div className="crumb-strip">
        <div className="path">
          <a onClick={handleGoHome}>Home</a>
          {activeProject ? (
            <>
              <span className="sep">›</span>
              <a onClick={() => setActiveView('project-studio')}>{activeProject.name}</a>
              <span className="sep">›</span>
              <span>{activeDoc?.original_name || activeDoc?.filename || 'HLA Architecture Specification'}</span>
            </>
          ) : (
            <>
              <span className="sep">›</span>
              <span>All Workspaces</span>
            </>
          )}
        </div>
        <div>
          <span className="badge">Multi-DB Engine · Live</span>
        </div>
      </div>

      {/* ===== Shell Layout ===== */}
      <div className="shell">
        {/* Left Sidebar */}
        <div className="sidebar">
          <div className="side-h">Workspace</div>
          <div className="side-search">
            <span className="ic">⌕</span>
            <input
              id="sideSearch"
              placeholder="Filter items…"
              value={sideSearch}
              onChange={(e) => setSideSearch(e.target.value)}
            />
          </div>

          <div className="ws-box">
            <span>{activeProject ? `${activeProject.name} (active)` : 'All Workspaces (Home)'}</span>
            {activeProject && (
              <span style={{ color: '#999', cursor: 'pointer' }} onClick={handleGoHome} title="Return to Home">✕</span>
            )}
          </div>

          <div className="side-label">Workspace &amp; Design</div>
          {(!sideSearch || 'project folders'.includes(sideSearch.toLowerCase())) && (
            <button
              className={`nav-item ${activeView === 'workspaces' ? 'active' : ''}`}
              onClick={handleGoHome}
            >
              <span>Project Folders</span>
              <span className="count">{projectsList.length}</span>
            </button>
          )}
          {(!sideSearch || 'project studio'.includes(sideSearch.toLowerCase())) && (
            <button
              className={`nav-item ${activeView === 'project-studio' ? 'active' : ''}`}
              onClick={() => {
                if (!activeProject && projectsList.length > 0) {
                  setActiveProject(projectsList[0])
                }
                setActiveView('project-studio')
              }}
            >
              <span>Project Studio</span>
            </button>
          )}

          <div className="side-label">Engines &amp; Introspection</div>
          {(!sideSearch || 'rules engine'.includes(sideSearch.toLowerCase())) && (
            <button className="nav-item" onClick={() => setShowRulesModal(true)}>
              <span>Rules Engine (R1–R11)</span>
              <span className="count">Catalog</span>
            </button>
          )}
          {(!sideSearch || 'live db introspector'.includes(sideSearch.toLowerCase())) && (
            <button className="nav-item" onClick={() => setShowIntrospectModal(true)}>
              <span>Live DB Introspector</span>
              <span className="count" style={{ color: 'var(--good)' }}>Live</span>
            </button>
          )}

          <div className="side-label">Governance &amp; Access</div>
          {userRole === 'admin' ? (
            (!sideSearch || 'user management'.includes(sideSearch.toLowerCase())) && (
              <button className="nav-item" onClick={() => setShowUserMgmt(true)}>
                <span>User Management</span>
                <span className="count">Admin</span>
              </button>
            )
          ) : (
            <button className="nav-item" onClick={() => setShowRoleInfoModal(true)}>
              <span>RBAC Permissions</span>
              <span className="count">{userRole.toUpperCase()}</span>
            </button>
          )}
        </div>

        {/* Main Canvas */}
        <div className="main">
          {/* Workspaces Explorer View */}
          {activeView === 'workspaces' && (
            <ProjectExplorer
              projects={projectsList}
              onSelectProject={(proj) => {
                setActiveProject(proj)
                setActiveView('project-studio')
              }}
              onRefreshProjects={fetchProjectsSummary}
              currentUser={currentUser}
            />
          )}

          {/* Project Studio View */}
          {activeView === 'project-studio' && (
            <>
              {/* Workspace Header Card */}
              <div className="ws-header">
                <div className="ws-header-top">
                  <div className="ws-title-row">
                    <h1>{activeProject?.name || 'HI'}</h1>
                    <span className="badge">Active workspace</span>
                  </div>
                  <div className="btn-row">
                    <button className="btn-ghost" onClick={handleGoHome}>
                      ← Back to workspaces
                    </button>
                    <button
                      className={`btn-ghost ${refreshing ? 'spinning' : ''}`}
                      id="refreshBtn"
                      onClick={doRefresh}
                      disabled={refreshing}
                    >
                      <span className="ic">⟳</span> Refresh
                    </button>
                  </div>
                </div>
                <div className="ws-desc">
                  {activeProject?.description || 'Isolated architecture workspace for ETL data ingestion, reconciliation balancing, and client solution design.'}
                </div>

                <div className="tab-row">
                  <button
                    className={`tab ${projectStudioTab === 'workbench' ? 'active' : ''}`}
                    onClick={() => setProjectStudioTab('workbench')}
                  >
                    Architecture Workbench ({projectDocs.length})
                  </button>
                  <button
                    className={`tab ${projectStudioTab === 'ingest' ? 'active' : ''}`}
                    onClick={() => setProjectStudioTab('ingest')}
                  >
                    Ingest Documents &amp; Files
                  </button>
                  <button
                    className={`tab ${projectStudioTab === 'connectors' ? 'active' : ''}`}
                    onClick={() => setProjectStudioTab('connectors')}
                  >
                    Source Connectors &amp; Vault ({activeProject?.connection_count || 0})
                  </button>
                  <button
                    className={`tab ${projectStudioTab === 'targetdb' ? 'active' : ''}`}
                    onClick={() => setProjectStudioTab('targetdb')}
                  >
                    Target DB Studio
                  </button>
                  <button
                    className={`tab ${projectStudioTab === 'scheduler' ? 'active' : ''}`}
                    onClick={() => setProjectStudioTab('scheduler')}
                  >
                    Control Scheduler
                  </button>
                </div>
              </div>

              {/* Panel 1: Architecture Workbench */}
              {projectStudioTab === 'workbench' && (
                <HlaStudioWorkbench
                  activeProject={activeProject}
                  projectDocs={projectDocs}
                  selectedDocId={selectedDocId}
                  onSelectDocId={setSelectedDocId}
                  onRefreshDocs={() => activeProject?.id && fetchProjectDetails(activeProject.id)}
                  currentUser={currentUser}
                  onNavigateTab={(t) => setProjectStudioTab(t)}
                  showToast={showToast}
                />
              )}

              {/* Panel 2: Ingest */}
              {projectStudioTab === 'ingest' && (
                <div className="panel active">
                  <FileUpload
                    projectId={activeProject?.id}
                    onUploadSuccess={handleUploadSuccess}
                  />
                </div>
              )}

              {/* Panel 3: Connectors */}
              {projectStudioTab === 'connectors' && (
                <div className="panel active">
                  <SourceDBManager
                    projectId={activeProject?.id}
                    currentUser={currentUser}
                    onClose={() => setProjectStudioTab('workbench')}
                    onSaved={() => {
                      if (activeProject?.id) fetchProjectDetails(activeProject.id)
                    }}
                  />
                </div>
              )}

              {/* Panel 4: Target DB */}
              {projectStudioTab === 'targetdb' && (
                <div className="panel active">
                  <TargetDBStudio
                    projectId={activeProject?.id}
                    documentId={selectedDocId}
                    projectDocs={projectDocs}
                    currentUser={currentUser}
                    onRefreshProject={() => activeProject?.id && fetchProjectDetails(activeProject.id)}
                  />
                </div>
              )}

              {/* Panel 5: Scheduler */}
              {projectStudioTab === 'scheduler' && (
                <div className="panel active">
                  <ControlScheduler
                    projectId={activeProject?.id}
                    projectDocs={projectDocs}
                    currentUser={currentUser}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>

      {/* ===== Command Palette (⌘K) Overlay ===== */}
      <div
        className={`cmdk-overlay ${cmdkOpen ? 'open' : ''}`}
        onClick={(e) => {
          if (e.target === e.currentTarget) setCmdkOpen(false)
        }}
      >
        <div className="cmdk">
          <input
            id="cmdkInput"
            placeholder="Jump to a tab, rule, or table…"
            value={cmdkQuery}
            onChange={(e) => setCmdkQuery(e.target.value)}
            autoFocus
          />
          <div className="cmdk-list">
            {filteredCmdItems.map((it, idx) => (
              <div
                key={idx}
                className={`cmdk-item ${idx === 0 ? 'sel' : ''}`}
                onClick={() => {
                  it.action()
                  setCmdkOpen(false)
                }}
              >
                <span>{it.label}</span>
                <span className="k">{it.k}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ===== Global Toast Banner ===== */}
      <div className={`toast ${toastMsg ? 'show' : ''}`} id="toast">
        {toastMsg}
      </div>

      {/* ── Login / Switch Role Modal ── */}
      <LoginModal
        isOpen={showLoginModal || !currentUser}
        onLoginSuccess={handleLoginSuccess}
        onClose={currentUser ? () => setShowLoginModal(false) : null}
        currentRole={currentUser?.role}
      />

      {/* ── Admin User Management Modal ── */}
      {userRole === 'admin' && (
        <UserManagementModal
          isOpen={showUserMgmt}
          onClose={() => setShowUserMgmt(false)}
          currentUser={currentUser}
        />
      )}

      {/* ── Interactive Rules Catalog & Simulator Modal ── */}
      <RulesModal
        isOpen={showRulesModal}
        onClose={() => setShowRulesModal(false)}
        documentId={selectedDocId}
      />

      {/* ── Universal Live DB Introspector Modal ── */}
      <GlobalIntrospectModal
        isOpen={showIntrospectModal}
        onClose={() => setShowIntrospectModal(false)}
      />

      {/* ── Role Permissions Matrix Modal ── */}
      <RoleInfoModal
        isOpen={showRoleInfoModal}
        onClose={() => setShowRoleInfoModal(false)}
        currentUser={currentUser}
        onOpenUserMgmt={() => setShowUserMgmt(true)}
      />
    </div>
  )
}

export default App
