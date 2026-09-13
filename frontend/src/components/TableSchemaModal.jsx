import { useState } from 'react'
import './TableSchemaModal.css'

export default function TableSchemaModal({ tableData, onClose }) {
  const [activeTab, setActiveTab] = useState('columns') // 'columns' | 'samples'

  if (!tableData) return null

  const columns = tableData.columns || []
  const sampleRows = tableData.sample_rows || []
  const sampleKeys = sampleRows.length > 0 ? Object.keys(sampleRows[0]) : []

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="schema-modal-dialog" onClick={(e) => e.stopPropagation()}>
        <div className="schema-modal-header">
          <div className="schema-modal-title">
            <h3>
              <span>🔍</span> Source DB Schema: {tableData.schema_name}.{tableData.table_name}
            </h3>
            <div className="schema-meta-row">
              <span style={{ color: '#63cab7', fontWeight: 600 }}>
                Est. Rows: {Number(tableData.row_count || 0).toLocaleString()}
              </span>
              <span>·</span>
              <span style={{ color: tableData.is_simulated ? '#ffb347' : '#48d596' }}>
                {tableData.is_simulated ? 'Discovery Sandbox Mode' : '✓ Live Source Database'}
              </span>
            </div>
          </div>
          <button className="btn-close-modal" onClick={onClose}>✕</button>
        </div>

        {tableData.fallback_reason && (
          <div style={{ background: 'rgba(255, 179, 71, 0.1)', color: '#ffb347', padding: '0.6rem 1.5rem', fontSize: '0.78rem', borderBottom: '1px solid rgba(255, 179, 71, 0.2)' }}>
            ⚠️ {tableData.fallback_reason}
          </div>
        )}

        <div className="schema-nav-tabs">
          <button
            className={`schema-tab-btn ${activeTab === 'columns' ? 'active' : ''}`}
            onClick={() => setActiveTab('columns')}
          >
            Columns & Data Types ({columns.length})
          </button>
          <button
            className={`schema-tab-btn ${activeTab === 'samples' ? 'active' : ''}`}
            onClick={() => setActiveTab('samples')}
          >
            Sample Records Preview ({sampleRows.length})
          </button>
        </div>

        <div className="schema-modal-body">
          {activeTab === 'columns' && (
            <table className="schema-data-table">
              <thead>
                <tr>
                  <th style={{ width: '40px' }}>#</th>
                  <th>Column Name</th>
                  <th>Data Type</th>
                  <th>Nullable</th>
                  <th>Default Value</th>
                </tr>
              </thead>
              <tbody>
                {columns.map((col, idx) => (
                  <tr key={idx}>
                    <td style={{ color: 'rgba(224, 234, 244, 0.4)' }}>{idx + 1}</td>
                    <td style={{ fontFamily: 'monospace', fontWeight: 600, color: '#e0eaf4' }}>
                      {col.column_name}
                    </td>
                    <td>
                      <span className="data-type-badge">{col.data_type}</span>
                    </td>
                    <td style={{ color: col.is_nullable === 'YES' ? 'rgba(224, 234, 244, 0.6)' : '#ff7b72' }}>
                      {col.is_nullable}
                    </td>
                    <td style={{ color: 'rgba(224, 234, 244, 0.5)', fontFamily: 'monospace', fontSize: '0.8rem' }}>
                      {col.default || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {activeTab === 'samples' && (
            <div className="sample-grid-wrap">
              {sampleRows.length === 0 ? (
                <p style={{ padding: '2rem', textAlign: 'center', color: 'rgba(224, 234, 244, 0.5)' }}>
                  No preview rows available.
                </p>
              ) : (
                <table className="schema-data-table">
                  <thead>
                    <tr>
                      {sampleKeys.map((k) => (
                        <th key={k}>{k}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {sampleRows.map((row, rIdx) => (
                      <tr key={rIdx}>
                        {sampleKeys.map((k) => (
                          <td key={k} style={{ fontFamily: 'monospace', fontSize: '0.8rem', whiteSpace: 'nowrap' }}>
                            {String(row[k] ?? '—')}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </div>

        <div className="modal-footer" style={{ padding: '0.75rem 1.5rem' }}>
          <button className="btn-modal-cancel" onClick={onClose}>Close Inspector</button>
        </div>
      </div>
    </div>
  )
}
