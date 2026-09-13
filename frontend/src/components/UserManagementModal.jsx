import { useState, useEffect } from 'react'
import axios from 'axios'
import './UserManagementModal.css'

export default function UserManagementModal({ isOpen, onClose, currentUser }) {
  const [users, setUsers] = useState([])
  const [loading, setLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [updatingId, setUpdatingId] = useState(null)
  const [errorMsg, setErrorMsg] = useState('')
  const [successMsg, setSuccessMsg] = useState('')

  // New user form state
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState('architect')

  useEffect(() => {
    if (isOpen) {
      fetchUsers()
      setErrorMsg('')
      setSuccessMsg('')
    }
  }, [isOpen])

  if (!isOpen) return null

  const fetchUsers = async () => {
    setLoading(true)
    try {
      const res = await axios.get('/api/auth/users')
      setUsers(res.data || [])
    } catch (err) {
      setErrorMsg(err.response?.data?.error || 'Failed to load user directory.')
    } finally {
      setLoading(false)
    }
  }

  const handleCreateUser = async (e) => {
    e.preventDefault()
    if (!username.trim() || !password.trim()) return

    setSubmitting(true)
    setErrorMsg('')
    setSuccessMsg('')

    try {
      const res = await axios.post('/api/auth/users', {
        username: username.trim(),
        password: password.trim(),
        email: email.trim() || undefined,
        role,
      })
      setSuccessMsg(res.data?.message || `User '${username}' provisioned successfully with role ${role.toUpperCase()}.`)
      setUsername('')
      setPassword('')
      setEmail('')
      setRole('architect')
      await fetchUsers()
    } catch (err) {
      setErrorMsg(err.response?.data?.error || 'Failed to provision user account.')
    } finally {
      setSubmitting(false)
    }
  }

  const handleUpdateRole = async (userId, targetUsername, newRole) => {
    setUpdatingId(userId)
    setErrorMsg('')
    setSuccessMsg('')

    try {
      const res = await axios.put(`/api/auth/users/${userId}`, {
        role: newRole,
      })
      setSuccessMsg(res.data?.message || `Permissions for '${targetUsername}' updated to ${newRole.toUpperCase()}.`)
      await fetchUsers()
    } catch (err) {
      setErrorMsg(err.response?.data?.error || 'Failed to update user permissions.')
    } finally {
      setUpdatingId(null)
    }
  }

  const handleResetPassword = async (user) => {
    const newPwd = window.prompt(`Enter new password for user '${user.username}':`)
    if (!newPwd || !newPwd.trim()) return

    if (newPwd.trim().length < 4) {
      alert('Password must be at least 4 characters long.')
      return
    }

    setUpdatingId(user.id)
    setErrorMsg('')
    setSuccessMsg('')

    try {
      await axios.put(`/api/auth/users/${user.id}`, {
        password: newPwd.trim(),
      })
      setSuccessMsg(`Password for user '${user.username}' was reset successfully.`)
    } catch (err) {
      setErrorMsg(err.response?.data?.error || 'Failed to reset password.')
    } finally {
      setUpdatingId(null)
    }
  }

  const handleDeleteUser = async (user) => {
    if (!window.confirm(`Are you sure you want to permanently delete user account '${user.username}'?`)) {
      return
    }

    try {
      await axios.delete(`/api/auth/users/${user.id}`)
      setSuccessMsg(`User account '${user.username}' has been removed.`)
      await fetchUsers()
    } catch (err) {
      alert(err.response?.data?.error || 'Failed to delete user.')
    }
  }

  return (
    <div className="user-mgmt-backdrop" onClick={onClose}>
      <div className="user-mgmt-modal" onClick={(e) => e.stopPropagation()} id="user-mgmt-modal">
        {/* Header */}
        <div className="user-mgmt-header">
          <div>
            <h2>
              <span>👥</span> User Administration &amp; Permissions
            </h2>
            <p>
              As Administrator, create user accounts, assign roles, and configure system permissions.
            </p>
          </div>
          <button className="btn-close-mgmt" onClick={onClose} title="Close">
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="user-mgmt-body">
          {errorMsg && (
            <div style={{
              background: 'rgba(239, 68, 68, 0.15)',
              border: '1px solid rgba(239, 68, 68, 0.35)',
              color: '#fca5a5',
              padding: '0.75rem 1rem',
              borderRadius: '10px',
              fontSize: '0.85rem'
            }}>
              ⚠️ {errorMsg}
            </div>
          )}

          {successMsg && (
            <div style={{
              background: 'rgba(99, 202, 183, 0.15)',
              border: '1px solid rgba(99, 202, 183, 0.35)',
              color: '#63cab7',
              padding: '0.75rem 1rem',
              borderRadius: '10px',
              fontSize: '0.85rem'
            }}>
              ✓ {successMsg}
            </div>
          )}

          {/* Provision New User Form */}
          <div className="mgmt-form-card">
            <div className="mgmt-form-title">
              <span>➕</span> Create New User &amp; Assign Permissions
            </div>
            <form onSubmit={handleCreateUser}>
              <div className="mgmt-form-grid">
                <div className="mgmt-field">
                  <label>Username *</label>
                  <input
                    type="text"
                    className="mgmt-input"
                    placeholder="e.g. john_doe"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    required
                    id="input-new-username"
                  />
                </div>

                <div className="mgmt-field">
                  <label>Password *</label>
                  <input
                    type="password"
                    className="mgmt-input"
                    placeholder="Initial password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                    id="input-new-password"
                  />
                </div>

                <div className="mgmt-field">
                  <label>Email (Optional)</label>
                  <input
                    type="email"
                    className="mgmt-input"
                    placeholder="user@enterprise.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    id="input-new-email"
                  />
                </div>

                <div className="mgmt-field">
                  <label>Assigned Role &amp; Permission Level *</label>
                  <select
                    className="mgmt-input"
                    value={role}
                    onChange={(e) => setRole(e.target.value)}
                    id="select-new-role"
                  >
                    <option value="architect">🛠️ Solution Architect (Design, Upload, &amp; Pipelines)</option>
                    <option value="viewer">👁️ Stakeholder / Viewer (Read-Only Workspaces)</option>
                    <option value="admin">👑 System Administrator (Full Access &amp; User Provisioning)</option>
                  </select>
                </div>
              </div>

              <button
                type="submit"
                className="btn-create-user"
                disabled={submitting || !username.trim() || !password.trim()}
                id="btn-submit-create-user"
              >
                {submitting ? 'Creating Account…' : '🚀 Create User & Grant Permissions'}
              </button>
            </form>
          </div>

          {/* Existing Accounts Table with Inline Role/Permission Management */}
          <div className="mgmt-table-card">
            <div className="mgmt-table-title">
              <span>Active User Directory ({users.length} accounts)</span>
              <button
                onClick={fetchUsers}
                style={{
                  background: 'transparent',
                  border: 'none',
                  color: '#63cab7',
                  fontSize: '0.8rem',
                  cursor: 'pointer',
                  fontWeight: 600
                }}
              >
                🔄 Refresh Directory
              </button>
            </div>

            <div className="mgmt-table-wrap">
              <table className="mgmt-table">
                <thead>
                  <tr>
                    <th>Username</th>
                    <th>Permissions / Role</th>
                    <th>Email</th>
                    <th>Created</th>
                    <th style={{ textAlign: 'right' }}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan="5" style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
                        Loading user directory…
                      </td>
                    </tr>
                  ) : users.length === 0 ? (
                    <tr>
                      <td colSpan="5" style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
                        No users registered.
                      </td>
                    </tr>
                  ) : (
                    users.map((u) => {
                      const isSelf = currentUser && currentUser.id === u.id
                      const uRole = u.role?.toLowerCase() || 'viewer'
                      const isBusy = updatingId === u.id

                      return (
                        <tr key={u.id}>
                          <td>
                            <strong style={{ color: '#ffffff' }}>{u.username}</strong>
                            {isSelf && (
                              <span style={{ marginLeft: '0.4rem', fontSize: '0.72rem', color: '#63cab7', fontWeight: 600 }}>
                                (Current Session)
                              </span>
                            )}
                          </td>
                          <td>
                            {isSelf ? (
                              <span className="role-pill admin" title="Cannot change your own role to prevent lockout">
                                👑 Admin (Self)
                              </span>
                            ) : (
                              <select
                                className="mgmt-role-select"
                                value={uRole}
                                disabled={isBusy}
                                onChange={(e) => handleUpdateRole(u.id, u.username, e.target.value)}
                                title="Change role permissions for this user"
                              >
                                <option value="architect">🛠️ Solution Architect</option>
                                <option value="viewer">👁️ Viewer (Read-Only)</option>
                                <option value="admin">👑 Administrator</option>
                              </select>
                            )}
                          </td>
                          <td style={{ color: '#94a3b8' }}>{u.email || '—'}</td>
                          <td style={{ color: '#64748b', fontSize: '0.78rem' }}>
                            {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                          </td>
                          <td style={{ textAlign: 'right' }}>
                            <button
                              type="button"
                              className="btn-action-pwd"
                              onClick={() => handleResetPassword(u)}
                              disabled={isBusy}
                              title={`Reset password for ${u.username}`}
                            >
                              🔑 Reset Pwd
                            </button>
                            <button
                              type="button"
                              className="btn-delete-user"
                              onClick={() => handleDeleteUser(u)}
                              disabled={isSelf || isBusy}
                              title={isSelf ? 'Cannot delete your own active Admin account' : `Delete account ${u.username}`}
                            >
                              🗑️ Remove
                            </button>
                          </td>
                        </tr>
                      )
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Role Permissions Legend */}
          <div className="mgmt-permissions-guide">
            <div className="mgmt-permissions-guide-title">
              Role Permissions Matrix &amp; Scope
            </div>
            <div className="mgmt-perm-grid">
              <div className="mgmt-perm-card admin">
                <div className="mgmt-perm-card-title">👑 Administrator</div>
                <div className="mgmt-perm-card-desc">
                  Full control: Create users, grant &amp; revoke permissions, reset passwords, delete projects &amp; documents, configure database connectors, and trigger pipeline execution.
                </div>
              </div>
              <div className="mgmt-perm-card architect">
                <div className="mgmt-perm-card-title">🛠️ Solution Architect</div>
                <div className="mgmt-perm-card-desc">
                  Design &amp; ETL: Upload HLA specifications, view Target DB Studio, configure connectors, run rule evaluations, and design architecture flows.
                </div>
              </div>
              <div className="mgmt-perm-card viewer">
                <div className="mgmt-perm-card-title">👁️ Stakeholder / Viewer</div>
                <div className="mgmt-perm-card-desc">
                  Read-only: Browse workspaces, view document schemas, inspect R1–R15 rules catalog, and examine data lineage. No edit or upload rights.
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
