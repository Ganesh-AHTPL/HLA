import React, { useState, useEffect } from 'react'
import axios from 'axios'

export default function PermissionsTab({ onNotify }) {
  const [roles, setRoles] = useState([])
  const [categories, setCategories] = useState({})
  const [matrix, setMatrix] = useState({})
  const [initialMatrix, setInitialMatrix] = useState({})
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [selectedRole, setSelectedRole] = useState('all')

  useEffect(() => {
    fetchMatrix()
  }, [])

  const fetchMatrix = async () => {
    setLoading(true)
    try {
      const res = await axios.get('/api/governance/permissions/matrix')
      setRoles(res.data?.roles || [])
      setCategories(res.data?.categories || {})
      const m = res.data?.matrix || {}
      setMatrix(JSON.parse(JSON.stringify(m)))
      setInitialMatrix(JSON.parse(JSON.stringify(m)))
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to load permission matrix.', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleToggle = (roleCode, permCode) => {
    // Admin self-protection
    if (roleCode === 'admin' && (permCode === 'user.manage' || permCode === 'permission.manage')) {
      onNotify("Protection rule: 'user.manage' and 'permission.manage' cannot be revoked from Administrator.", 'error')
      return
    }

    setMatrix((prev) => {
      const currentPerms = prev[roleCode] || []
      const exists = currentPerms.includes(permCode)
      const updatedPerms = exists
        ? currentPerms.filter((p) => p !== permCode)
        : [...currentPerms, permCode]

      return {
        ...prev,
        [roleCode]: updatedPerms
      }
    })
  }

  const handleSaveRolePermissions = async (roleCode) => {
    setSaving(true)
    try {
      const perms = matrix[roleCode] || []
      const res = await axios.put('/api/governance/permissions/matrix', {
        role_code: roleCode,
        permissions: perms
      })
      onNotify(res.data?.message || `Permissions for role '${roleCode}' saved.`, 'success')
      setInitialMatrix((prev) => ({
        ...prev,
        [roleCode]: [...perms]
      }))
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to update permissions.', 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveAll = async () => {
    setSaving(true)
    try {
      for (const role of roles) {
        const perms = matrix[role.code] || []
        await axios.put('/api/governance/permissions/matrix', {
          role_code: role.code,
          permissions: perms
        })
      }
      onNotify('Full role-permission matrix synchronized successfully.', 'success')
      setInitialMatrix(JSON.parse(JSON.stringify(matrix)))
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to save matrix updates.', 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = () => {
    setMatrix(JSON.parse(JSON.stringify(initialMatrix)))
  }

  const hasChanges = JSON.stringify(matrix) !== JSON.stringify(initialMatrix)

  const displayedRoles = selectedRole === 'all'
    ? roles
    : roles.filter((r) => r.code === selectedRole)

  return (
    <div className="gov-tab-content">
      {/* Header controls */}
      <div className="gov-controls-bar">
        <div>
          <h3 style={{ margin: 0, fontSize: '1rem', color: '#f8fafc' }}>
            Interactive Role-Permission Matrix
          </h3>
          <p style={{ margin: '0.25rem 0 0 0', fontSize: '0.8rem', color: '#94a3b8' }}>
            Configure granular authorizations across 25 standard enterprise permissions and 8 domains.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <select
            className="gov-select"
            value={selectedRole}
            onChange={(e) => setSelectedRole(e.target.value)}
          >
            <option value="all">View: All Roles</option>
            {roles.map((r) => (
              <option key={r.id} value={r.code}>
                Filter to: {r.name}
              </option>
            ))}
          </select>

          {hasChanges && (
            <button className="btn-gov-secondary" onClick={handleReset} disabled={saving}>
              Discard Changes
            </button>
          )}

          <button
            className="btn-gov-primary"
            onClick={handleSaveAll}
            disabled={!hasChanges || saving}
            id="btn-save-permission-matrix"
          >
            {saving ? 'Saving Matrix…' : '💾 Save Changes'}
          </button>
        </div>
      </div>

      {/* Matrix Table */}
      <div className="gov-table-wrap">
        <table className="gov-table matrix-table">
          <thead>
            <tr>
              <th style={{ minWidth: 260 }}>Domain &amp; Permission</th>
              <th style={{ minWidth: 280 }}>Description</th>
              {displayedRoles.map((r) => (
                <th key={r.id} className="role-col">
                  <div>{r.name}</div>
                  <span style={{ fontSize: '0.68rem', color: '#64748b', fontWeight: 500, fontFamily: 'monospace' }}>
                    {r.code}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan={displayedRoles.length + 2} style={{ textAlign: 'center', padding: '3rem', color: '#64748b' }}>
                  Loading permission matrix…
                </td>
              </tr>
            ) : (
              Object.entries(categories).map(([domain, perms]) => (
                <React.Fragment key={domain}>
                  {/* Domain Header Row */}
                  <tr>
                    <td
                      colSpan={displayedRoles.length + 2}
                      className="domain-section-header"
                    >
                      DOMAIN: {domain.toUpperCase()} ({perms.length} permissions)
                    </td>
                  </tr>

                  {/* Permissions in Domain */}
                  {perms.map((p) => (
                    <tr key={p.code}>
                      <td>
                        <strong style={{ color: '#f8fafc', display: 'block', fontSize: '0.82rem' }}>
                          {p.name}
                        </strong>
                        <span style={{ fontSize: '0.72rem', color: '#38bdf8', fontFamily: 'monospace' }}>
                          {p.code}
                        </span>
                      </td>

                      <td style={{ color: '#94a3b8', fontSize: '0.78rem' }}>
                        {p.description}
                      </td>

                      {displayedRoles.map((r) => {
                        const isGranted = (matrix[r.code] || []).includes(p.code)
                        const isLockedAdmin = r.code === 'admin' && (p.code === 'user.manage' || p.code === 'permission.manage')

                        return (
                          <td key={r.code} className="cell-check">
                            <input
                              type="checkbox"
                              className="matrix-checkbox"
                              checked={isGranted}
                              disabled={isLockedAdmin}
                              onChange={() => handleToggle(r.code, p.code)}
                              title={isLockedAdmin ? 'Protected: cannot remove from Administrator' : `Toggle ${p.code} for ${r.name}`}
                            />
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </React.Fragment>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
