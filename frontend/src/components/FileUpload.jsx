import React, { useState, useRef, useCallback } from 'react'
import axios from 'axios'
import './FileUpload.css'

const ACCEPTED_TYPES = [
  'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', // .xlsx
  'application/vnd.ms-excel',                                           // .xls
]
const ACCEPTED_EXTENSIONS = ['.xlsx', '.xls']

function formatBytes(bytes) {
  if (bytes === 0) return '0 Bytes'
  const k = 1024
  const sizes = ['Bytes', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

function isValidFile(file) {
  const ext = '.' + file.name.split('.').pop().toLowerCase()
  return ACCEPTED_TYPES.includes(file.type) || ACCEPTED_EXTENSIONS.includes(ext)
}

const STATUS = {
  IDLE: 'idle',
  DRAGGING: 'dragging',
  READY: 'ready',
  UPLOADING: 'uploading',
  SUCCESS: 'success',
  ERROR: 'error',
}

export default function FileUpload({ onUploadSuccess, projectId, currentUser }) {
  const [status, setStatus] = useState(STATUS.IDLE)
  const [file, setFile] = useState(null)
  const [progress, setProgress] = useState(0)
  const [errorMsg, setErrorMsg] = useState('')
  const [responseData, setResponseData] = useState(null)
  const inputRef = useRef(null)

  if (currentUser?.role?.toLowerCase() === 'viewer') {
    return (
      <div className="upload-viewer-notice">
        <div className="viewer-notice-icon">👁️</div>
        <div className="viewer-notice-content">
          <h4>Read-Only Viewer Access</h4>
          <p>
            You are signed in with the <strong style={{ color: '#38bdf8' }}>Viewer</strong> role. You can inspect architecture analyses, live database schemas, and data models. HLA document uploads are reserved for <strong style={{ color: '#00f2fe' }}>Architects</strong> and <strong style={{ color: '#fb7185' }}>Admins</strong>.
          </p>
        </div>
      </div>
    )
  }

  const handleFile = useCallback((selectedFile) => {
    if (!selectedFile) return
    if (!isValidFile(selectedFile)) {
      setErrorMsg(`Unsupported file format. Only Excel files (.xlsx, .xls) conforming to the HLA Control Specification template are accepted. Word (.docx, .doc), PDF, CSV, and other formats are strictly not permitted.`)
      setStatus(STATUS.ERROR)
      return
    }
    setFile(selectedFile)
    setStatus(STATUS.READY)
    setErrorMsg('')
    setResponseData(null)
    setProgress(0)
  }, [])

  const onDragOver = (e) => {
    e.preventDefault()
    setStatus(STATUS.DRAGGING)
  }

  const onDragLeave = (e) => {
    e.preventDefault()
    setStatus(file ? STATUS.READY : STATUS.IDLE)
  }

  const onDrop = (e) => {
    e.preventDefault()
    const dropped = e.dataTransfer.files[0]
    handleFile(dropped)
  }

  const onInputChange = (e) => {
    handleFile(e.target.files[0])
  }

  const openFilePicker = () => inputRef.current?.click()

  const uploadFile = async () => {
    if (!file) return

    setStatus(STATUS.UPLOADING)
    setProgress(0)
    setErrorMsg('')

    const formData = new FormData()
    formData.append('file', file)
    if (projectId) {
      formData.append('project_id', projectId)
    }

    try {
      const uploadUrl = projectId ? `/api/projects/${projectId}/upload` : '/api/upload'
      const res = await axios.post(uploadUrl, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (ev) => {
          if (ev.total) {
            const pct = Math.round((ev.loaded * 100) / ev.total)
            setProgress(pct)
          }
        },
      })

      setStatus(STATUS.SUCCESS)
      setResponseData(res.data)
      if (onUploadSuccess) {
        onUploadSuccess(res.data.id)
      }
    } catch (err) {
      setStatus(STATUS.ERROR)
      const msg =
        err.response?.data?.error ||
        (err.code === 'ECONNABORTED'
          ? 'Upload timed out. Try a smaller file.'
          : 'Upload failed. Ensure the backend server is running.')
      setErrorMsg(msg)
    }
  }

  const reset = () => {
    setStatus(STATUS.IDLE)
    setFile(null)
    setProgress(0)
    setErrorMsg('')
    setResponseData(null)
    if (inputRef.current) inputRef.current.value = ''
  }

  const ext = file ? '.' + file.name.split('.').pop().toLowerCase() : ''
  const isWord = ['.docx', '.doc'].includes(ext)

  return (
    <div className="upload-container">
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx,.xls"
        style={{ display: 'none' }}
        onChange={onInputChange}
      />

      {/* ── Dropzone Area ── */}
      <div
        className={`upload-dropzone ${status}`}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={status === STATUS.IDLE || status === STATUS.ERROR ? openFilePicker : undefined}
      >
        <div className="dropzone-ambient-glow" />

        {/* State 1: Idle or Dragging */}
        {(status === STATUS.IDLE || status === STATUS.DRAGGING) && (
          <div className="dropzone-idle-content">
            <div className="dropzone-icon-orb">
              <span style={{ fontSize: '2rem' }}>📊</span>
            </div>
            <h3>Drop your HLA Control Specification (.xlsx) Here</h3>
            <p className="dropzone-hint">
              Drag & drop your standard Excel specification (.xlsx, .xls), or <span className="browse-link">browse files</span>
            </p>
            <div className="supported-formats-pills">
              <span className="fmt-pill xlsx" style={{ borderColor: 'rgba(16, 185, 129, 0.4)', color: '#34d399', background: 'rgba(16, 185, 129, 0.12)' }}>★ .XLSX / .XLS Only (Shared HLA Format)</span>
              <span className="fmt-pill max">Max 50 MB</span>
            </div>
          </div>
        )}

        {/* State 2: File Selected & Ready */}
        {status === STATUS.READY && file && (
          <div className="dropzone-ready-content">
            <div className="file-type-badge excel">
              XLSX
            </div>
            <div className="file-info-block">
              <h4 className="file-name">{file.name}</h4>
              <span className="file-size">{formatBytes(file.size)}</span>
            </div>
            <div className="ready-actions-row">
              <button className="btn-secondary btn-change-file" onClick={openFilePicker}>
                Change File
              </button>
              <button className="btn-primary btn-upload-now" onClick={uploadFile}>
                🚀 Upload & Ingest Specification
              </button>
            </div>
          </div>
        )}

        {/* State 3: Uploading Progress */}
        {status === STATUS.UPLOADING && (
          <div className="dropzone-uploading-content">
            <div className="spinner-cyan" style={{ width: '40px', height: '40px' }} />
            <h4>Ingesting and Analyzing Document…</h4>
            <span className="upload-progress-text">{progress}% Completed</span>
            <div className="upload-progress-bar-track">
              <div className="upload-progress-bar-fill" style={{ width: `${progress}%` }} />
            </div>
          </div>
        )}

        {/* State 4: Success */}
        {status === STATUS.SUCCESS && responseData && (
          <div className="dropzone-success-content">
            <div className="success-icon-badge">✅</div>
            <h4>Ingestion Complete!</h4>
            <p className="success-msg">
              <strong>{responseData.original_name || file?.name}</strong> was successfully ingested and parsed.
            </p>
            {responseData.analysis && (
              <span className="auto-analyzed-tag">
                ✨ Automated Architecture Extraction Active
              </span>
            )}
            <button className="btn-secondary" onClick={reset} style={{ marginTop: '0.85rem' }}>
              + Ingest Another Document
            </button>
          </div>
        )}

        {/* State 5: Error */}
        {status === STATUS.ERROR && (
          <div className="dropzone-error-content">
            <div className="error-icon-badge">⚠️</div>
            <h4>Upload Encountered an Issue</h4>
            <p className="error-msg">{errorMsg}</p>
            <button className="btn-secondary" onClick={reset} style={{ marginTop: '0.75rem' }}>
              Try Again
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
