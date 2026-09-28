import React, { useState, useEffect, useMemo } from 'react';
import api from '../services/api';

export default function HlaStudioWorkbench({
  activeProject,
  projectDocs = [],
  selectedDocId,
  onSelectDocId,
  onRefreshDocs,
  currentUser,
  onNavigateTab,
  showToast,
}) {
  const [doc, setDoc] = useState(null);
  const [loading, setLoading] = useState(false);
  const [analysisRunning, setAnalysisRunning] = useState(false);
  const [analysisStep, setAnalysisStep] = useState(0); // 0 = idle, 1 = parsing, 2 = mapping, 3 = validating
  const [progressPercent, setProgressPercent] = useState(0);
  const [openStage, setOpenStage] = useState(null);
  const [docDropdownOpen, setDocDropdownOpen] = useState(false);
  const [activeFileTab, setActiveFileTab] = useState('components');
  const [mappingFilter, setMappingFilter] = useState('all');
  const [priorityFilter, setPriorityFilter] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedSourceTable, setSelectedSourceTable] = useState(null);

  // Close source detail modal on Escape key
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        setSelectedSourceTable(null);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const activeDoc = projectDocs.find((d) => d.id === selectedDocId) || projectDocs[0] || null;

  useEffect(() => {
    if (activeDoc?.id) {
      fetchDocDetails(activeDoc.id);
    } else {
      setDoc(null);
    }
  }, [activeDoc?.id]);

  const fetchDocDetails = async (id) => {
    setLoading(true);
    try {
      const res = await api.get(`/api/documents/${id}`);
      setDoc(res.data);
    } catch (err) {
      console.error('Failed to load document details:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRunAnalysis = async () => {
    if (!doc?.id) return;
    setAnalysisRunning(true);
    setAnalysisStep(1);
    setProgressPercent(33);

    // Step 1: parsing
    setTimeout(async () => {
      setAnalysisStep(2);
      setProgressPercent(66);

      // Step 2: semantic mapping
      setTimeout(async () => {
        setAnalysisStep(3);
        setProgressPercent(100);

        try {
          const res = await api.post(`/api/documents/${doc.id}/analyze`);
          if (res.data?.analysis) {
            setDoc((prev) => ({
              ...prev,
              status: 'analyzed',
              analysis: res.data.analysis,
            }));
            if (onRefreshDocs) onRefreshDocs();
          }
          if (showToast) showToast('Document analysis complete — structure dynamically discovered');
        } catch (err) {
          if (showToast) showToast(err.response?.data?.error || 'Analysis failed.');
        } finally {
          setTimeout(() => {
            setAnalysisRunning(false);
            setAnalysisStep(0);
            setProgressPercent(0);
          }, 1000);
        }
      }, 600);
    }, 600);
  };

  const toggleStage = (stageNum) => {
    setOpenStage((prev) => (prev === stageNum ? null : stageNum));
  };

  const isViewer = currentUser?.role?.toLowerCase() === 'viewer';
  const canDelete = !isViewer;
  const [deletingDocId, setDeletingDocId] = useState(null);

  const handleDeleteDoc = async (docIdToDelete, docName) => {
    if (!docIdToDelete) return;
    const displayName = docName || 'this document';
    if (
      !window.confirm(
        `Are you sure you want to remove document "${displayName}"?\n\nThis will remove the uploaded workbook and all extracted metadata.`
      )
    ) {
      return;
    }

    setDeletingDocId(docIdToDelete);
    try {
      await api.delete(`/api/documents/${docIdToDelete}`);
      if (showToast) {
        showToast(`Document "${displayName}" removed successfully.`);
      }
      if (onRefreshDocs) {
        await onRefreshDocs();
      }
      const remaining = projectDocs.filter((d) => d.id !== docIdToDelete);
      if (remaining.length > 0) {
        onSelectDocId(remaining[0].id);
      } else {
        onSelectDocId(null);
      }
    } catch (err) {
      const msg = err.response?.data?.error || 'Failed to remove document.';
      if (showToast) {
        showToast(msg);
      } else {
        alert(msg);
      }
    } finally {
      setDeletingDocId(null);
    }
  };

  // ── Document Metadata Extraction (100% Dynamic) ──
  const analysis = doc?.analysis && typeof doc.analysis === 'object' ? doc.analysis : {};
  const components = Array.isArray(analysis.components) ? analysis.components : [];
  const requirements = Array.isArray(analysis.requirements) ? analysis.requirements : [];
  const sources = Array.isArray(analysis.sources)
    ? analysis.sources
    : Array.isArray(analysis.source_tables)
    ? analysis.source_tables
    : [];
  const allTableObjects = Array.isArray(analysis.all_table_objects)
    ? analysis.all_table_objects
    : (Array.isArray(analysis.hla_data_model?.all_table_objects)
      ? analysis.hla_data_model.all_table_objects
      : (sources.length > 0 ? sources : []));
  const dataModel = Array.isArray(analysis.data_model)
    ? analysis.data_model
    : (Array.isArray(analysis.target_tables) ? analysis.target_tables : []);
  const logicalInputs = Array.isArray(analysis.logical_input_streams)
    ? analysis.logical_input_streams
    : (Array.isArray(analysis.logical_inputs) ? analysis.logical_inputs : []);
  const lineageRelationships = Array.isArray(analysis.lineage_relationships)
    ? analysis.lineage_relationships
    : (Array.isArray(analysis.hla_data_model?.lineage_relationships) ? analysis.hla_data_model.lineage_relationships : []);
  const rulesObj = analysis.rules && typeof analysis.rules === 'object' ? analysis.rules : {};
  const filterRules = Array.isArray(rulesObj.filter_rules) ? rulesObj.filter_rules : [];
  const balanceRules = Array.isArray(rulesObj.balance_rules) ? rulesObj.balance_rules : [];
  const businessRules = Array.isArray(rulesObj.business_rules) ? rulesObj.business_rules : [];
  const allRules = [...filterRules, ...balanceRules, ...businessRules.filter(b => !filterRules.includes(b) && !balanceRules.includes(b))];
  const mappings = Array.isArray(analysis.mappings) ? analysis.mappings : [];
  const pipelineStages = Array.isArray(analysis.pipeline_stages) ? analysis.pipeline_stages : [];
  const buckets = Array.isArray(analysis.buckets) ? analysis.buckets : (Array.isArray(analysis.reconciliation) ? analysis.reconciliation : []);
  const rawSheets = analysis.raw_sheets && typeof analysis.raw_sheets === 'object' ? analysis.raw_sheets : {};
  const sheetNames = analysis.sheet_names || Object.keys(rawSheets);
  const detectedSections = Array.isArray(analysis.detected_sections) ? analysis.detected_sections : [];
  const summaryCounts = analysis.summary_counts || {};

  const [archLayerFilter, setArchLayerFilter] = useState('all');

  // Build available dynamic sub-tabs
  const availableTabs = useMemo(() => {
    const tabs = [];
    if (sources.length > 0) {
      tabs.push({ id: 'sources', label: 'Source Systems', count: sources.length });
    }
    if (dataModel.length > 0) {
      tabs.push({ id: 'datamodel', label: 'Target Architecture', count: dataModel.length });
    }
    if (allRules.length > 0) {
      tabs.push({ id: 'rules', label: 'Business Rules & Filters', count: allRules.length });
    }
    if (mappings.length > 0) {
      tabs.push({ id: 'mappings', label: 'Attribute Mapping (Lineage)', count: mappings.length });
    }
    if (buckets.length > 0) {
      tabs.push({ id: 'buckets', label: 'Buckets & KRI', count: buckets.length });
    }
    if (components.length > 0) {
      tabs.push({ id: 'components', label: 'Architecture Components', count: components.length });
    }
    if (requirements.length > 0) {
      tabs.push({ id: 'requirements', label: 'Requirements', count: requirements.length });
    }
    tabs.push({ id: 'raw_sheets', label: 'Discovered Sheets', count: sheetNames.length });
    tabs.push({ id: 'synthesis', label: 'Architecture Synthesis & Code' });
    return tabs;
  }, [sources.length, dataModel.length, allRules.length, mappings.length, buckets.length, components.length, requirements.length, sheetNames.length]);

  // Adjust active tab if current tab is not available
  useEffect(() => {
    if (availableTabs.length > 0) {
      const exists = availableTabs.some((t) => t.id === activeFileTab);
      if (!exists) {
        setActiveFileTab(availableTabs[0].id);
      }
    }
  }, [availableTabs, activeFileTab]);

  // Filter components
  const filteredComponents = useMemo(() => {
    if (!searchQuery.trim()) return components;
    const q = searchQuery.toLowerCase();
    return components.filter(
      (c) =>
        c.component?.toLowerCase().includes(q) ||
        c.responsibility?.toLowerCase().includes(q) ||
        c.input?.toLowerCase().includes(q) ||
        c.output?.toLowerCase().includes(q) ||
        c.technology?.toLowerCase().includes(q) ||
        c.interaction?.toLowerCase().includes(q)
    );
  }, [components, searchQuery]);

  // Filter requirements
  const filteredRequirements = useMemo(() => {
    let list = requirements;
    if (priorityFilter !== 'all') {
      list = list.filter((r) => (r.priority || '').toLowerCase() === priorityFilter.toLowerCase());
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (r) =>
          r.requirement?.toLowerCase().includes(q) ||
          r.description?.toLowerCase().includes(q) ||
          r.acceptance_criteria?.toLowerCase().includes(q)
      );
    }
    return list;
  }, [requirements, priorityFilter, searchQuery]);

  // Filter mappings
  const filteredMappings = useMemo(() => {
    let list = mappings;
    if (mappingFilter === 'direct') {
      list = list.filter((m) => (m.mapping_type || '').toLowerCase() === 'direct');
    } else if (mappingFilter === 'derived') {
      list = list.filter((m) => (m.mapping_type || '').toLowerCase() === 'derived');
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      list = list.filter(
        (m) =>
          m.target_column?.toLowerCase().includes(q) ||
          m.source_field?.toLowerCase().includes(q) ||
          m.source_table?.toLowerCase().includes(q) ||
          m.derivation_logic?.toLowerCase().includes(q)
      );
    }
    return list;
  }, [mappings, mappingFilter, searchQuery]);

  // Filter sources dynamically
  const filteredSources = useMemo(() => {
    if (!searchQuery.trim()) return sources;
    const q = searchQuery.toLowerCase();
    return sources.filter((s) => {
      const tName = (s.full_table_name || s.source_table_name || s.table_name || '').toLowerCase();
      const schema = (s.schema || s.source_schema || '').toLowerCase();
      const db = (s.database || s.database_name || s.source_system || s.source_db || '').toLowerCase();
      const loadType = (s.load_type || s.type_of_load || '').toLowerCase();
      const freq = (s.frequency || '').toLowerCase();
      const sched = (s.schedule_time || s.schedule || '').toLowerCase();
      return (
        tName.includes(q) ||
        schema.includes(q) ||
        db.includes(q) ||
        loadType.includes(q) ||
        freq.includes(q) ||
        sched.includes(q)
      );
    });
  }, [sources, searchQuery]);

  // Related metadata for currently selected source table
  const relatedSourceMappings = useMemo(() => {
    if (!selectedSourceTable) return [];
    const tName = (selectedSourceTable.source_table_name || selectedSourceTable.table_name || '').toLowerCase();
    const fullTName = (selectedSourceTable.full_table_name || '').toLowerCase();
    const schema = (selectedSourceTable.schema || '').toLowerCase();
    return mappings.filter((m) => {
      const mTable = (m.source_table || '').toLowerCase();
      const mField = (m.source_field || '').toLowerCase();
      if (!mTable && !mField) return false;
      return (
        (tName && (mTable === tName || mTable.includes(tName))) ||
        (fullTName && (mTable === fullTName || mTable.includes(fullTName))) ||
        (schema && (mTable.startsWith(`${schema}.`) || mField.startsWith(`${schema}.`)))
      );
    });
  }, [selectedSourceTable, mappings]);

  const relatedSourceRules = useMemo(() => {
    if (!selectedSourceTable) return [];
    const tName = (selectedSourceTable.source_table_name || selectedSourceTable.table_name || '').toLowerCase();
    const fullTName = (selectedSourceTable.full_table_name || '').toLowerCase();
    const schema = (selectedSourceTable.schema || '').toLowerCase();
    return allRules.filter((r) => {
      const stream = (r.data_stream || r.target || r.source_table || '').toLowerCase();
      const stmt = (r.rule_statement || r.description || r.rule_description || '').toLowerCase();
      return (
        (tName && (stream.includes(tName) || stmt.includes(tName))) ||
        (fullTName && (stream.includes(fullTName) || stmt.includes(fullTName))) ||
        (schema && (stream.includes(schema) || stmt.includes(schema)))
      );
    });
  }, [selectedSourceTable, allRules]);

  const relatedTargetAttributes = useMemo(() => {
    const list = new Set();
    relatedSourceMappings.forEach((m) => {
      if (m.target_column) list.add(m.target_column);
    });
    return Array.from(list);
  }, [relatedSourceMappings]);

  if (!activeDoc) {
    return (
      <div className="empty-state">
        <div className="icon">⇪</div>
        <h3>No documents in this workspace</h3>
        <p>
          Drop an architecture or specification Excel workbook (.xlsx, .xls) here.
          HLA Studio will parse it and extract components, requirements, tables, and lineage dynamically.
        </p>
        <button
          className="btn-buy"
          style={{ minWidth: 0, display: 'inline-flex', margin: '0 auto' }}
          onClick={() => onNavigateTab('ingest')}
        >
          + Upload a document
        </button>
      </div>
    );
  }

  return (
    <div className="panel active" id="panel-workbench">
      {/* ── Unified Document Card ── */}
      <div className="doc-card">
        <div className="doc-card-left">
          <div className="doc-icon">XLSX</div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', position: 'relative' }}>
              <button
                className="doc-switch"
                onClick={() => setDocDropdownOpen(!docDropdownOpen)}
                style={{
                  fontSize: '15px',
                  fontWeight: 700,
                  color: 'var(--link)',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '4px',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  padding: 0,
                }}
              >
                {activeDoc.original_name || activeDoc.filename} ▾
              </button>
              {docDropdownOpen && (
                <div className="doc-dropdown open">
                  {projectDocs.map((d) => (
                    <div
                      key={d.id}
                      className={`opt ${d.id === activeDoc.id ? 'sel' : ''}`}
                      style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}
                      onClick={() => {
                        onSelectDocId(d.id);
                        setDocDropdownOpen(false);
                      }}
                    >
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {d.original_name || d.filename}
                      </span>
                      {canDelete && (
                        <span
                          title="Remove this document"
                          style={{
                            color: '#ef4444',
                            padding: '2px 6px',
                            borderRadius: '4px',
                            fontSize: '12px',
                            cursor: 'pointer',
                            flexShrink: 0,
                          }}
                          onClick={(e) => {
                            e.stopPropagation();
                            setDocDropdownOpen(false);
                            handleDeleteDoc(d.id, d.original_name || d.filename);
                          }}
                        >
                          🗑️
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <div className="doc-meta">
              <span className="status-chip">✓ {doc?.status === 'analyzed' ? 'Analyzed' : 'Ready'}</span>
              <span>{((activeDoc.file_size || 0) / 1024).toFixed(1)} KB</span>
              <span>·</span>
              <span>Doc #{activeDoc.id}</span>
              <span>·</span>
              <span>Uploaded {activeDoc.uploaded_at ? new Date(activeDoc.uploaded_at).toLocaleDateString() : 'Today'}</span>
              <span>·</span>
              <span className="compliance">
                ★ {sheetNames.length} {sheetNames.length === 1 ? 'Sheet' : 'Sheets'} Discovered
              </span>
            </div>
          </div>
        </div>

        <div className="doc-actions">
          <a
            onClick={(e) => {
              e.preventDefault();
              onNavigateTab('ingest');
            }}
            style={{
              fontSize: '12px',
              fontWeight: 600,
              color: 'var(--link)',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              marginRight: '6px',
            }}
          >
            + Upload another document
          </a>
          <button
            className="btn-buy"
            id="analyzeBtn"
            onClick={handleRunAnalysis}
            disabled={analysisRunning}
          >
            {analysisRunning ? (
              <>
                <span className="spinner"></span> Running analysis…
              </>
            ) : (
              'Run AI Architecture Analysis'
            )}
          </button>
          {sources.length > 0 && (
            <button className="btn-cart" onClick={() => onNavigateTab('connectors')}>
              Source DBs ({sources.length})
            </button>
          )}
          {canDelete && (
            <button
              className="btn-danger-ghost"
              onClick={() => handleDeleteDoc(activeDoc.id, activeDoc.original_name || activeDoc.filename)}
              disabled={deletingDocId === activeDoc.id}
              title="Remove this uploaded document"
            >
              {deletingDocId === activeDoc.id ? 'Removing…' : '🗑️ Remove Document'}
            </button>
          )}
        </div>
      </div>

      {/* ── Analysis Progress Animation Box ── */}
      <div className={`analysis-progress ${analysisRunning ? 'show' : ''}`} id="analysisProgress">
        <div className={`step ${analysisStep > 1 ? 'done' : analysisStep === 1 ? 'current' : ''}`}>
          <span className="mark">{analysisStep > 1 ? '✓' : analysisStep === 1 ? '◐' : '○'}</span>
          Discovering workbook sheets &amp; table boundaries…
        </div>
        <div className={`step ${analysisStep > 2 ? 'done' : analysisStep === 2 ? 'current' : ''}`}>
          <span className="mark">{analysisStep > 2 ? '✓' : analysisStep === 2 ? '◐' : '○'}</span>
          Inferring semantic entities, architecture components &amp; requirements…
        </div>
        <div className={`step ${analysisStep === 3 ? 'current done' : ''}`}>
          <span className="mark">{analysisStep === 3 ? '✓' : '○'}</span>
          Building isolated document knowledge model…
        </div>
        <div className="progress-track">
          <div className="progress-fill" style={{ width: `${progressPercent}%` }}></div>
        </div>
      </div>

      {/* ── Dynamic Stat Metric Cards ── */}
      <div className="stats">
        {components.length > 0 && (
          <div className="stat" title="Architecture components detected in workbook">
            <div className="stat-label">Architecture Components</div>
            <div className="stat-value">{components.length}</div>
            <div className="stat-sub">
              {components.map((c) => c.component).slice(0, 2).join(', ')}
              {components.length > 2 ? ` +${components.length - 2} more` : ''}
            </div>
          </div>
        )}

        {requirements.length > 0 && (
          <div className="stat" title="Requirements parsed from specification">
            <div className="stat-label">Requirements</div>
            <div className="stat-value">{requirements.length}</div>
            <div className="stat-sub">
              {requirements.filter((r) => (r.priority || '').toLowerCase() === 'high').length} high priority ·{' '}
              {requirements.filter((r) => (r.priority || '').toLowerCase() === 'medium').length} medium
            </div>
          </div>
        )}

        {sources.length > 0 && (
          <div className="stat" title="Physical upstream sources defined in Source Systems sheet">
            <div className="stat-label">Physical Sources</div>
            <div className="stat-value">{sources.length}</div>
            <div className="stat-sub">
              {sources.filter((s) => (s.type_of_load || '').toLowerCase().includes('truncate')).length} truncate ·{' '}
              {sources.filter((s) => (s.type_of_load || '').toLowerCase().includes('append')).length} append
            </div>
          </div>
        )}

        {dataModel.length > 0 && (
          <div className="stat" title="Target architecture entities defined in Data Model sheet">
            <div className="stat-label">Target Architecture</div>
            <div className="stat-value">{dataModel.length}</div>
            <div className="stat-sub">Data Model table entities</div>
          </div>
        )}

        {allRules.length > 0 && (
          <div className="stat" title="Validation & Business Rules">
            <div className="stat-label">Business & Filter Rules</div>
            <div className="stat-value">{allRules.length}</div>
            <div className="stat-sub">
              {filterRules.length} filter · {balanceRules.length} balance
            </div>
          </div>
        )}

        {mappings.length > 0 && (
          <div className="stat" title="Target attributes & mappings">
            <div className="stat-label">Target Attributes</div>
            <div className="stat-value">{mappings.length}</div>
            <div className="stat-sub">
              {mappings.filter((m) => m.mapping_type === 'Direct').length} direct ·{' '}
              {mappings.filter((m) => m.mapping_type === 'Derived').length} derived
            </div>
          </div>
        )}

        {/* Total Sheets Card */}
        <div className="stat" title="Total sheets scanned in workbook">
          <div className="stat-label">Workbook Sheets</div>
          <div className="stat-value">{sheetNames.length || 1}</div>
          <div className="stat-sub">
            {summaryCounts.total_rows_scanned || 0} rows scanned · {detectedSections.length} detected sections
          </div>
        </div>
      </div>

      {/* ── Architecture Component Interaction (Only if actual Architecture Components exist in document) ── */}
      {components.length > 0 && (
        <>
          <div className="pipeline-head">
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <span className="lineage-tag">Document lineage</span>
              <h2>Component Interaction & Data Flow</h2>
            </div>
            <div className="pipeline-head-right">Click a component to inspect responsibilities &amp; I/O</div>
          </div>

          <div className="schematic">
            {components.map((c, idx) => {
              const stageNum = idx + 1;
              const isOpen = openStage === stageNum;
              return (
                <div
                  key={idx}
                  className={`stage ${isOpen ? 'open' : ''}`}
                  onClick={() => toggleStage(stageNum)}
                >
                  <div className="stage-num">{stageNum}</div>
                  <div className="stage-title">{c.component}</div>
                  <div className="stage-desc">{c.responsibility || c.technology || 'Core component'}</div>
                  <span className="stage-link">{isOpen ? 'Close details ▴' : 'Inspect I/O ▾'}</span>
                </div>
              );
            })}

            {/* Dynamic Interactive Drawer */}
            {openStage && openStage <= components.length && (
              <div className="schematic-drawer">
                {(() => {
                  const c = components[openStage - 1];
                  return (
                    <div>
                      <strong>Component {openStage} — {c.component}:</strong>
                      <div style={{ marginTop: '8px', display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '10px' }}>
                        <div style={{ padding: '8px 12px', background: 'rgba(59, 130, 246, 0.08)', borderRadius: '6px', border: '1px solid rgba(59, 130, 246, 0.2)' }}>
                          <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--link)', fontWeight: 700 }}>Responsibility</span>
                          <div style={{ marginTop: '4px', fontSize: '13px', fontWeight: 600 }}>{c.responsibility || 'Not specified'}</div>
                        </div>
                        <div style={{ padding: '8px 12px', background: 'rgba(16, 185, 129, 0.08)', borderRadius: '6px', border: '1px solid rgba(16, 185, 129, 0.2)' }}>
                          <span style={{ fontSize: '11px', textTransform: 'uppercase', color: '#10b981', fontWeight: 700 }}>Consumes (Input)</span>
                          <div style={{ marginTop: '4px', fontSize: '13px', fontFamily: 'var(--font-mono)' }}>{c.input || 'None / Ingestion Start'}</div>
                        </div>
                        <div style={{ padding: '8px 12px', background: 'rgba(245, 158, 11, 0.08)', borderRadius: '6px', border: '1px solid rgba(245, 158, 11, 0.2)' }}>
                          <span style={{ fontSize: '11px', textTransform: 'uppercase', color: '#f59e0b', fontWeight: 700 }}>Produces (Output)</span>
                          <div style={{ marginTop: '4px', fontSize: '13px', fontFamily: 'var(--font-mono)' }}>{c.output || 'Terminal / Analytics Dataset'}</div>
                        </div>
                        <div style={{ padding: '8px 12px', background: 'rgba(139, 92, 246, 0.08)', borderRadius: '6px', border: '1px solid rgba(139, 92, 246, 0.2)' }}>
                          <span style={{ fontSize: '11px', textTransform: 'uppercase', color: '#8b5cf6', fontWeight: 700 }}>Technology / Interaction</span>
                          <div style={{ marginTop: '4px', fontSize: '13px' }}>
                            <code>{c.technology || 'Generic Platform'}</code> · {c.interaction || 'Direct'}
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })()}
              </div>
            )}
          </div>
        </>
      )}

      {/* ── Dynamic File Sub-Tabs ── */}
      <div className="file-tabs">
        {availableTabs.map((tab) => (
          <button
            key={tab.id}
            className={`file-tab ${activeFileTab === tab.id ? 'active' : ''}`}
            onClick={() => {
              setActiveFileTab(tab.id);
              setSearchQuery('');
            }}
          >
            {tab.label} {tab.count !== undefined && <span className="n">({tab.count})</span>}
          </button>
        ))}
      </div>

      {/* ── Sub-Tab Content Displays (Data-Driven, No Hardcoding) ── */}
      <div style={{ marginTop: '16px' }}>
        {/* Tab: Architecture Components */}
        {activeFileTab === 'components' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <span style={{ fontSize: '13px', color: 'var(--text-mute)' }}>
                Showing {filteredComponents.length} architecture components discovered in workbook.
              </span>
              <input
                type="text"
                placeholder="Search components, inputs, outputs…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid var(--border)',
                  background: 'var(--bg-card)',
                  color: 'var(--text)',
                  fontSize: '12.5px',
                  width: '260px',
                }}
              />
            </div>
            <div className="table-responsive-wrapper">
              <table className="enterprise-data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Component Name</th>
                    <th>Responsibility</th>
                    <th>Consumes (Input)</th>
                    <th>Produces (Output)</th>
                    <th>Technology</th>
                    <th>Interaction</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredComponents.length > 0 ? (
                    filteredComponents.map((c, idx) => (
                      <tr key={idx}>
                        <td>{idx + 1}</td>
                        <td style={{ fontWeight: 700, color: 'var(--link)' }}>{c.component}</td>
                        <td style={{ fontSize: '13px', color: 'var(--text)' }}>{c.responsibility || '-'}</td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '12.5px' }}>
                          <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.1)', color: '#10b981', borderColor: 'rgba(16, 185, 129, 0.3)' }}>
                            {c.input || '-'}
                          </span>
                        </td>
                        <td style={{ fontFamily: 'var(--font-mono)', fontSize: '12.5px' }}>
                          <span className="badge" style={{ background: 'rgba(59, 130, 246, 0.1)', color: 'var(--link)', borderColor: 'rgba(59, 130, 246, 0.3)' }}>
                            {c.output || '-'}
                          </span>
                        </td>
                        <td>
                          <span className="badge" style={{ background: '#F1F5F9', color: '#334155' }}>
                            {c.technology || '-'}
                          </span>
                        </td>
                        <td style={{ fontSize: '12.5px' }}>{c.interaction || '-'}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={7} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-mute)' }}>
                        No components matched your search query.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab: Requirements */}
        {activeFileTab === 'requirements' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px', flexWrap: 'wrap', gap: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '13px', color: 'var(--text-mute)' }}>
                  Showing {filteredRequirements.length} requirements.
                </span>
                <div className="btn-group" style={{ display: 'inline-flex', gap: '4px' }}>
                  {['all', 'High', 'Medium', 'Low'].map((p) => (
                    <button
                      key={p}
                      onClick={() => setPriorityFilter(p)}
                      style={{
                        padding: '3px 10px',
                        fontSize: '11.5px',
                        borderRadius: '4px',
                        border: '1px solid var(--border)',
                        background: priorityFilter.toLowerCase() === p.toLowerCase() ? 'var(--navy)' : 'var(--bg-card)',
                        color: priorityFilter.toLowerCase() === p.toLowerCase() ? '#fff' : 'var(--text)',
                        cursor: 'pointer',
                        fontWeight: 600,
                      }}
                    >
                      {p === 'all' ? 'All Priorities' : p}
                    </button>
                  ))}
                </div>
              </div>
              <input
                type="text"
                placeholder="Search requirements, criteria…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid var(--border)',
                  background: 'var(--bg-card)',
                  color: 'var(--text)',
                  fontSize: '12.5px',
                  width: '260px',
                }}
              />
            </div>
            <div className="table-responsive-wrapper">
              <table className="enterprise-data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Requirement ID</th>
                    <th>Description</th>
                    <th>Priority</th>
                    <th>Acceptance Criteria</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredRequirements.length > 0 ? (
                    filteredRequirements.map((r, idx) => {
                      const isHigh = (r.priority || '').toLowerCase() === 'high';
                      const isMed = (r.priority || '').toLowerCase() === 'medium';
                      return (
                        <tr key={idx}>
                          <td>{idx + 1}</td>
                          <td>
                            <span className="badge" style={{ background: 'var(--navy)', color: '#fff', borderColor: 'var(--navy)', fontWeight: 700 }}>
                              {r.requirement}
                            </span>
                          </td>
                          <td style={{ fontSize: '13px', color: 'var(--text)', fontWeight: 500 }}>
                            {r.description}
                          </td>
                          <td>
                            <span
                              className="badge"
                              style={{
                                background: isHigh ? 'rgba(239, 68, 68, 0.12)' : isMed ? 'rgba(245, 158, 11, 0.12)' : 'rgba(16, 185, 129, 0.12)',
                                color: isHigh ? '#ef4444' : isMed ? '#f59e0b' : '#10b981',
                                borderColor: isHigh ? 'rgba(239, 68, 68, 0.3)' : isMed ? 'rgba(245, 158, 11, 0.3)' : 'rgba(16, 185, 129, 0.3)',
                                fontWeight: 700,
                              }}
                            >
                              {r.priority || 'Medium'}
                            </span>
                          </td>
                          <td style={{ fontSize: '12.5px', color: 'var(--text-mute)' }}>
                            {r.acceptance_criteria || '-'}
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={5} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-mute)' }}>
                        No requirements matched your filter.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab: Source Systems (Physical Sources Only) */}
        {activeFileTab === 'sources' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: 'var(--text)' }}>
                  SOURCE SYSTEMS ({sources.length} Physical Upstream Source{sources.length === 1 ? '' : 's'})
                </h3>
                <p style={{ margin: '2px 0 0', fontSize: '12px', color: 'var(--text-mute)' }}>
                  Physical upstream database tables defined strictly in the Source Systems section of the workbook.
                </p>
              </div>

              <input
                type="text"
                placeholder="Search source system, database, schema, table…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid var(--border)',
                  background: 'var(--bg-card)',
                  color: 'var(--text)',
                  fontSize: '12.5px',
                  width: '280px',
                }}
              />
            </div>

            <div className="table-responsive-wrapper">
              <table className="enterprise-data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Source System</th>
                    <th>Database</th>
                    <th>Schema</th>
                    <th>Source Table</th>
                    <th>Load Type</th>
                    <th>Frequency</th>
                    <th>Schedule</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    let displayList = sources;
                    if (searchQuery.trim()) {
                      const q = searchQuery.toLowerCase();
                      displayList = displayList.filter(s =>
                        (s.source_system || '').toLowerCase().includes(q) ||
                        (s.database || s.source_db || '').toLowerCase().includes(q) ||
                        (s.schema || s.source_schema || '').toLowerCase().includes(q) ||
                        (s.table || s.source_table || '').toLowerCase().includes(q) ||
                        (s.type_of_load || s.load_type || '').toLowerCase().includes(q) ||
                        (s.frequency || '').toLowerCase().includes(q) ||
                        (s.schedule_time || s.schedule || '').toLowerCase().includes(q)
                      );
                    }

                    if (displayList.length === 0) {
                      return (
                        <tr>
                          <td colSpan={10} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-mute)' }}>
                            No physical source records found in the uploaded workbook.
                          </td>
                        </tr>
                      );
                    }

                    return displayList.map((s, idx) => {
                      const srcSystem = s.source_system || s.source_name || s.database || 'Not specified';
                      const srcDb = s.database || s.source_db || s.source_database || 'Not specified';
                      const srcSchema = s.schema || s.source_schema || s.schema_name || 'public';
                      const srcTable = s.table || s.source_table || s.source_table_name || s.table_name || '';
                      const loadType = s.type_of_load || s.load_type || 'Truncate and load';
                      const freq = s.frequency || 'Daily';
                      const sched = s.schedule_time || s.schedule || s.run_time || '—';
                      const status = s.status || s.active || 'Active';

                      return (
                        <tr
                          key={idx}
                          style={{ cursor: 'pointer' }}
                          onClick={() => setSelectedSourceTable(s)}
                          title="Click to inspect source table details"
                        >
                          <td>{idx + 1}</td>
                          <td style={{ fontWeight: 600, color: 'var(--text)' }}>
                            {srcSystem}
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                            {srcDb}
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text-secondary)' }}>
                            {srcSchema}
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--link)' }}>
                            {srcTable}
                          </td>
                          <td>
                            <span className="badge" style={{
                              background: String(loadType).toLowerCase().includes('append') ? 'rgba(245, 158, 11, 0.12)' : '#E8F0FE',
                              color: String(loadType).toLowerCase().includes('append') ? '#f59e0b' : 'var(--accent-dark)',
                              fontWeight: 600
                            }}>
                              {loadType}
                            </span>
                          </td>
                          <td style={{ fontSize: '12px' }}>{freq}</td>
                          <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>{sched}</td>
                          <td>
                            <span className="badge" style={{ background: 'rgba(34, 197, 94, 0.12)', color: '#22c55e', fontWeight: 600 }}>
                              {status}
                            </span>
                          </td>
                          <td>
                            <button
                              className="btn-ghost"
                              style={{ padding: '3px 8px', fontSize: '11.5px' }}
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedSourceTable(s);
                              }}
                            >
                              Inspect ↗
                            </button>
                          </td>
                        </tr>
                      );
                    });
                  })()}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab: Rules */}
        {activeFileTab === 'rules' && (
          <div className="table-responsive-wrapper">
            <table className="enterprise-data-table">
              <thead>
                <tr>
                  <th>Rule ID</th>
                  <th>Rule Category</th>
                  <th>Target Dataset / Stream</th>
                  <th>Filtration &amp; Balance Criteria</th>
                  <th>Severity</th>
                </tr>
              </thead>
              <tbody>
                {allRules.length > 0 ? (
                  allRules.map((r, idx) => (
                    <tr key={idx}>
                      <td>
                        <span className="badge" style={{ background: 'var(--navy)', color: '#fff', borderColor: 'var(--navy)' }}>
                          {r.rule_id || `R${idx + 1}`}
                        </span>
                      </td>
                      <td style={{ fontWeight: 600 }}>{r.category || r.rule_type || 'Validation'}</td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                        {r.data_stream || r.target || r.source_table || 'Core'}
                      </td>
                      <td style={{ fontSize: '12.5px', color: 'var(--text)' }}>
                        {r.rule_statement || r.description || r.rule_description || '-'}
                      </td>
                      <td>
                        <span className="badge" style={{ background: '#FEF3C7', color: '#92400E', borderColor: '#FCD34D' }}>
                          {r.severity || 'MANDATORY'}
                        </span>
                      </td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={5} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-mute)' }}>
                      No rules detected in this document.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Tab: Mappings */}
        {activeFileTab === 'mappings' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ fontSize: '13px', color: 'var(--text-mute)' }}>
                  Showing {filteredMappings.length} mappings.
                </span>
                <button
                  className={`btn-ghost ${mappingFilter === 'all' ? 'active' : ''}`}
                  onClick={() => setMappingFilter('all')}
                  style={{ fontSize: '12px', padding: '3px 8px' }}
                >
                  All
                </button>
                <button
                  className={`btn-ghost ${mappingFilter === 'direct' ? 'active' : ''}`}
                  onClick={() => setMappingFilter('direct')}
                  style={{ fontSize: '12px', padding: '3px 8px' }}
                >
                  Direct (1:1)
                </button>
                <button
                  className={`btn-ghost ${mappingFilter === 'derived' ? 'active' : ''}`}
                  onClick={() => setMappingFilter('derived')}
                  style={{ fontSize: '12px', padding: '3px 8px' }}
                >
                  Derived (Logic)
                </button>
              </div>
              <input
                type="text"
                placeholder="Search columns, source fields…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid var(--border)',
                  background: 'var(--bg-card)',
                  color: 'var(--text)',
                  fontSize: '12.5px',
                  width: '260px',
                }}
              />
            </div>
            <div className="table-responsive-wrapper">
              <table className="enterprise-data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Target Column</th>
                    <th>Source Field</th>
                    <th>Source Table</th>
                    <th>Mapping Type</th>
                    <th>Derivation Logic</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredMappings.length > 0 ? (
                    filteredMappings.map((m, idx) => {
                      const isDirect = (m.mapping_type || '').toLowerCase() === 'direct';
                      return (
                        <tr key={idx}>
                          <td>{idx + 1}</td>
                          <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--accent-dark)' }}>
                            {m.target_column}
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)' }}>{m.source_field || '-'}</td>
                          <td style={{ fontFamily: 'var(--font-mono)', color: 'var(--link)' }}>
                            {m.source_table || '-'}
                          </td>
                          <td>
                            <span
                              className="badge"
                              style={{
                                background: isDirect ? 'rgba(16, 185, 129, 0.12)' : 'rgba(139, 92, 246, 0.12)',
                                color: isDirect ? '#10b981' : '#8b5cf6',
                                borderColor: isDirect ? 'rgba(16, 185, 129, 0.3)' : 'rgba(139, 92, 246, 0.3)',
                                fontWeight: 700,
                              }}
                            >
                              {m.mapping_type || 'Direct'}
                            </span>
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)', fontSize: '12px', color: 'var(--text)' }}>
                            {m.derivation_logic || '1:1 pass-through'}
                          </td>
                        </tr>
                      );
                    })
                  ) : (
                    <tr>
                      <td colSpan={6} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-mute)' }}>
                        No attribute mappings detected in this document.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab: Target Architecture (Data Model Objects Only) */}
        {activeFileTab === 'datamodel' && (
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '14px', flexWrap: 'wrap', gap: '8px' }}>
              <div>
                <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: 'var(--text)' }}>
                  TARGET ARCHITECTURE ({dataModel.length} Target Object{dataModel.length === 1 ? '' : 's'})
                </h3>
                <p style={{ margin: '2px 0 0', fontSize: '12px', color: 'var(--text-mute)' }}>
                  Target architecture and internal staging objects driven directly from the Data Model sheet.
                </p>
              </div>

              <input
                type="text"
                placeholder="Search process stage, target table, type, description…"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  padding: '6px 12px',
                  borderRadius: '6px',
                  border: '1px solid var(--border)',
                  background: 'var(--bg-card)',
                  color: 'var(--text)',
                  fontSize: '12.5px',
                  width: '280px',
                }}
              />
            </div>

            <div className="table-responsive-wrapper">
              <table className="enterprise-data-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Process Stage</th>
                    <th>Target Table</th>
                    <th>Table Type</th>
                    <th>Load Type</th>
                    <th>Description</th>
                    <th>Status</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {(() => {
                    let displayList = dataModel;
                    if (searchQuery.trim()) {
                      const q = searchQuery.toLowerCase();
                      displayList = displayList.filter(dm =>
                        (dm.stage || dm.layer || '').toLowerCase().includes(q) ||
                        (dm.entity_name || dm.table_name || dm.table || '').toLowerCase().includes(q) ||
                        (dm.standard_type || dm.type || '').toLowerCase().includes(q) ||
                        (dm.load_type || dm.type_of_load || '').toLowerCase().includes(q) ||
                        (dm.description || '').toLowerCase().includes(q)
                      );
                    }

                    if (displayList.length === 0) {
                      return (
                        <tr>
                          <td colSpan={8} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-mute)' }}>
                            No target architecture records found in the Data Model sheet.
                          </td>
                        </tr>
                      );
                    }

                    return displayList.map((dm, idx) => {
                      const stage = dm.stage || dm.layer || 'Target Stage';
                      const tbl = dm.entity_name || dm.table_name || dm.table || '';
                      const tblType = dm.standard_type || dm.type || (dm.reuse_rebuild ? `Standard (${dm.reuse_rebuild})` : 'Standard Table');
                      const loadType = dm.load_type || dm.type_of_load || 'Truncate and load';
                      const desc = dm.description || 'Target architecture entity';
                      const status = dm.status || 'Active';

                      return (
                        <tr
                          key={idx}
                          style={{ cursor: 'pointer' }}
                          onClick={() => setSelectedSourceTable(dm)}
                          title="Click to inspect target table columns & schema"
                        >
                          <td>{idx + 1}</td>
                          <td>
                            <span style={{ fontWeight: 600, color: 'var(--text)' }}>
                              {stage}
                            </span>
                          </td>
                          <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: '#a855f7' }}>
                            {tbl}
                          </td>
                          <td style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                            {tblType}
                          </td>
                          <td>
                            <span className="badge" style={{
                              background: String(loadType).toLowerCase().includes('append') ? 'rgba(245, 158, 11, 0.12)' : '#E8F0FE',
                              color: String(loadType).toLowerCase().includes('append') ? '#f59e0b' : 'var(--accent-dark)',
                              fontWeight: 600
                            }}>
                              {loadType}
                            </span>
                          </td>
                          <td style={{ fontSize: '12px', color: 'var(--text-secondary)', maxWidth: '320px' }}>
                            {desc}
                          </td>
                          <td>
                            <span className="badge" style={{ background: 'rgba(34, 197, 94, 0.12)', color: '#22c55e', fontWeight: 600 }}>
                              {status}
                            </span>
                          </td>
                          <td>
                            <button
                              className="btn-ghost"
                              style={{ padding: '3px 8px', fontSize: '11.5px' }}
                              onClick={(e) => {
                                e.stopPropagation();
                                setSelectedSourceTable(dm);
                              }}
                            >
                              Inspect ↗
                            </button>
                          </td>
                        </tr>
                      );
                    });
                  })()}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Tab: Buckets & KRI */}
        {activeFileTab === 'buckets' && (
          <div className="table-responsive-wrapper">
            <table className="enterprise-data-table">
              <thead>
                <tr>
                  <th>Bucket / Code</th>
                  <th>Description / State</th>
                  <th>KRI Risk Level</th>
                  <th>Operational Action</th>
                </tr>
              </thead>
              <tbody>
                {buckets.length > 0 ? (
                  buckets.map((b, idx) => (
                    <tr key={idx}>
                      <td>
                        <span className="badge" style={{ background: 'var(--navy)', color: '#fff' }}>
                          {b.bucket_id || b.code || `B${idx + 1}`}
                        </span>
                      </td>
                      <td>{b.description || b.state || '-'}</td>
                      <td>
                        <span className="badge" style={{ background: '#FEE2E2', color: '#B91C1C' }}>
                          {b.kri || 'Risk Low'}
                        </span>
                      </td>
                      <td>{b.action || '-'}</td>
                    </tr>
                  ))
                ) : (
                  <tr>
                    <td colSpan={4} style={{ textAlign: 'center', padding: '24px', color: 'var(--text-mute)' }}>
                      No reconciliation buckets detected in this document.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Tab: Discovered Sheets */}
        {activeFileTab === 'raw_sheets' && (
          <div className="table-responsive-wrapper">
            <table className="enterprise-data-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Discovered Sheet Name</th>
                  <th>Row Count</th>
                  <th>Header Count</th>
                  <th>Discovered Column Headers</th>
                </tr>
              </thead>
              <tbody>
                {sheetNames.map((name, idx) => {
                  const sInfo = rawSheets[name] || {};
                  return (
                    <tr key={idx}>
                      <td>{idx + 1}</td>
                      <td style={{ fontWeight: 700, color: 'var(--link)' }}>{name}</td>
                      <td>
                        <span className="badge" style={{ background: '#E0F2FE', color: '#0369A1' }}>
                          {sInfo.row_count || 0} rows
                        </span>
                      </td>
                      <td>{sInfo.header_count || (sInfo.original_headers || []).length} columns</td>
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: '12px' }}>
                        {(sInfo.original_headers || []).join(' · ') || 'None detected'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Tab: Synthesis & Code */}
        {activeFileTab === 'synthesis' && (
          <div style={{ background: 'var(--bg-card)', padding: '20px', borderRadius: '8px', border: '1px solid var(--border)' }}>
            <h3 style={{ margin: '0 0 8px 0', fontSize: '16px', color: 'var(--text)' }}>
              Architecture Synthesis for {activeDoc.original_name || activeDoc.filename}
            </h3>
            <p style={{ fontSize: '13px', color: 'var(--text-mute)', margin: '0 0 16px 0' }}>
              Synthesized purely from the {sheetNames.length} discovered sheets in this document without hardcoded assumptions.
            </p>

            {components.length > 0 && (
              <div style={{ marginBottom: '16px' }}>
                <h4 style={{ fontSize: '14px', color: 'var(--link)', margin: '0 0 6px 0' }}>
                  Component Interaction Architecture:
                </h4>
                <pre style={{ padding: '12px', background: 'var(--navy)', color: '#E2E8F0', borderRadius: '6px', fontSize: '12.5px', overflowX: 'auto', lineHeight: '1.6' }}>
{components.map((c, i) => `${i + 1}. [${c.component}] (${c.technology || 'Service'})\n   Consumes: ${c.input}\n   Responsibility: ${c.responsibility}\n   Produces: ${c.output}\n   Interaction: ${c.interaction}`).join('\n\n')}
                </pre>
              </div>
            )}

            {requirements.length > 0 && (
              <div>
                <h4 style={{ fontSize: '14px', color: 'var(--link)', margin: '0 0 6px 0' }}>
                  Specification Requirements:
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '8px' }}>
                  {requirements.map((r, i) => (
                    <div key={i} style={{ padding: '10px 12px', background: 'var(--bg-subtle)', borderRadius: '6px', border: '1px solid var(--border)' }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <span style={{ fontWeight: 700, color: 'var(--navy)' }}>{r.requirement}</span>
                        <span style={{ fontSize: '11px', fontWeight: 600, color: (r.priority || '').toLowerCase() === 'high' ? '#ef4444' : '#f59e0b' }}>
                          {r.priority}
                        </span>
                      </div>
                      <div style={{ fontSize: '12.5px', color: 'var(--text)', marginBottom: '4px' }}>{r.description}</div>
                      {r.acceptance_criteria && (
                        <div style={{ fontSize: '11.5px', color: 'var(--text-mute)', fontStyle: 'italic' }}>
                          Acceptance: {r.acceptance_criteria}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* ── Source Table Details Modal / Drawer (100% Document-Driven) ── */}
      {selectedSourceTable && (
        <div
          className="modal-backdrop"
          onClick={() => setSelectedSourceTable(null)}
          style={{ zIndex: 10000 }}
        >
          <div
            className="target-config-modal"
            onClick={(e) => e.stopPropagation()}
            style={{
              maxWidth: '840px',
              width: '95%',
              maxHeight: '88vh',
              display: 'flex',
              flexDirection: 'column',
              background: 'var(--bg-card)',
              borderRadius: '12px',
              boxShadow: '0 25px 60px -10px rgba(0, 0, 0, 0.7)',
              border: '1px solid var(--border)',
              overflow: 'hidden',
            }}
          >
            {/* Modal Header */}
            <div
              className="modal-header"
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '16px 20px',
                borderBottom: '1px solid var(--border)',
                background: 'var(--bg-surface)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <span style={{ fontSize: '20px' }}>🗄️</span>
                <div>
                  <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 700, color: 'var(--text)' }}>
                    Source Table Details
                  </h3>
                  <span style={{ fontSize: '12px', color: 'var(--text-mute)', fontFamily: 'var(--font-mono)' }}>
                    {selectedSourceTable.full_table_name ||
                      (selectedSourceTable.schema
                        ? `${selectedSourceTable.schema}.${selectedSourceTable.source_table_name || selectedSourceTable.table_name}`
                        : selectedSourceTable.source_table_name || selectedSourceTable.table_name)}
                  </span>
                </div>
              </div>
              <button
                onClick={() => setSelectedSourceTable(null)}
                style={{
                  background: 'none',
                  border: 'none',
                  fontSize: '20px',
                  color: 'var(--text-mute)',
                  cursor: 'pointer',
                  padding: '4px 8px',
                  borderRadius: '4px',
                }}
                title="Close (Esc)"
              >
                ✕
              </button>
            </div>

            {/* Modal Body */}
            <div
              style={{
                padding: '20px',
                overflowY: 'auto',
                display: 'flex',
                flexDirection: 'column',
                gap: '18px',
              }}
            >
              {/* Top Metadata Grid */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
                  gap: '12px',
                  padding: '16px',
                  background: 'var(--bg-subtle)',
                  borderRadius: '8px',
                  border: '1px solid var(--border)',
                }}
              >
                <div>
                  <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-mute)', fontWeight: 700 }}>
                    Source ID
                  </span>
                  <div style={{ marginTop: '3px', fontSize: '13px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--text)' }}>
                    <span className="badge" style={{ background: '#F1F5F9', color: '#1E293B', fontWeight: 700 }}>
                      {selectedSourceTable.source_id || 'SRC001'}
                    </span>
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-mute)', fontWeight: 700 }}>
                    Source / Database
                  </span>
                  <div style={{ marginTop: '3px', fontSize: '13px', fontWeight: 700, color: 'var(--text)' }}>
                    {selectedSourceTable.database || selectedSourceTable.source_name || selectedSourceTable.database_name || selectedSourceTable.source_system || selectedSourceTable.source_db || 'Default'}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-mute)', fontWeight: 700 }}>
                    Schema
                  </span>
                  <div style={{ marginTop: '3px', fontSize: '13px', fontFamily: 'var(--font-mono)' }}>
                    <span className="badge" style={{ background: '#E0E7FF', color: '#3730A3', fontWeight: 700 }}>
                      {selectedSourceTable.schema_name || selectedSourceTable.schema || selectedSourceTable.source_schema || 'public'}
                    </span>
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-mute)', fontWeight: 700 }}>
                    Table
                  </span>
                  <div style={{ marginTop: '3px', fontSize: '13px', fontWeight: 700, fontFamily: 'var(--font-mono)', color: 'var(--link)' }}>
                    {selectedSourceTable.table_name || selectedSourceTable.source_table || selectedSourceTable.source_table_name || selectedSourceTable.table || '-'}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-mute)', fontWeight: 700 }}>
                    Type of Load
                  </span>
                  <div style={{ marginTop: '3px', fontSize: '13px' }}>
                    <span className="badge" style={{ background: '#FEF3C7', color: '#92400E', fontWeight: 600 }}>
                      {selectedSourceTable.load_type || selectedSourceTable.type_of_load || 'Truncate and load'}
                    </span>
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-mute)', fontWeight: 700 }}>
                    Frequency
                  </span>
                  <div style={{ marginTop: '3px', fontSize: '13px', fontWeight: 600 }}>
                    {selectedSourceTable.frequency || selectedSourceTable.refresh_time || 'Daily'}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-mute)', fontWeight: 700 }}>
                    Schedule Time
                  </span>
                  <div style={{ marginTop: '3px', fontSize: '13px', fontFamily: 'var(--font-mono)' }}>
                    {selectedSourceTable.schedule_time || selectedSourceTable.schedule || '-'}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-mute)', fontWeight: 700 }}>
                    Active
                  </span>
                  <div style={{ marginTop: '3px', fontSize: '13px' }}>
                    <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.1)', color: '#10b981', fontWeight: 700 }}>
                      {selectedSourceTable.active || 'Yes'}
                    </span>
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-mute)', fontWeight: 700 }}>
                    Approximate End Time
                  </span>
                  <div style={{ marginTop: '3px', fontSize: '13px', color: 'var(--text-mute)' }}>
                    {selectedSourceTable.approximate_end_time || selectedSourceTable.approx_end_time || selectedSourceTable.end_time || '-'}
                  </div>
                </div>

                <div>
                  <span style={{ fontSize: '11px', textTransform: 'uppercase', color: 'var(--text-mute)', fontWeight: 700 }}>
                    Source Document Provenance
                  </span>
                  <div style={{ marginTop: '3px', fontSize: '12.5px' }}>
                    <span className="badge" style={{ background: '#F1F5F9', color: '#334155' }}>
                      Sheet: {selectedSourceTable.sheet_name || 'Source Systems'} · Row #{selectedSourceTable.source_row || selectedSourceTable.row_index || 1}
                    </span>
                  </div>
                </div>
              </div>

              {/* Related Target Attributes */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <h4 style={{ margin: 0, fontSize: '13.5px', color: 'var(--text)', fontWeight: 700 }}>
                    🎯 Related Target Attributes ({relatedTargetAttributes.length})
                  </h4>
                  <span style={{ fontSize: '11.5px', color: 'var(--text-mute)' }}>
                    Extracted from document mapping matrix
                  </span>
                </div>
                {relatedTargetAttributes.length > 0 ? (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {relatedTargetAttributes.map((attr, idx) => (
                      <span
                        key={idx}
                        className="badge"
                        style={{
                          background: 'rgba(59, 130, 246, 0.1)',
                          color: 'var(--link)',
                          borderColor: 'rgba(59, 130, 246, 0.3)',
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 600,
                        }}
                      >
                        {attr}
                      </span>
                    ))}
                  </div>
                ) : (
                  <div style={{ fontSize: '12.5px', color: 'var(--text-mute)', padding: '8px 12px', background: 'var(--bg-subtle)', borderRadius: '6px' }}>
                    No target attributes explicitly reference this table name in the mapping matrix.
                  </div>
                )}
              </div>

              {/* Related Attribute Mappings */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <h4 style={{ margin: 0, fontSize: '13.5px', color: 'var(--text)', fontWeight: 700 }}>
                    🔗 Linked Attribute Mappings ({relatedSourceMappings.length})
                  </h4>
                </div>
                {relatedSourceMappings.length > 0 ? (
                  <div className="table-responsive-wrapper" style={{ maxHeight: '220px', overflowY: 'auto' }}>
                    <table className="enterprise-data-table" style={{ fontSize: '12px' }}>
                      <thead>
                        <tr>
                          <th>#</th>
                          <th>Target Column</th>
                          <th>Source Field</th>
                          <th>Mapping Type</th>
                          <th>Derivation Logic</th>
                        </tr>
                      </thead>
                      <tbody>
                        {relatedSourceMappings.map((m, idx) => (
                          <tr key={idx}>
                            <td>{idx + 1}</td>
                            <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: 'var(--accent-dark)' }}>
                              {m.target_column}
                            </td>
                            <td style={{ fontFamily: 'var(--font-mono)' }}>{m.source_field || '-'}</td>
                            <td>
                              <span className="badge" style={{ background: (m.mapping_type || '').toLowerCase() === 'direct' ? 'rgba(16, 185, 129, 0.12)' : 'rgba(139, 92, 246, 0.12)', color: (m.mapping_type || '').toLowerCase() === 'direct' ? '#10b981' : '#8b5cf6' }}>
                                {m.mapping_type || 'Direct'}
                              </span>
                            </td>
                            <td style={{ color: 'var(--text-mute)' }}>{m.derivation_logic || '1:1 pass-through'}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : (
                  <div style={{ fontSize: '12.5px', color: 'var(--text-mute)', padding: '8px 12px', background: 'var(--bg-subtle)', borderRadius: '6px' }}>
                    No attribute mappings found specifically linked to this source dataset.
                  </div>
                )}
              </div>

              {/* Related Business & Filter Rules */}
              <div>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <h4 style={{ margin: 0, fontSize: '13.5px', color: 'var(--text)', fontWeight: 700 }}>
                    📋 Linked Business &amp; Filter Rules ({relatedSourceRules.length})
                  </h4>
                </div>
                {relatedSourceRules.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', maxHeight: '200px', overflowY: 'auto' }}>
                    {relatedSourceRules.map((r, idx) => (
                      <div
                        key={idx}
                        style={{
                          padding: '10px 12px',
                          background: 'var(--bg-subtle)',
                          borderRadius: '6px',
                          border: '1px solid var(--border)',
                          display: 'flex',
                          alignItems: 'flex-start',
                          gap: '10px',
                        }}
                      >
                        <span className="badge" style={{ background: 'var(--navy)', color: '#fff', flexShrink: 0 }}>
                          {r.rule_id || `R${idx + 1}`}
                        </span>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '2px' }}>
                            <strong style={{ fontSize: '12.5px' }}>{r.category || r.rule_type || 'Rule'}</strong>
                            <span style={{ fontSize: '11px', color: 'var(--text-mute)', fontFamily: 'var(--font-mono)' }}>
                              Stream: {r.data_stream || r.target || 'Core'}
                            </span>
                          </div>
                          <div style={{ fontSize: '12px', color: 'var(--text)' }}>
                            {r.rule_statement || r.description || r.rule_description || '-'}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div style={{ fontSize: '12.5px', color: 'var(--text-mute)', padding: '8px 12px', background: 'var(--bg-subtle)', borderRadius: '6px' }}>
                    No specific filter rules explicitly reference this dataset.
                  </div>
                )}
              </div>
            </div>

            {/* Modal Footer */}
            <div
              className="modal-footer"
              style={{
                padding: '12px 20px',
                borderTop: '1px solid var(--border)',
                background: 'var(--bg-surface)',
                display: 'flex',
                justifyContent: 'flex-end',
              }}
            >
              <button
                className="btn-ghost"
                onClick={() => setSelectedSourceTable(null)}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
