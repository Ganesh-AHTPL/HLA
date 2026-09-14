import React, { useState, useEffect } from 'react'
import axios from 'axios'

export default function AuditTab({ onNotify, onOpenDetails }) {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)

  // Filters
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo, setDateTo] = useState('')
  const [userQuery, setUserQuery] = useState('')
  const [actionFilter, setActionFilter] = useState('ALL')
  const [resourceFilter, setResourceFilter] = useState('ALL')
  const [statusFilter, setStatusFilter] = useState('ALL')
  const [page, setPage] = useState(1)
  const [pageSize, setPageSize] = useState(25)
  const [total, setTotal] = useState(0)

  // Filter dropdown options
  const [actionOptions, setActionOptions] = useState([])
  const [resourceOptions, setResourceOptions] = useState([])

  useEffect(() => {
    fetchMetaOptions()
  }, [])

  useEffect(() => {
    fetchAuditEvents()
  }, [dateFrom, dateTo, userQuery, actionFilter, resourceFilter, statusFilter, page, pageSize])

  const fetchMetaOptions = async () => {
    try {
      const res = await axios.get('/api/governance/audit/meta')
      setActionOptions(res.data?.actions || [])
      setResourceOptions(res.data?.resource_types || [])
    } catch (err) {
      console.error('Failed to load audit metadata options:', err)
    }
  }

  const fetchAuditEvents = async () => {
    setLoading(true)
    try {
      const params = {
        page,
        page_size: pageSize,
        date_from: dateFrom ? new Date(dateFrom).toISOString() : undefined,
        date_to: dateTo ? new Date(dateTo).toISOString() : undefined,
        user: userQuery.trim() || undefined,
        action: actionFilter,
        resource_type: resourceFilter,
        status: statusFilter
      }
      const res = await axios.get('/api/governance/audit/events', { params })
      setEvents(res.data?.events || [])
      setTotal(res.data?.total || 0)
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to load audit events.', 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleExportCsv = async () => {
    setExporting(true)
    try {
      const params = new URLSearchParams()
      if (actionFilter !== 'ALL') params.append('action', actionFilter)
      if (resourceFilter !== 'ALL') params.append('resource_type', resourceFilter)
      if (statusFilter !== 'ALL') params.append('status', statusFilter)
      if (userQuery.trim()) params.append('user', userQuery.trim())

      const res = await axios.get(`/api/governance/audit/export?${params.toString()}`, {
        responseType: 'blob'
      })

      const blob = new Blob([res.data], { type: 'text/csv;charset=utf-8;' })
      const link = document.createElement('a')
      const url = URL.createObjectURL(blob)
      link.setAttribute('href', url)
      link.setAttribute('download', `hla_audit_log_${new Date().toISOString().slice(0, 10)}.csv`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
      onNotify('Audit CSV file downloaded successfully.', 'success')
    } catch (err) {
      onNotify(err.response?.data?.error || 'Failed to export audit CSV.', 'error')
    } finally {
      setExporting(false)
    }
  }

  const resetFilters = () => {
    setDateFrom('')
    setDateTo('')
    setUserQuery('')
    setActionFilter('ALL')
    setResourceFilter('ALL')
    setStatusFilter('ALL')
    setPage(1)
  }

  const getStatusBadge = (status) => {
    switch (status) {
      case 'SUCCESS':
        return <span className="gov-badge badge-success">✓ Success</span>
      case 'FAILURE':
        return <span className="gov-badge badge-failure">✕ Failure</span>
      case 'WARNING':
        return <span className="gov-badge badge-warning">⚠️ Warning</span>
      default:
        return <span className="gov-badge badge-disabled">{status}</span>
    }
  }

  return (
    <div className="gov-tab-content">
      {/* Filter Bar */}
      <div className="gov-controls-bar">
        <div className="gov-filters-group">
          <input
            type="text"
            className="gov-search-input"
            style={{ minWidth: 160 }}
            placeholder="Filter by user…"
            value={userQuery}
            onChange={(e) => {
              setUserQuery(e.target.value)
              setPage(1)
            }}
          />

          <select
            className="gov-select"
            value={actionFilter}
            onChange={(e) => {
              setActionFilter(e.target.value)
              setPage(1)
            }}
          >
            <option value="ALL">Action: All Actions</option>
            {actionOptions.map((act) => (
              <option key={act} value={act}>{act}</option>
            ))}
          </select>

          <select
            className="gov-select"
            value={resourceFilter}
            onChange={(e) => {
              setResourceFilter(e.target.value)
              setPage(1)
            }}
          >
            <option value="ALL">Resource: All Types</option>
            {resourceOptions.map((res) => (
              <option key={res} value={res}>{res}</option>
            ))}
          </select>

          <select
            className="gov-select"
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value)
              setPage(1)
            }}
          >
            <option value="ALL">Status: All</option>
            <option value="SUCCESS">SUCCESS</option>
            <option value="FAILURE">FAILURE</option>
            <option value="WARNING">WARNING</option>
          </select>

          <button className="btn-gov-secondary" onClick={resetFilters} title="Reset all filters">
            🔄 Reset
          </button>
        </div>

        <button
          className="btn-gov-primary"
          onClick={handleExportCsv}
          disabled={exporting}
          id="btn-export-audit-csv"
        >
          {exporting ? 'Generating CSV…' : '📥 Export CSV'}
        </button>
      </div>

      {/* Audit Events Table */}
      <div className="gov-table-wrap">
        <table className="gov-table">
          <thead>
            <tr>
              <th>Timestamp (UTC)</th>
              <th>User</th>
              <th>Action</th>
              <th>Resource Type</th>
              <th>Resource ID</th>
              <th>Status</th>
              <th>Client IP</th>
              <th style={{ textAlign: 'right' }}>Details</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr>
                <td colSpan="8" style={{ textAlign: 'center', padding: '3rem', color: '#64748b' }}>
                  Querying append-only audit trail…
                </td>
              </tr>
            ) : events.length === 0 ? (
              <tr>
                <td colSpan="8" style={{ textAlign: 'center', padding: '3rem', color: '#64748b' }}>
                  No audit entries found matching the filter criteria.
                </td>
              </tr>
            ) : (
              events.map((e) => (
                <tr key={e.id}>
                  <td style={{ color: '#94a3b8', fontSize: '0.78rem', whiteSpace: 'nowrap' }}>
                    {e.timestamp ? new Date(e.timestamp).toUTCString() : '—'}
                  </td>

                  <td>
                    <strong style={{ color: '#f8fafc' }}>{e.username}</strong>
                  </td>

                  <td>
                    <span style={{ fontFamily: 'monospace', color: '#38bdf8', fontSize: '0.78rem', background: 'rgba(56, 189, 248, 0.08)', padding: '0.15rem 0.45rem', borderRadius: 4 }}>
                      {e.action}
                    </span>
                  </td>

                  <td style={{ color: '#cbd5e1', fontSize: '0.8rem' }}>
                    {e.resource_type}
                  </td>

                  <td style={{ color: '#64748b', fontSize: '0.78rem', fontFamily: 'monospace' }}>
                    {e.resource_id || '—'}
                  </td>

                  <td>{getStatusBadge(e.status)}</td>

                  <td style={{ color: '#64748b', fontSize: '0.76rem', fontFamily: 'monospace' }}>
                    {e.ip_address || '—'}
                  </td>

                  <td style={{ textAlign: 'right' }}>
                    <button
                      className="btn-gov-secondary"
                      style={{ padding: '0.25rem 0.6rem', fontSize: '0.75rem' }}
                      onClick={() => onOpenDetails(e)}
                    >
                      🔍 Inspect
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontSize: '0.8rem', color: '#94a3b8' }}>
        <div>
          Showing {events.length} of {total} immutable audit records
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
    </div>
  )
}
