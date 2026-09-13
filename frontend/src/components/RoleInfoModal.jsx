import React from 'react'

export default function RoleInfoModal({ isOpen, onClose, currentUser, onOpenUserMgmt }) {
  if (!isOpen) return null

  const userRole = currentUser?.role?.toLowerCase() || 'viewer'
  const isAdmin = userRole === 'admin'

  const matrix = [
    {
      capability: 'User & Account Management (Create/Delete users)',
      admin: true,
      architect: false,
      viewer: false,
    },
    {
      capability: 'Create & Manage Project Workspaces',
      admin: true,
      architect: true,
      viewer: false,
    },
    {
      capability: 'Upload & Parse HLA Control Specifications (.xlsx)',
      admin: true,
      architect: true,
      viewer: false,
    },
    {
      capability: 'Configure Source DB Connections & Credentials',
      admin: true,
      architect: true,
      viewer: false,
    },
    {
      capability: 'Execute Live DB Schema & Table Introspection',
      admin: true,
      architect: true,
      viewer: true,
    },
    {
      capability: 'Inspect R1–R10 Filter & R11 Balance Rules',
      admin: true,
      architect: true,
      viewer: true,
    },
    {
      capability: 'Export Data Model & Architecture Lineage',
      admin: true,
      architect: true,
      viewer: true,
    },
    {
      capability: 'Delete Projects & Documents',
      admin: true,
      architect: false,
      viewer: false,
    },
  ]

  return (
    <div className="rules-modal-overlay" onClick={onClose}>
      <div className="rules-modal-card" style={{ maxWidth: '780px' }} onClick={e => e.stopPropagation()}>
        <div className="rules-modal-header">
          <div className="rules-modal-title-group">
            <div className="rules-badge" style={{ color: '#fb7185', borderColor: 'rgba(244, 63, 94, 0.3)', background: 'rgba(244, 63, 94, 0.1)' }}>
              <span>🛡️</span> ZERO-TRUST ROLE-BASED ACCESS CONTROL
            </div>
            <h2>RBAC Governance & Permissions Matrix</h2>
            <p className="rules-modal-subtitle">
              You are currently authenticated as <strong>{currentUser?.username || 'Guest'}</strong> with role{' '}
              <span className={`role-pill ${userRole}`}>{userRole}</span>.
            </p>
          </div>
          <button className="rules-close-btn" onClick={onClose}>✕</button>
        </div>

        <div className="rules-modal-body">
          <div style={{ background: 'rgba(15, 23, 42, 0.6)', border: '1px solid rgba(255, 255, 255, 0.08)', borderRadius: '12px', overflow: 'hidden' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
              <thead>
                <tr style={{ background: '#090e1a', borderBottom: '1px solid rgba(255, 255, 255, 0.1)' }}>
                  <th style={{ padding: '0.75rem 1rem', textAlign: 'left', color: '#94a3b8' }}>Platform Capability</th>
                  <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', color: '#fb7185' }}>👑 Admin</th>
                  <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', color: '#38bdf8' }}>🛠️ Architect</th>
                  <th style={{ padding: '0.75rem 0.5rem', textAlign: 'center', color: '#94a3b8' }}>👁️ Viewer</th>
                </tr>
              </thead>
              <tbody>
                {matrix.map((row, i) => (
                  <tr key={i} style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
                    <td style={{ padding: '0.65rem 1rem', color: '#f8fafc', fontWeight: 600 }}>{row.capability}</td>
                    <td style={{ padding: '0.65rem 0.5rem', textAlign: 'center', fontSize: '1.1rem' }}>
                      {row.admin ? '✅' : '—'}
                    </td>
                    <td style={{ padding: '0.65rem 0.5rem', textAlign: 'center', fontSize: '1.1rem' }}>
                      {row.architect ? '✅' : '—'}
                    </td>
                    <td style={{ padding: '0.65rem 0.5rem', textAlign: 'center', fontSize: '1.1rem' }}>
                      {row.viewer ? '✅' : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="rules-modal-footer">
          {isAdmin ? (
            <button
              style={{
                background: 'linear-gradient(135deg, #f43f5e 0%, #fb7185 100%)',
                border: 'none',
                color: '#fff',
                padding: '0.5rem 1.25rem',
                borderRadius: '8px',
                fontSize: '0.82rem',
                fontWeight: 700,
                cursor: 'pointer',
              }}
              onClick={() => {
                onClose()
                if (onOpenUserMgmt) onOpenUserMgmt()
              }}
            >
              👥 Open Admin User Management
            </button>
          ) : (
            <span style={{ fontSize: '0.8rem', color: '#64748b' }}>
              Account provisioning is restricted to Administrator.
            </span>
          )}
          <button className="rules-btn-primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
