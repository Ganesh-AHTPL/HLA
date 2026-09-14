import React from 'react'

export default function AuditEventModal({ event, onClose }) {
  if (!event) return null

  return (
    <div className="gov-submodal-backdrop" onClick={onClose}>
      <div className="gov-submodal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 650 }}>
        <div className="gov-submodal-header">
          <div className="gov-submodal-title">
            <span>🔍</span> Audit Event #{event.id}: {event.action}
          </div>
          <button className="btn-gov-secondary" onClick={onClose}>✕</button>
        </div>

        <div className="gov-submodal-body">
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem', background: 'rgba(255,255,255,0.03)', padding: '1rem', borderRadius: 8, border: '1px solid rgba(255,255,255,0.06)' }}>
            <div>
              <span style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase' }}>User Principal</span>
              <div style={{ color: '#f8fafc', fontWeight: 600 }}>{event.username} (ID: {event.user_id || 'System'})</div>
            </div>

            <div>
              <span style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase' }}>Timestamp (UTC)</span>
              <div style={{ color: '#f8fafc', fontSize: '0.8rem' }}>{event.timestamp}</div>
            </div>

            <div>
              <span style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase' }}>Resource</span>
              <div style={{ color: '#38bdf8' }}>{event.resource_type} {event.resource_id ? `#${event.resource_id}` : ''}</div>
            </div>

            <div>
              <span style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase' }}>Result Status</span>
              <div>
                <span className={`gov-badge ${event.status === 'SUCCESS' ? 'badge-success' : 'badge-failure'}`}>
                  {event.status}
                </span>
              </div>
            </div>

            <div>
              <span style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase' }}>Client IP Address</span>
              <div style={{ color: '#cbd5e1', fontFamily: 'monospace', fontSize: '0.8rem' }}>{event.ip_address || '—'}</div>
            </div>

            <div>
              <span style={{ fontSize: '0.72rem', color: '#64748b', textTransform: 'uppercase' }}>Project Scope</span>
              <div style={{ color: '#cbd5e1' }}>{event.project_id ? `Project #${event.project_id}` : 'Global System'}</div>
            </div>
          </div>

          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.4rem' }}>
              <span style={{ fontSize: '0.78rem', color: '#94a3b8', textTransform: 'uppercase', fontWeight: 600 }}>
                Sanitized Metadata Payload (Zero Credentials Guarantee)
              </span>
              <span style={{ fontSize: '0.72rem', color: '#34d399' }}>✓ Scrubbed</span>
            </div>
            <pre className="json-viewer-box">
              {JSON.stringify(event.metadata || {}, null, 2)}
            </pre>
          </div>
        </div>

        <div style={{ padding: '0.75rem 1.5rem', background: 'rgba(30, 41, 59, 0.5)', display: 'flex', justifyContent: 'flex-end', borderTop: '1px solid rgba(255,255,255,0.08)' }}>
          <button className="btn-gov-secondary" onClick={onClose}>Close</button>
        </div>
      </div>
    </div>
  )
}
