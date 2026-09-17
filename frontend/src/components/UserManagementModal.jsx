import React, { useState, useEffect } from 'react'
import './UserManagementModal.css'
import './governance/governance.css'

import UsersTab from './governance/UsersTab'
import RolesTab from './governance/RolesTab'
import PermissionsTab from './governance/PermissionsTab'
import AuditTab from './governance/AuditTab'
import SecurityCenterTab from './governance/SecurityCenterTab'
import UserActivityModal from './governance/UserActivityModal'
import EffectivePermissionsModal from './governance/EffectivePermissionsModal'
import AuditEventModal from './governance/AuditEventModal'

export default function UserManagementModal({ isOpen, onClose, currentUser }) {
  const [activeTab, setActiveTab] = useState('users') // 'users', 'roles', 'permissions', 'audit', 'security'
  const [notification, setNotification] = useState(null)
  const [refreshTrigger, setRefreshTrigger] = useState(0)

  // Submodals
  const [activityUser, setActivityUser] = useState(null)
  const [permissionsUser, setPermissionsUser] = useState(null)
  const [selectedAuditEvent, setSelectedAuditEvent] = useState(null)

  useEffect(() => {
    if (isOpen) {
      setNotification(null)
    }
  }, [isOpen])

  if (!isOpen) return null

  const notify = (msg, type = 'info') => {
    setNotification({ msg, type })
    setTimeout(() => {
      setNotification((curr) => (curr?.msg === msg ? null : curr))
    }, 4500)
  }

  const handleRefreshAll = () => {
    setRefreshTrigger((t) => t + 1)
  }

  return (
    <div className="user-mgmt-backdrop" onClick={onClose}>
      <div
        className="user-mgmt-modal"
        onClick={(e) => e.stopPropagation()}
        id="user-mgmt-modal"
        style={{
          width: '95vw',
          maxWidth: '1280px',
          height: '92vh',
          display: 'flex',
          flexDirection: 'column',
          borderRadius: '16px',
          overflow: 'hidden'
        }}
      >
        {/* Modal Header */}
        <div className="user-mgmt-header" style={{ padding: '1.15rem 1.75rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <span style={{ fontSize: '1.4rem' }}>🏛️</span>
              <h2 style={{ margin: 0, fontSize: '1.25rem', color: '#f8fafc' }}>
                Enterprise Governance &amp; Administration
              </h2>
              <span className="gov-badge badge-role-admin" style={{ fontSize: '0.7rem' }}>
                Single Authority RBAC
              </span>
            </div>
            <p style={{ margin: '0.35rem 0 0 0', fontSize: '0.82rem', color: '#94a3b8' }}>
              Manage users, configure custom security roles, enforce fine-grained permissions, and inspect immutable audit logs.
            </p>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <button className="btn-close-mgmt" onClick={onClose} title="Close">
              ✕
            </button>
          </div>
        </div>

        {/* Global Notification Banner */}
        {notification && (
          <div
            style={{
              padding: '0.75rem 1.5rem',
              fontSize: '0.84rem',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background:
                notification.type === 'error'
                  ? 'rgba(239, 68, 68, 0.2)'
                  : notification.type === 'success'
                  ? 'rgba(16, 185, 129, 0.2)'
                  : 'rgba(56, 189, 248, 0.2)',
              borderBottom: '1px solid rgba(255,255,255,0.08)',
              color:
                notification.type === 'error'
                  ? '#fca5a5'
                  : notification.type === 'success'
                  ? '#6ee7b7'
                  : '#7dd3fc'
            }}
          >
            <span>
              {notification.type === 'error' ? '⚠️ ' : notification.type === 'success' ? '✓ ' : 'ℹ️ '}
              {notification.msg}
            </span>
            <button
              onClick={() => setNotification(null)}
              style={{ background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer' }}
            >
              ✕
            </button>
          </div>
        )}

        {/* Governance Tabs Nav */}
        <div className="gov-tabs-nav">
          <button
            className={`gov-tab-btn ${activeTab === 'users' ? 'active' : ''}`}
            onClick={() => setActiveTab('users')}
            id="tab-btn-users"
          >
            <span>👥</span> Users Directory
          </button>

          <button
            className={`gov-tab-btn ${activeTab === 'roles' ? 'active' : ''}`}
            onClick={() => setActiveTab('roles')}
            id="tab-btn-roles"
          >
            <span>🛡️</span> Roles &amp; Scopes
          </button>

          <button
            className={`gov-tab-btn ${activeTab === 'permissions' ? 'active' : ''}`}
            onClick={() => setActiveTab('permissions')}
            id="tab-btn-permissions"
          >
            <span>🔑</span> Permission Matrix
          </button>

          <button
            className={`gov-tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
            onClick={() => setActiveTab('audit')}
            id="tab-btn-audit"
          >
            <span>📜</span> Audit &amp; Activity
          </button>

          <button
            className={`gov-tab-btn ${activeTab === 'security' ? 'active' : ''}`}
            onClick={() => setActiveTab('security')}
            id="tab-btn-security"
          >
            <span>🔒</span> Security Center
          </button>
        </div>

        {/* Tab Body */}
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column' }}>
          {activeTab === 'users' && (
            <UsersTab
              currentUser={currentUser}
              onOpenActivity={(u) => setActivityUser(u)}
              onOpenPermissions={(u) => setPermissionsUser(u)}
              refreshTrigger={refreshTrigger}
              onNotify={notify}
            />
          )}

          {activeTab === 'roles' && (
            <RolesTab
              onNotify={notify}
              onOpenMatrixForRole={() => setActiveTab('permissions')}
            />
          )}

          {activeTab === 'permissions' && (
            <PermissionsTab onNotify={notify} />
          )}

          {activeTab === 'audit' && (
            <AuditTab
              onNotify={notify}
              onOpenDetails={(ev) => setSelectedAuditEvent(ev)}
            />
          )}

          {activeTab === 'security' && (
            <SecurityCenterTab onNotify={notify} />
          )}
        </div>

        {/* Submodals */}
        {activityUser && (
          <UserActivityModal
            user={activityUser}
            onClose={() => setActivityUser(null)}
            onNotify={notify}
          />
        )}

        {permissionsUser && (
          <EffectivePermissionsModal
            user={permissionsUser}
            onClose={() => setPermissionsUser(null)}
            onNotify={notify}
          />
        )}

        {selectedAuditEvent && (
          <AuditEventModal
            event={selectedAuditEvent}
            onClose={() => setSelectedAuditEvent(null)}
          />
        )}
      </div>
    </div>
  )
}
