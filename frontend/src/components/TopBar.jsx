import React from 'react'
import './TopBar.css'

export default function TopBar({
  activeView,
  onSelectView,
  activeProject,
  onResetProject,
  onGoHome,
  activeDoc,
  onResetDoc,
  currentUser,
  onOpenCreateProject,
  onOpenRulesModal,
  onOpenIntrospectModal,
  theme = 'dark',
  onToggleTheme,
  onOpenAiAssistant,
}) {
  const userRole = currentUser?.role?.toLowerCase() || 'viewer'
  const canCreate = ['admin', 'architect'].includes(userRole)

  return (
    <header className="app-topbar">
      {/* ── Left: Clean Breadcrumb Navigation ── */}
      <div className="topbar-left">
        <nav className="topbar-breadcrumbs" aria-label="Breadcrumb">
          <button
            className={`breadcrumb-node ${activeView === 'workspaces' && !activeProject ? 'current' : ''}`}
            onClick={() => {
              if (onGoHome) {
                onGoHome()
              } else {
                onResetProject()
                onSelectView('workspaces')
              }
            }}
          >
            <svg className="breadcrumb-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>
              <polyline points="9 22 9 12 15 12 15 22"/>
            </svg>
            <span>Workspaces</span>
          </button>

          {activeProject && (
            <>
              <span className="breadcrumb-separator">/</span>
              <button
                className={`breadcrumb-node ${!activeDoc ? 'current' : ''}`}
                onClick={() => {
                  if (onResetDoc) onResetDoc()
                  onSelectView('project-studio')
                }}
              >
                <svg className="breadcrumb-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
                </svg>
                <span>{activeProject.name}</span>
              </button>
            </>
          )}

          {activeDoc && (
            <>
              <span className="breadcrumb-separator">/</span>
              <span className="breadcrumb-node current active-doc-pill">
                <svg className="breadcrumb-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                  <polyline points="14 2 14 8 20 8"/>
                  <line x1="16" y1="13" x2="8" y2="13"/>
                  <line x1="16" y1="17" x2="8" y2="17"/>
                  <polyline points="10 9 9 9 8 9"/>
                </svg>
                <span>{activeDoc.original_name || activeDoc.filename}</span>
              </span>
            </>
          )}
        </nav>
      </div>

      {/* ── Right: Unified Actions & Theme Switcher ── */}
      <div className="topbar-right">
        {/* Universal Multi-DB Health Indicator */}
        <div className="topbar-status-beacon" title="Connected to Universal Multi-DB Engine (Snowflake, MSSQL, MySQL, Oracle, PostgreSQL)">
          <span className="topbar-beacon-dot" />
          <span>Multi-DB Engine</span>
        </div>

        {/* Introspect DB Trigger */}
        <button
          className="topbar-btn"
          onClick={onOpenIntrospectModal}
          title="Universal Live DB Introspector"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <ellipse cx="12" cy="5" rx="9" ry="3"/>
            <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/>
            <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/>
          </svg>
          <span>Introspect DB</span>
        </button>

        {/* Rules Catalog Trigger */}
        <button
          className="topbar-btn"
          onClick={onOpenRulesModal}
          title="R1–R10 Filter & R11 Balance Rules"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"/>
          </svg>
          <span>Rules (R1–R11)</span>
        </button>

        {/* HLA AI Assistant Trigger */}
        <button
          className="topbar-btn"
          onClick={onOpenAiAssistant}
          title="Open HLA AI Assistant (Local Ollama Copilot)"
          style={{ background: 'rgba(56, 189, 248, 0.1)', borderColor: 'rgba(56, 189, 248, 0.3)', color: '#38bdf8' }}
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
            <circle cx="12" cy="12" r="4" />
          </svg>
          <span>Ask AI</span>
        </button>

        {/* Theme Switcher Toggle */}
        <button
          className="topbar-btn-icon"
          onClick={onToggleTheme}
          title={theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode'}
          aria-label="Toggle Theme"
        >
          {theme === 'dark' ? (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="5"/>
              <line x1="12" y1="1" x2="12" y2="3"/>
              <line x1="12" y1="21" x2="12" y2="23"/>
              <line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/>
              <line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/>
              <line x1="1" y1="12" x2="3" y2="12"/>
              <line x1="21" y1="12" x2="23" y2="12"/>
              <line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/>
              <line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>
            </svg>
          ) : (
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
            </svg>
          )}
        </button>

        {/* New project action (if permitted) */}
        {canCreate && (
          <button
            className="topbar-btn-primary"
            onClick={onOpenCreateProject}
            title="Create a new architecture project folder"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/>
              <line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            <span>New Project</span>
          </button>
        )}
      </div>
    </header>
  )
}
