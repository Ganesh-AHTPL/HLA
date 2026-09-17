import React from 'react'
import './Sidebar.css'

export default function Sidebar({
  activeView,
  onSelectView,
  activeProject,
  onResetProject,
  onGoHome,
  projectsCount = 0,
  currentUser,
  onOpenLogin,
  onLogout,
  onOpenRulesModal,
  onOpenIntrospectModal,
  onOpenUserMgmt,
  onOpenRoleInfo,
  onOpenAiAssistant,
}) {
  const userRole = currentUser?.role?.toLowerCase() || 'viewer'
  const isAdmin = userRole === 'admin'

  const handleBrandClick = () => {
    if (onGoHome) {
      onGoHome()
    } else {
      if (onResetProject) onResetProject()
      if (onSelectView) onSelectView('workspaces')
    }
  }

  return (
    <aside className="app-sidebar">
      {/* ── Brand Logo Header ── */}
      <div
        className="sidebar-brand"
        onClick={handleBrandClick}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            handleBrandClick()
          }
        }}
        title="Go to Home / Workspaces"
        aria-label="HLA Studio Home"
      >
        <div className="brand-icon-wrap">
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="12 2 2 7 12 12 22 7 12 2"/>
            <polyline points="2 17 12 22 22 17"/>
            <polyline points="2 12 12 17 22 12"/>
          </svg>
        </div>
        <div className="brand-info">
          <div className="brand-title">
            <span>HLA</span> Studio
            <span className="brand-ver">v3.0</span>
          </div>
          <span className="brand-subtitle">Architecture & ETL Engine</span>
        </div>
      </div>

      {/* ── Active Project Context ── */}
      <div className="sidebar-context-card">
        <div className="context-label">Active Workspace</div>
        {activeProject ? (
          <div className="active-project-pill">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
            <span className="proj-name" title={activeProject.name}>
              {activeProject.name}
            </span>
            <button
              className="btn-switch-context"
              onClick={onResetProject}
              title="Return to all workspaces"
              aria-label="Close workspace"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"/>
                <line x1="6" y1="6" x2="18" y2="18"/>
              </svg>
            </button>
          </div>
        ) : (
          <div className="global-context-pill">
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10"/>
              <line x1="2" y1="12" x2="22" y2="12"/>
              <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
            </svg>
            <span>All Workspaces</span>
          </div>
        )}
      </div>

      {/* ── Navigation Links ── */}
      <nav className="sidebar-nav">
        <div className="nav-group-title">WORKSPACE & DESIGN</div>

        <button
          className={`sidebar-nav-item ${activeView === 'workspaces' ? 'active' : ''}`}
          onClick={() => onSelectView('workspaces')}
        >
          <svg className="nav-item-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
          </svg>
          <span className="nav-item-text">Project Folders</span>
          {projectsCount > 0 && <span className="nav-item-badge">{projectsCount}</span>}
        </button>

        {activeProject && (
          <button
            className={`sidebar-nav-item ${activeView === 'project-studio' ? 'active' : ''}`}
            onClick={() => onSelectView('project-studio')}
          >
            <svg className="nav-item-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="3" width="18" height="18" rx="2" ry="2"/>
              <line x1="3" y1="9" x2="21" y2="9"/>
              <line x1="9" y1="21" x2="9" y2="9"/>
            </svg>
            <span className="nav-item-text">Project Studio</span>
            <span className="nav-item-live-dot" />
          </button>
        )}

        <div className="nav-group-title">ENGINES & INTROSPECTION</div>

        <button
          className="sidebar-nav-item"
          onClick={onOpenRulesModal}
          title="Open R1–R10 Filter Rules & R11 Balance Dataset Catalog"
        >
          <svg className="nav-item-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
          </svg>
          <span className="nav-item-text">Rules Engine (R1–R11)</span>
          <span className="nav-item-hint">Catalog</span>
        </button>

        <button
          className="sidebar-nav-item"
          onClick={onOpenIntrospectModal}
          title="Universal Live Database Schema & Sample Inspector"
        >
          <svg className="nav-item-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <ellipse cx="12" cy="5" rx="9" ry="3"/>
            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
          </svg>
          <span className="nav-item-text">Live DB Introspector</span>
          <span className="nav-item-hint">Live</span>
        </button>

        <div className="nav-group-title">AI & INTELLIGENCE</div>

        <button
          className="sidebar-nav-item"
          onClick={onOpenAiAssistant}
          title="Open HLA AI Assistant (Local Ollama Copilot)"
        >
          <svg className="nav-item-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            <circle cx="12" cy="12" r="4" />
          </svg>
          <span className="nav-item-text">HLA AI Assistant</span>
          <span className="nav-item-hint" style={{ color: '#38bdf8', background: 'rgba(56, 189, 248, 0.15)', borderColor: 'rgba(56, 189, 248, 0.3)' }}>qwen3</span>
        </button>

        <div className="nav-group-title">GOVERNANCE & ACCESS</div>

        {isAdmin ? (
          <button
            className="sidebar-nav-item"
            onClick={onOpenUserMgmt}
            title="Admin account provisioning & role management"
          >
            <svg className="nav-item-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/>
              <circle cx="9" cy="7" r="4"/>
              <path d="M23 21v-2a4 4 0 0 0-3-3.87"/>
              <path d="M16 3.13a4 4 0 0 1 0 7.75"/>
            </svg>
            <span className="nav-item-text">User Management</span>
            <span className="nav-item-role-tag admin">Admin</span>
          </button>
        ) : (
          <button
            className="sidebar-nav-item"
            onClick={onOpenRoleInfo}
            title="View Zero-Trust RBAC permissions matrix"
          >
            <svg className="nav-item-icon" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
            </svg>
            <span className="nav-item-text">RBAC Matrix</span>
            <span className="nav-item-role-tag">{userRole}</span>
          </button>
        )}
      </nav>

      {/* ── User Profile & Session Widget ── */}
      <div className="sidebar-footer">
        {currentUser ? (
          <div className="user-session-card">
            <div className="user-avatar-wrap">
              <span className="user-avatar-text">
                {currentUser.username?.substring(0, 2).toUpperCase()}
              </span>
              <span className={`user-status-dot ${userRole}`} />
            </div>
            <div className="user-details">
              <div className="user-name-row">
                <span className="user-username">{currentUser.username}</span>
                <span className={`role-pill ${userRole}`}>{userRole}</span>
              </div>
              <span className="user-email">{currentUser.email || 'active'}</span>
            </div>
            <button
              className="btn-sidebar-signout"
              onClick={onLogout}
              title="Sign out of current account"
              aria-label="Sign out"
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>
                <polyline points="16 17 21 12 16 7"/>
                <line x1="21" y1="12" x2="9" y2="12"/>
              </svg>
            </button>
          </div>
        ) : (
          <button className="btn-sidebar-login" onClick={onOpenLogin}>
            Sign In
          </button>
        )}
      </div>
    </aside>
  )
}
