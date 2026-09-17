import React, { useState, useEffect } from 'react'
import axios from 'axios'

export default function UserActivityModal({ user, onClose, onNotify }) {
  const [activities, setActivities] = useState([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (user) {
      fetchActivity()
    }
  }, [user])

  if (!user) return null

  const fetchActivity = async () => {
    setLoading(true)
    try {
      const res = await axios.get(`/api/governance/users/${user.id}/activity?limit=30`)
      setActivities(res.data?.activity || [])
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to load user activity trail.', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="gov-submodal-backdrop" onClick={onClose}>
      <div className="gov-submodal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 680 }}>
        <div className="gov-submodal-header">
          <div className="gov-submodal-title">
            <span>📜</span> Activity Trail: {user.username}
          </div>
          <button className="btn-gov-secondary" onClick={onClose}>✕</button>
        </div>

        <div className="gov-submodal-body">
          {loading ? (
            <p style={{ textAlign: 'center', color: '#64748b' }}>Loading audit records…</p>
          ) : activities.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '2.5rem', color: '#64748b' }}>
              No recent audit activity logged for this user.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
              {activities.map((a) => (
                <div
                  key={a.id}
                  style={{
                    padding: '0.75rem',
                    background: 'rgba(255,255,255,0.03)',
                    border: '1px solid rgba(255,255,255,0.06)',
                    borderRadius: 8,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '0.3rem'
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ color: '#38bdf8', fontFamily: 'monospace', fontWeight: 600, fontSize: '0.8rem' }}>
                        {a.action}
                      </span>
                      <span className={`gov-badge ${a.status === 'SUCCESS' ? 'badge-success' : 'badge-failure'}`} style={{ fontSize: '0.68rem' }}>
                        {a.status}
                      </span>
                    </div>
                    <span style={{ color: '#64748b', fontSize: '0.74rem' }}>
                      {a.timestamp ? new Date(a.timestamp).toLocaleString() : '—'}
                    </span>
                  </div>

                  <div style={{ fontSize: '0.76rem', color: '#94a3b8', display: 'flex', gap: '1rem' }}>
                    <span>Target: <strong style={{ color: '#cbd5e1' }}>{a.resource_type}</strong> ({a.resource_id || 'general'})</span>
                    <span>IP: <strong style={{ color: '#cbd5e1' }}>{a.ip_address || '—'}</strong></span>
                  </div>

                  {a.metadata && Object.keys(a.metadata).length > 0 && (
                    <div style={{ background: 'rgba(0,0,0,0.3)', padding: '0.4rem 0.6rem', borderRadius: 6, fontSize: '0.72rem', color: '#94a3b8', fontFamily: 'monospace' }}>
                      {JSON.stringify(a.metadata)}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div style={{ padding: '0.75rem 1.5rem', background: 'rgba(30, 41, 59, 0.5)', display: 'flex', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          <button className="btn-gov-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}
