import React, { useState, useEffect } from 'react'
import axios from 'axios'

export default function RolesTab({ onNotify, onOpenMatrixForRole }) {
  const [roles, setRoles] = useState([])
  const [permissions, setPermissions] = useState([])
  const [loading, setLoading] = useState(false)

  // Create role modal state
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [newRoleName, setNewRoleName] = useState('')
  const [newRoleCode, setNewRoleCode] = useState('')
  const [newRoleDesc, setNewRoleDesc] = useState('')
  const [newRolePerms, setNewRolePerms] = useState([])
  const [creating, setCreating] = useState(false)

  // Clone role modal state
  const [cloningRole, setCloningRole] = useState(null)
  const [cloneName, setCloneName] = useState('')
  const [cloneCode, setCloneCode] = useState('')
  const [cloneDesc, setCloneDesc] = useState('')
  const [cloning, setCloning] = useState(false)

  // View role members modal state
  const [inspectRole, setInspectRole] = useState(null)
  const [roleUsers, setRoleUsers] = useState([])
  const [loadingUsers, setLoadingUsers] = useState(false)

  useEffect(() => {
    fetchRoles()
    fetchPermissions()
  }, [])

  const fetchRoles = async () => {
    setLoading(true)
    try {
      const res = await axios.get('/api/governance/roles')
      setRoles(res.data || [])
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to load roles catalog.', 'error')
    } finally {
      setLoading(false)
    }
  }

  const fetchPermissions = async () => {
    try {
      const res = await axios.get('/api/governance/permissions')
      setPermissions(res.data || [])
    } catch (err) {
      console.error('Failed to load permissions catalog:', err)
    }
  }

  const handleCreateRole = async (e) => {
    e.preventDefault()
    if (!newRoleName.trim() || !newRoleCode.trim()) return

    setCreating(true)
    try {
      const res = await axios.post('/api/governance/roles', {
        name: newRoleName.trim(),
        code: newRoleCode.trim(),
        description: newRoleDesc.trim(),
        permissions: newRolePerms
      })
      onNotify(res.data?.message || 'Custom role created successfully.', 'success')
      setShowCreateModal(false)
      setNewRoleName('')
      setNewRoleCode('')
      setNewRoleDesc('')
      setNewRolePerms([])
      fetchRoles()
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to create role.', 'error')
    } finally {
      setCreating(false)
    }
  }

  const handleCloneRole = async (e) => {
    e.preventDefault()
    if (!cloningRole) return

    setCloning(true)
    try {
      const res = await axios.post(`/api/governance/roles/${cloningRole.id}/clone`, {
        name: cloneName.trim(),
        code: cloneCode.trim(),
        description: cloneDesc.trim()
      })
      onNotify(res.data?.message || 'Role cloned successfully.', 'success')
      setCloningRole(null)
      fetchRoles()
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to clone role.', 'error')
    } finally {
      setCloning(false)
    }
  }

  const handleDeleteRole = async (role) => {
    if (role.is_system) {
      onNotify('System roles are immutable and cannot be removed.', 'error')
      return
    }

    if (!window.confirm(`Are you sure you want to delete custom role '${role.name}'?`)) {
      return
    }

    try {
      const res = await axios.delete(`/api/governance/roles/${role.id}`)
      onNotify(res.data?.message || 'Custom role deleted.', 'success')
      fetchRoles()
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to delete role.', 'error')
    }
  }

  const handleInspectUsers = async (role) => {
    setInspectRole(role)
    setLoadingUsers(true)
    try {
      const res = await axios.get(`/api/governance/roles/${role.id}/users`)
      setRoleUsers(res.data?.users || [])
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to load role members.', 'error')
    } finally {
      setLoadingUsers(false)
    }
  }

  const openCloneModal = (role) => {
    setCloningRole(role)
    setCloneName(`Copy of ${role.name}`)
    setCloneCode(`${role.code}_copy`)
    setCloneDesc(`Cloned from ${role.name}`)
  }

  const togglePermissionSelection = (code) => {
    setNewRolePerms((prev) =>
      prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]
    )
  }

  return (
    <div className="gov-tab-content">
      {/* Top Controls */}
      <div className="gov-controls-bar">
        <div>
          <h3 style={{ margin: 0, fontSize: '1rem', color: '#f8fafc' }}>
            Enterprise Security Roles Catalog
          </h3>
          <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.8rem', color: '#94a3b8' }}>
            Define custom roles, configure granular domain privileges, and inspect member allocations.
          </p>
        </div>

        <button className="btn-gov-primary" onClick={() => setShowCreateModal(true)}>
          <span>➕</span> Create Custom Role
        </button>
      </div>

      {/* Roles Cards Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
        {loading ? (
          <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '3rem', color: '#64748b' }}>
            Loading roles directory…
          </div>
        ) : (
          roles.map((r) => (
            <div
              key={r.id}
              className="sec-card"
              style={{
                borderColor: r.is_system ? 'rgba(168, 85, 247, 0.3)' : 'rgba(45, 212, 191, 0.25)',
                background: 'rgba(30, 41, 59, 0.5)'
              }}
            >
              <div className="sec-card-header">
                <div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span style={{ fontSize: '1rem', fontWeight: 700, color: '#f8fafc' }}>
                      {r.name}
                    </span>
                    {r.is_system ? (
                      <span className="gov-badge badge-role-admin" style={{ fontSize: '0.68rem' }}>System</span>
                    ) : (
                      <span className="gov-badge badge-role-custom" style={{ fontSize: '0.68rem' }}>Custom</span>
                    )}
                  </div>
                  <span style={{ fontSize: '0.74rem', color: '#64748b', fontFamily: 'monospace' }}>
                    code: {r.code}
                  </span>
                </div>

                <span className={`sec-status-pill ${r.is_active ? 'status-connected' : 'status-not_configured'}`}>
                  {r.is_active ? 'ACTIVE' : 'INACTIVE'}
                </span>
              </div>

              <p style={{ fontSize: '0.82rem', color: '#cbd5e1', margin: 0, minHeight: '2.5rem' }}>
                {r.description || 'No description provided.'}
              </p>

              <div className="sec-card-body" style={{ borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '0.6rem' }}>
                <div className="sec-stat-row">
                  <span className="sec-stat-label">Assigned Permissions:</span>
                  <span className="sec-stat-val">{r.permission_count || 0} / 25</span>
                </div>
                <div className="sec-stat-row">
                  <span className="sec-stat-label">Assigned Users:</span>
                  <span className="sec-stat-val" style={{ color: '#38bdf8' }}>{r.user_count || 0} members</span>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem', borderTop: '1px solid rgba(255,255,255,0.06)', paddingTop: '0.75rem' }}>
                <button
                  className="btn-gov-secondary"
                  style={{ flex: 1, justifyContent: 'center' }}
                  onClick={() => handleInspectUsers(r)}
                  title="View assigned user members"
                >
                  👥 Users
                </button>

                <button
                  className="btn-gov-secondary"
                  style={{ flex: 1, justifyContent: 'center' }}
                  onClick={() => openCloneModal(r)}
                  title="Clone this role into a custom role"
                >
                  📑 Clone
                </button>

                {!r.is_system && (
                  <button
                    className="btn-gov-secondary"
                    style={{ color: '#f87171', borderColor: 'rgba(239, 68, 68, 0.3)' }}
                    onClick={() => handleDeleteRole(r)}
                    title="Delete custom role"
                  >
                    🗑️
                  </button>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* ── Create Custom Role Modal ─────────────────────────────────── */}
      {showCreateModal && (
        <div className="gov-submodal-backdrop" onClick={() => setShowCreateModal(false)}>
          <div className="gov-submodal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 640 }}>
            <div className="gov-submodal-header">
              <div className="gov-submodal-title">
                <span>➕</span> Create New Custom Security Role
              </div>
              <button className="btn-gov-secondary" onClick={() => setShowCreateModal(false)}>✕</button>
            </div>
            <form onSubmit={handleCreateRole}>
              <div className="gov-submodal-body">
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>Role Name *</label>
                    <input
                      type="text"
                      className="gov-search-input"
                      style={{ width: '100%' }}
                      placeholder="e.g. Compliance Officer"
                      value={newRoleName}
                      onChange={(e) => {
                        setNewRoleName(e.target.value)
                        if (!newRoleCode) {
                          setNewRoleCode(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))
                        }
                      }}
                      required
                    />
                  </div>
                  <div>
                    <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>Unique Code Slug *</label>
                    <input
                      type="text"
                      className="gov-search-input"
                      style={{ width: '100%' }}
                      placeholder="e.g. compliance_officer"
                      value={newRoleCode}
                      onChange={(e) => setNewRoleCode(e.target.value.toLowerCase())}
                      required
                    />
                  </div>
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>Role Description</label>
                  <textarea
                    className="gov-search-input"
                    style={{ width: '100%', minHeight: 60, resize: 'vertical' }}
                    placeholder="Describe role responsibilities and governance boundaries…"
                    value={newRoleDesc}
                    onChange={(e) => setNewRoleDesc(e.target.value)}
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.5rem' }}>
                    Assign Initial Permissions ({newRolePerms.length} selected)
                  </label>
                  <div style={{ maxHeight: 220, overflowY: 'auto', border: '1px solid rgba(255,255,255,0.08)', borderRadius: 8, padding: '0.5rem' }}>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(240px, 1fr))', gap: '0.4rem' }}>
                      {permissions.map((p) => {
                        const checked = newRolePerms.includes(p.code)
                        return (
                          <label
                            key={p.id}
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '0.5rem',
                              padding: '0.35rem 0.5rem',
                              background: checked ? 'rgba(56, 189, 248, 0.1)' : 'transparent',
                              borderRadius: 6,
                              fontSize: '0.78rem',
                              cursor: 'pointer',
                              color: checked ? '#38bdf8' : '#cbd5e1'
                            }}
                          >
                            <input
                              type="checkbox"
                              checked={checked}
                              onChange={() => togglePermissionSelection(p.code)}
                            />
                            <span>{p.code}</span>
                          </label>
                        )
                      })}
                    </div>
                  </div>
                </div>
              </div>

              <div style={{ padding: '1rem 1.5rem', background: 'rgba(30, 41, 59, 0.5)', display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                <button type="button" className="btn-gov-secondary" onClick={() => setShowCreateModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-gov-primary" disabled={creating}>
                  {creating ? 'Creating…' : '🚀 Create Role'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── Clone Role Modal ────────────────────────────────────────── */}
      {cloningRole && (
        <div className="gov-submodal-backdrop" onClick={() => setCloningRole(null)}>
          <div className="gov-submodal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 500 }}>
            <div className="gov-submodal-header">
              <div className="gov-submodal-title">
                <span>📑</span> Clone Role: {cloningRole.name}
              </div>
              <button className="btn-gov-secondary" onClick={() => setCloningRole(null)}>✕</button>
            </div>
            <form onSubmit={handleCloneRole}>
              <div className="gov-submodal-body">
                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>New Role Name *</label>
                  <input
                    type="text"
                    className="gov-search-input"
                    style={{ width: '100%' }}
                    value={cloneName}
                    onChange={(e) => setCloneName(e.target.value)}
                    required
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>New Role Code Slug *</label>
                  <input
                    type="text"
                    className="gov-search-input"
                    style={{ width: '100%' }}
                    value={cloneCode}
                    onChange={(e) => setCloneCode(e.target.value.toLowerCase())}
                    required
                  />
                </div>

                <div>
                  <label style={{ display: 'block', fontSize: '0.8rem', color: '#94a3b8', marginBottom: '0.35rem' }}>Description</label>
                  <textarea
                    className="gov-search-input"
                    style={{ width: '100%', minHeight: 60 }}
                    value={cloneDesc}
                    onChange={(e) => setCloneDesc(e.target.value)}
                  />
                </div>
              </div>

              <div style={{ padding: '1rem 1.5rem', background: 'rgba(30, 41, 59, 0.5)', display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                <button type="button" className="btn-gov-secondary" onClick={() => setCloningRole(null)}>
                  Cancel
                </button>
                <button type="submit" className="btn-gov-primary" disabled={cloning}>
                  {cloning ? 'Cloning…' : '📑 Complete Clone'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ── View Role Members Modal ─────────────────────────────────── */}
      {inspectRole && (
        <div className="gov-submodal-backdrop" onClick={() => setInspectRole(null)}>
          <div className="gov-submodal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 580 }}>
            <div className="gov-submodal-header">
              <div className="gov-submodal-title">
                <span>👥</span> Members Assigned to '{inspectRole.name}' ({roleUsers.length})
              </div>
              <button className="btn-gov-secondary" onClick={() => setInspectRole(null)}>✕</button>
            </div>
            <div className="gov-submodal-body">
              {loadingUsers ? (
                <p style={{ textAlign: 'center', color: '#64748b' }}>Loading members…</p>
              ) : roleUsers.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '2rem', color: '#64748b' }}>
                  No active users currently assigned to this role.
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  {roleUsers.map((u) => (
                    <div
                      key={u.id}
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '0.65rem 0.85rem',
                        background: 'rgba(255,255,255,0.03)',
                        borderRadius: 8,
                        border: '1px solid rgba(255,255,255,0.06)'
                      }}
                    >
                      <div>
                        <strong style={{ color: '#f8fafc' }}>{u.username}</strong>
                        <span style={{ display: 'block', fontSize: '0.75rem', color: '#94a3b8' }}>{u.email || 'No email registered'}</span>
                      </div>
                      <span className={`gov-badge ${u.status === 'ACTIVE' ? 'badge-active' : 'badge-disabled'}`}>
                        {u.status}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div style={{ padding: '0.75rem 1.5rem', background: 'rgba(30, 41, 59, 0.5)', display: 'flex', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
              <button className="btn-gov-secondary" onClick={() => setInspectRole(null)}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
