import React, { useState, useEffect } from 'react'
import axios from 'axios'

export default function EffectivePermissionsModal({ user, onClose, onNotify }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (user) {
      fetchPermissions()
    }
  }, [user])

  if (!user) return null

  const fetchPermissions = async () => {
    setLoading(true)
    try {
      const res = await axios.get(`/api/governance/users/${user.id}/permissions`)
      setData(res.data)
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to resolve effective permissions.', 'error')
    } finally {
      setLoading(false)
    }
  }

  const perms = data?.effective_permissions || []

  return (
    <div className="gov-submodal-backdrop" onClick={onClose}>
      <div className="gov-submodal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 640 }}>
        <div className="gov-submodal-header">
          <div className="gov-submodal-title">
            <span>🛡️</span> Effective Permissions: {user.username}
          </div>
          <button className="btn-gov-secondary" onClick={onClose}>✕</button>
        </div>

        <div className="gov-submodal-body">
          {loading ? (
            <p style={{ textAlign: 'center', color: '#64748b' }}>Resolving permissions…</p>
          ) : (
            <>
              <div style={{ background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: 8, border: '1px solid rgba(255,255,255,0.06)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <span style={{ fontSize: '0.74rem', color: '#94a3b8', textTransform: 'uppercase' }}>Assigned Role</span>
                    <h4 style={{ margin: '0.2rem 0', color: '#f8fafc' }}>{data?.role_name || user.role}</h4>
                  </div>
                  <span className="gov-badge badge-active" style={{ fontSize: '0.8rem' }}>
                    {perms.length} Permissions Granted
                  </span>
                </div>
                {data?.role_description && (
                  <p style={{ margin: '0.5rem 0 0 0', fontSize: '0.8rem', color: '#cbd5e1' }}>
                    {data.role_description}
                  </p>
                )}
              </div>

              <div>
                <h5 style={{ margin: '0 0 0.5rem 0', color: '#94a3b8', fontSize: '0.78rem', textTransform: 'uppercase' }}>
                  Granted Permission Tokens
                </h5>
                <div className="perm-pill-grid">
                  {perms.length === 0 ? (
                    <span style={{ color: '#64748b', fontSize: '0.8rem' }}>No permissions currently assigned.</span>
                  ) : (
                    perms.map((p) => (
                      <span key={p} className="perm-tag-pill">
                        ✓ {p}
                      </span>
                    ))
                  )}
                </div>
              </div>
            </>
          )}
        </div>

        <div style={{ padding: '0.75rem 1.5rem', background: 'rgba(30, 41, 59, 0.5)', display: 'flex', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          <button className="btn-gov-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}
