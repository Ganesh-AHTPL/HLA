import React, { useState, useEffect, useRef } from 'react'
import axios from 'axios'

export default function UsersTab({
  currentUser,
  onOpenActivity,
  onOpenPermissions,
  refreshTrigger,
  onNotify
}) {
  const [users, setUsers] = useState([])
  const [roles, setRoles] = useState([])
  const [loading, setLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [roleFilter, setRoleFilter] = useState('all')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(15)
  const [total, setTotal] = useState(0)

  // Provision modal state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newRole, setNewRole] = useState('architect')
  const [newStatus, setNewStatus] = useState('ACTIVE')
  const [creating, setCreating] = useState(false)

  // Edit user state
  const [editingUser, setEditingUser] = useState(null)
  const [editRole, setEditRole] = useState('')
  const [editEmail, setEditEmail] = useState('')
  const [editStatus, setEditStatus] = useState('')
  const [updating, setUpdating] = useState(false)

  // Active three-dot menu dropdown ID
  const [activeMenuId, setActiveMenuId] = useState(null)
  const menuRef = useRef(null)

  useEffect(() => {
    fetchUsers()
  }, [searchQuery, statusFilter, roleFilter, page, pageSize, refreshTrigger])

  useEffect(() => {
    fetchRoles()
  }, [])

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) {
        setActiveMenuId(null)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const fetchRoles = async () => {
    try {
      const res = await axios.get('/api/governance/roles')
      setRoles(res.data || [])
    } catch (err) {
      console.error('Failed to load roles:', err)
    }
  }

  const fetchUsers = async () => {
    setLoading(true)
    try {
      const params = {
        page,
        page_size: pageSize,
        q: searchQuery.trim(),
        status: statusFilter,
        role: roleFilter
      }
      const res = await axios.get('/api/governance/users', { params })
      setUsers(res.data?.users || [])
      setTotal(res.data?.total || 0)
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to load user directory.', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateUser = async (e) => {
    e.preventDefault()
    if (!newUsername.trim() || !newPassword.trim()) return

    setCreating(true)
    try {
      const res = await axios.post('/api/governance/users', {
        username: newUsername.trim(),
        password: newPassword.trim(),
        email: newEmail.trim() || undefined,
        role: newRole,
        status: newStatus
      })
      onNotify(res.data?.message || 'User account provisioned successfully.', 'success')
      setShowCreateModal(false)
      setNewUsername('')
      setNewPassword('')
      setNewEmail('')
      setNewRole('architect')
      setNewStatus('ACTIVE')
      fetchUsers()
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to create user.', 'error')
    } finally {
      setCreating(false)
    }
  }

  const handleSaveEdit = async (e) => {
    e.preventDefault()
    if (!editingUser) return

    setUpdating(true)
    try {
      const res = await axios.put(`/api/governance/users/${editingUser.id}`, {
        role: editRole,
        email: editEmail.trim() || null,
        status: editStatus
      })
      onNotify(res.data?.message || 'User updated successfully.', 'success')
      setEditingUser(null)
      fetchUsers()
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to update user.', 'error')
    } finally {
      setUpdating(false)
    }
  }

  const handleToggleStatus = async (user, targetStatus) => {
    setActiveMenuId(null)
    const isSelf = currentUser && currentUser.id === user.id
    if (isSelf && (targetStatus === 'LOCKED' || targetStatus === 'DISABLED')) {
      onNotify('Action blocked: You cannot lock or disable your own active Administrator account.', 'error')
      return
    }

    try {
      const res = await axios.post(`/api/governance/users/${user.id}/status`, { status: targetStatus })
      onNotify(res.data?.message || `User status changed to ${targetStatus}.`, 'success')
      fetchUsers()
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to update user status.', 'error')
    }
  }

  const handleForceLogout = async (user) => {
    setActiveMenuId(null)
    if (!window.confirm(`Invalidate all active sessions for user '${user.username}'? They will be required to log in again.`)) {
      return
    }

    try {
      const res = await axios.post(`/api/governance/users/${user.id}/force-logout`)
      onNotify(res.data?.message || 'User sessions invalidated.', 'success')
      fetchUsers()
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to force logout user.', 'error')
    }
  }

  const handleResetPassword = async (user) => {
    setActiveMenuId(null)
    const newPwd = window.prompt(`Enter new temporary password for user '${user.username}':`)
    if (!newPwd || !newPwd.trim()) return

    if (newPwd.trim().length < 4) {
      onNotify('Password must be at least 4 characters long.', 'error')
      return
    }

    try {
      await axios.put(`/api/governance/users/${user.id}`, { password: newPwd.trim() })
      onNotify(`Password reset successfully for '${user.username}'. Prior sessions invalidated.`, 'success')
      fetchUsers()
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to reset password.', 'error')
    }
  }

  const handleDeleteUser = async (user) => {
    setActiveMenuId(null)
    const isSelf = currentUser && currentUser.id === user.id
    if (isSelf) {
      onNotify('Action blocked: You cannot delete your own active Administrator account.', 'error')
      return
    }

    if (!window.confirm(`Permanently delete account '${user.username}'? This operation cannot be undone.`)) {
      return
    }

    try {
      await axios.delete(`/api/governance/users/${user.id}`)
      onNotify(`User '${user.username}' has been removed.`, 'success')
      fetchUsers()
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to delete user.', 'error')
    }
  }

  const openEditModal = (user) => {
    setActiveMenuId(null)
    setEditingUser(user)
    setEditRole(user.role || 'viewer')
    setEditEmail(user.email || '')
    setEditStatus(user.status || 'ACTIVE')
  }

  const getStatusBadge = (status) => {
    switch ((status || 'ACTIVE').toUpperCase()) {
      case 'ACTIVE':
        return <span className="gov-badge badge-active">● Active</span>
      case 'PENDING':
        return <span className="gov-badge badge-pending">⏳ Pending</span>
      case 'LOCKED':
        return <span className="gov-badge badge-locked">🔒 Locked</span>
      case 'DISABLED':
        return <span className="gov-badge badge-disabled">⛔ Disabled</span>
      default:
        return <span className="gov-badge badge-disabled">{status}</span>
    }
  }

  const getRoleBadge = (roleCode) => {
    switch ((roleCode || 'viewer').toLowerCase()) {
      case 'admin':
        return <span className="gov-badge badge-role-admin">👑 Admin</span>
      case 'architect':
        return <span className="gov-badge badge-role-architect">🛠️ Architect</span>
      case 'viewer':
        return <span className="gov-badge badge-role-viewer">👁️ Viewer</span>
      default:
        return <span className="gov-badge badge-role-custom">🛡️ {roleCode}</span>
    }
  }

  return (
    <div className="gov-tab-content">
      {/* Top Filter & Control Bar */}
      <div className="gov-controls-bar">
        <div className="gov-filters-group">
          <input
            type="text"
            className="gov-search-input"
            placeholder="🔍 Search users by username or email…"
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value)
              setPage(1)
            }}
          />

          <select
            className="gov-select"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value)
              setPage(1)
            }}
          >
            <option value="ALL">Status: All</option>
            <option value="ACTIVE">Status: Active</option>
            <option value="PENDING">Status: Pending</option>
            <option value="LOCKED">Status: Locked</option>
            <option value="DISABLED">Status: Disabled</option>
          </select>

          <select
            className="gov-select"
            value={roleFilter}
            onChange={(e) => {
              setRoleFilter(e.target.value)
              setPage(1)
            }}
          >
            <option value="all">Role: All Roles</option>
            {roles.map((r) => (
              <option key={r.id} value={r.code}>
                {r.name} ({r.code})
              </option>
            ))}
          </select>
        </div>

        <button
          className="btn-gov-primary"
          onClick={() => setShowCreateModal(true)}
          id="btn-provision-new-user"
        >
          <span>➕</span> Provision User
        </button>
      </div>

      {/* Users Table */}
      <div className="gov-table-wrap">
        <table className="gov-table">
          <thead>
            <tr>
              <th>User</th>
              <th>Role</th>
              <th>Status</th>
              <th>Email</th>
              <th>Last Login</th>
              <th>Last Activity</th>
              <th>MFA</th>
              <th>Created</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan="9" style={{ textAlign: 'center', padding: '2.5rem', color: '#64748b' }}>
                  Loading enterprise directory…
                </td>
              </tr>
            ) : users.length === 0 ? (
              <tr>
                <td colSpan="9" style={{ textAlign: 'center', padding: '2.5rem', color: '#64748b' }}>
                  No users found matching query criteria.
                </td>
              </tr>
            ) : (
              users.map((u) => {
                const isSelf = currentUser && currentUser.id === u.id
                const isMenuOpen = activeMenuId === u.id

                return (
                  <tr key={u.id}>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
                        <span style={{ fontWeight: 600, color: '#f8fafc' }}>{u.username}</span>
                        {isSelf && (
                          <span style={{ fontSize: '0.68rem', color: '#38bdf8', background: 'rgba(56, 189, 248, 0.12)', padding: '0.1rem 0.4rem', borderRadius: '4px', fontWeight: 600 }}>
                            You
                          </span>
                        )}
                      </div>
                    </td>
                    <td>{getRoleBadge(u.role)}</td>
                    <td>{getStatusBadge(u.status)}</td>
                    <td style={{ color: '#94a3b8' }}>{u.email || '—'}</td>
                    <td style={{ color: '#94a3b8', fontSize: '0.78rem' }}>
                      {u.last_login_at ? new Date(u.last_login_at).toLocaleString() : 'Never'}
                    </td>
                    <td style={{ color: '#64748b', fontSize: '0.78rem' }}>
                      {u.last_activity_at ? new Date(u.last_activity_at).toLocaleString() : '—'}
                    </td>
                    <td>
                      {u.mfa_enabled ? (
                        <span style={{ color: '#34d399', fontSize: '0.76rem', fontWeight: 600 }}>✓ Enrolled</span>
                      ) : (
                        <span style={{ color: '#64748b', fontSize: '0.76rem' }}>Off</span>
                      )}
                    </td>
                    <td style={{ color: '#64748b', fontSize: '0.78rem' }}>
                      {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div className="action-dropdown-wrap" ref={isMenuOpen ? menuRef : null}>
                        <button
                          className="btn-three-dots"
                          title="Actions menu"
                          onClick={() => setActiveMenuId(isMenuOpen ? null : u.id)}
                        >
                          ⋮
                        </button>

                        {isMenuOpen && (
                          <div className="action-menu">
                            <button className="action-menu-item" onClick={() => openEditModal(u)}>
                              <span>✏️</span> Edit Profile &amp; Role
                            </button>

                            <button className="action-menu-item" onClick={() => handleResetPassword(u)}>
                              <span>🔑</span> Reset Password
                            </button>

                            <button className="action-menu-item" onClick={() => onOpenPermissions(u)}>
                              <span>🛡️</span> View Permissions
                            </button>

                            <button className="action-menu-item" onClick={() => onOpenActivity(u)}>
                              <span>📜</span> View Audit Activity
                            </button>

                            <div className="menu-divider" />

                            <button
                              className="action-menu-item"
                              onClick={() => handleForceLogout(u)}
                            >
                              <span>🚪</span> Force Logout
                            </button>

                            {u.status === 'LOCKED' ? (
                              <button className="action-menu-item" onClick={() => handleToggleStatus(u, 'ACTIVE')}>
                                <span>🔓</span> Unlock Account
                              </button>
                            ) : (
                              <button
                                className="action-menu-item"
                                disabled={isSelf}
                                onClick={() => handleToggleStatus(u, 'LOCKED')}
                                title={isSelf ? 'Cannot lock your own active administrator account' : ''}
                              >
                                <span>🔒</span> Lock Account
                              </button>
                            )}

                            {u.status === 'DISABLED' ? (
                              <button className="action-menu-item" onClick={() => handleToggleStatus(u, 'ACTIVE')}>
                                <span>✅</span> Enable Account
                              </button>
                            ) : (
                              <button
                                className="action-menu-item"
                                disabled={isSelf}
                                onClick={() => handleToggleStatus(u, 'DISABLED')}
                                title={isSelf ? 'Cannot disable your own active administrator account' : ''}
                              >
                                <span>⛔</span> Disable Account
                              </button>
                            )}

                            <div className="menu-divider" />

                            <button
                              className="action-menu-item danger"
                              disabled={isSelf}
                              onClick={() => handleDeleteUser(u)}
                              title={isSelf ? 'Cannot delete your own active administrator account' : ''}
                            >
                              <span>🗑️</span> Remove User
                            </button>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8rem', color: '#94a3b8' }}>
        <div>
          Showing {users.length} of {total} total user accounts
        </div>
        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <button
            className="btn-gov-secondary"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            ← Previous
          </button>
          <span>Page {page} of {Math.max(1, Math.ceil(total / pageSize))}</span>
          <button
            className="btn-gov-secondary"
            disabled={page * pageSize >= total}
            onClick={() => setPage((p) => p + 1)}
          >
            Next →
          </button>
        </div>
      </div>

      {/* ── Provision User Modal ────────────────────────────────────── */}
      {showCreateModal && (
        <div className="gov-submodal-backdrop" onClick={() => setShowCreateModal(false)}>
          <div className="gov-submodal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 540 }}>
            <div className="gov-submodal-header">
              <div className="gov-submodal-title">
                <span>➕</span> Provision New Enterprise User
              </div>
              <button className="btn-gov-secondary" onClick={() => setShowCreateModal(false)}>✕</button>
            </div>
            <form onSubmit={handleCreateUser}>
              <div className="gov-submodal-body">
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>Username *</label>
                  <input
                    type="text"
                    className="gov-search-input"
                    style={{ width: '100%' }}
                    placeholder="e.g. john_doe"
                    value={newUsername}
                    onChange={(e) => setNewUsername(e.target.value)}
                    required
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>Initial Password *</label>
                  <input
                    type="password"
                    className="gov-search-input"
                    style={{ width: '100%' }}
                    placeholder="Strong initial password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>Corporate Email (Optional)</label>
                  <input
                    type="email"
                    className="gov-search-input"
                    style={{ width: '100%' }}
                    placeholder="john@enterprise.com"
                    value={newEmail}
                    onChange={(e) => setNewEmail(e.target.value)}
                  />
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>Assigned Role *</label>
                    <select
                      className="gov-select"
                      style={{ width: '100%' }}
                      value={newRole}
                      onChange={(e) => setNewRole(e.target.value)}
                    >
                      {roles.map((r) => (
                        <option key={r.id} value={r.code}>
                          {r.name} ({r.code})
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>Initial Status *</label>
                    <select
                      className="gov-select"
                      style={{ width: '100%' }}
                      value={newStatus}
                      onChange={(e) => setNewStatus(e.target.value)}
                    >
                      <option value="ACTIVE">ACTIVE</option>
                      <option value="PENDING">PENDING</option>
                      <option value="LOCKED">LOCKED</option>
                      <option value="DISABLED">DISABLED</option>
                    </select>
                  </div>
                </div>
              </div>

              <div style={{ padding: '1rem 1.5rem', background: 'rgba(30, 41, 59, 0.5)', display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                <button type="button" className="btn-gov-secondary" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-gov-primary" disabled={creating}>
                  {creating ? 'Provisioning…' : '🚀 Create User Account'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Edit Profile & Role Modal ───────────────────────────────── */}
      {editingUser && (
        <div className="gov-submodal-backdrop" onClick={() => setEditingUser(null)}>
          <div className="gov-submodal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 520 }}>
            <div className="gov-submodal-header">
              <div className="gov-submodal-title">
                <span>✏️</span> Edit User: {editingUser.username}
              </div>
              <button className="btn-gov-secondary" onClick={() => setEditingUser(null)}>✕</button>
            </div>
            <form onSubmit={handleSaveEdit}>
              <div className="gov-submodal-body">
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>Corporate Email</label>
                  <input
                    type="email"
                    className="gov-search-input"
                    style={{ width: '100%' }}
                    value={editEmail}
                    onChange={(e) => setEditEmail(e.target.value)}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>Assigned Role</label>
                  <select
                    className="gov-select"
                    style={{ width: '100%' }}
                    value={editRole}
                    onChange={(e) => setEditRole(e.target.value)}
                  >
                    {roles.map((r) => (
                      <option key={r.id} value={r.code}>
                        {r.name} ({r.code})
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>Account Status</label>
                  <select
                    className="gov-select"
                    style={{ width: '100%' }}
                    value={editStatus}
                    onChange={(e) => setEditStatus(e.target.value)}
                  >
                    <option value="ACTIVE">ACTIVE</option>
                    <option value="PENDING">PENDING</option>
                    <option value="LOCKED">LOCKED</option>
                    <option value="DISABLED">DISABLED</option>
                  </select>
                </div>
              </div>

              <div style={{ padding: '1rem 1.5rem', background: 'rgba(30, 41, 59, 0.5)', display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                <button type="button" className="btn-gov-secondary" onClick={() => setEditingUser(null)}>
                  Cancel
                </button>
                <button type="submit" className="btn-gov-primary" disabled={updating}>
                  {updating ? 'Saving…' : '💾 Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
