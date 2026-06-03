import React, { useState, useEffect } from 'react';
import './Traceability.css'; 

const API = 'https://scm-backend-pshv.onrender.com';

const Traceability = () => {
  const [summaryData, setSummaryData] = useState([]);
  
  // Drilldown Breakout States (TBE Sequential Log Style)
  const [selectedMoFlow, setSelectedMoFlow] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchSummaryDashboard();
  }, []);

  const fetchSummaryDashboard = async () => {
    try {
      setLoading(true);
      setError('');
      const res = await fetch(`${API}/traceability_all_mos`);
      if (!res.ok) throw new Error('Network error pulling records.');
      const json = await res.json();
      
      if (json.status === 'initializing') {
        setIsInitializing(true);
        setTimeout(fetchSummaryDashboard, 4000);
      } else if (json.status === 'success') {
        setIsInitializing(false);
        setSummaryData(json.data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleViewDetail = async (moString) => {
    try {
      // Open modal frame immediately and show loading spinner inside it
      setSelectedMoFlow({ mo: moString, flow_data: [] }); 
      setDetailLoading(true);
      
      const res = await fetch(`${API}/traceability_report/${moString.trim()}`);
      if (!res.ok) throw new Error('Could not pull variant flow.');
      const json = await res.json();
      
      if (json.status === 'success') {
        setSelectedMoFlow({
          mo: json.data.mo || moString,
          flow_data: json.data.rows || [] // Expecting sequential department flow here
        });
      }
    } catch (err) {
      console.error(err.message);
    } finally {
      setDetailLoading(false);
    }
  };

  const filteredSummary = summaryData.filter(item => 
    (item.mo && String(item.mo).toLowerCase().includes(search.toLowerCase())) ||
    (item.base_product && String(item.base_product).toLowerCase().includes(search.toLowerCase()))
  );

  const getRowSpan = (dataArray, currentIndex, keyField) => {
    const currentVal = dataArray[currentIndex][keyField];
    if (currentIndex > 0 && dataArray[currentIndex - 1][keyField] === currentVal) {
      return 0; 
    }
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span][keyField] === currentVal) {
      span++;
    }
    return span;
  };

  return (
    <div className="traceability-container">
      <div className="header-section">
        <div>
          <h1>MO Traceability Tracking</h1>
          <p className="sub-tag">Global Order Summary by Family</p>
        </div>
        
        <div className="control-actions">
          <button className="back-btn" style={{margin: '0 10px'}} onClick={fetchSummaryDashboard} disabled={loading}>
            {loading ? 'Refreshing...' : '🔄 Reload'}
          </button>

          <input
            className="search-box"
            placeholder="Search MO or Family..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={isInitializing}
          />
        </div>
      </div>

      {error && <div className="error-box">⚠️ Network Error: {error}</div>}
      
      {isInitializing && (
        <div className="initializing-box">
          <div className="spinner"></div>
          <p><strong>System Backend is warming up...</strong></p>
        </div>
      )}

      {/* MAIN DASHBOARD */}
      {!loading && !isInitializing && (
        <div className="table-wrapper">
          <table className="trace-table">
            <thead>
              {/* Fixed colSpan Math: 4 + 2 + 2 + 2 + 1 = 11 */}
              <tr className="super-header">
                <th colSpan="4" className="meta-head">Order Details</th>
                <th colSpan="2" className="sho-head">SHO Target</th>
                <th colSpan="2" className="tb-head">Transit Buffer</th>
                <th colSpan="2" className="ch-head">Channel Section</th>
                <th className="meta-head">Overall Status</th>
              </tr>
              {/* Exactly 11 headers underneath */}
              <tr className="sub-header">
                <th>MO Number</th>
                <th>Family / Base Product</th>
                <th>Component</th>
                <th>Target Qty</th>
                <th>SHO Qty</th>
                <th>Date</th>
                <th>TB Qty</th>
                <th>Date</th>
                <th>Chan Qty</th>
                <th>Date</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredSummary.map((row, idx) => {
                const moSpan = getRowSpan(filteredSummary, idx, 'mo');
                return (
                  <tr key={idx} className="data-row">
                    {/* Interactive Clickable MO Cell */}
                    {moSpan > 0 && (
                      <td 
                        rowSpan={moSpan} 
                        className="merged-mo-cell fw-bold text-primary clickable-family-cell"
                        title="Click to view full variant breakdown"
                        style={{ cursor: 'pointer', color: '#0284c7' }}
                        onClick={() => handleViewDetail(row.mo)}
                      >
                        {row.mo}
                      </td>
                    )}
                    {moSpan > 0 && (
                      <td rowSpan={moSpan} className="merged-mo-cell fw-bold">
                        {row.base_product}
                      </td>
                    )}
                    
                    {/* IM/OM Split Rows (These loop independently of moSpan) */}
                    <td style={{ fontWeight: 600, color: row.component === 'IM' ? '#0369a1' : '#b45309' }}>
                      {row.component}
                    </td>
                    <td className="qty-cell">{row.qty_req > 0 ? Number(row.qty_req).toLocaleString() : '-'}</td>
                    <td>{row.sho_qty ? Number(row.sho_qty).toLocaleString() : '-'}</td>
                    <td>{row.sho_date || '-'}</td>
                    <td>{row.tb_qty ? Number(row.tb_qty).toLocaleString() : '-'}</td>
                    <td>{row.tb_date || '-'}</td>
                    
                    {/* Re-Merged Channel Output */}
                    {moSpan > 0 && (
                      <td rowSpan={moSpan} className="merged-channel-cell fw-bold text-success">
                        {row.ch_qty ? Number(row.ch_qty).toLocaleString() : '-'}
                      </td>
                    )}
                    {moSpan > 0 && (
                      <td rowSpan={moSpan} className="merged-channel-cell">{row.ch_date || '-'}</td>
                    )}
                    {moSpan > 0 && (
                      <td rowSpan={moSpan} className="merged-channel-cell">
                        <span className={`status-badge ${row.status ? row.status.toLowerCase().replace(/\s+/g, '-') : ''}`}>
                          {row.status || 'In Process'}
                        </span>
                      </td>
                    )}
                  </tr>
                );
              })}
              {filteredSummary.length === 0 && (
                <tr>
                  <td colSpan="11" className="empty-state">
                    No records found matching the current search criteria.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* DRILLDOWN MODAL - EXACT TBE SEQUENTIAL FORMAT */}
      {selectedMoFlow && (
        <div className="modal-overlay" onClick={() => setSelectedMoFlow(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3>Variant Specific Location Breakdown</h3>
                <p className="modal-subheading">MO Scope: <strong>{selectedMoFlow.mo}</strong></p>
              </div>
              <button className="close-modal-btn" onClick={() => setSelectedMoFlow(null)}>&times;</button>
            </div>
            <div className="modal-body">
              {detailLoading ? (
                <div className="detail-loading-box">
                  <div className="spinner"></div>
                  <p>Querying breakdown registries...</p>
                </div>
              ) : selectedMoFlow.flow_data.length === 0 ? (
                <div className="empty-state">No independent deployment logs located for this MO structure.</div>
              ) : (
                <div className="modal-table-wrapper">
                  <table className="detail-variant-table">
                    <thead>
                      <tr>
                        <th style={{textAlign: 'left'}}>MO / Channel Reference</th>
                        <th style={{textAlign: 'left'}}>Department / Specific Location</th>
                        <th style={{textAlign: 'left'}}>Product / Part Sub Variant</th>
                        <th>In Date</th>
                        <th>Out Date</th>
                        <th>Qty</th>
                        <th>Execution Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {selectedMoFlow.flow_data.map((vRow, vIdx) => (
                        <tr key={vIdx} className="modal-data-row">
                          <td className="text-start text-muted" style={{fontSize: '0.95em'}}>{vRow.mo_ref || selectedMoFlow.mo}</td>
                          <td className="text-start">
                            <span className={`dept-tag ${vRow.department ? vRow.department.toLowerCase().replace(/\s+/g, '-') : ''}`}>
                              {vRow.department || '-'}
                            </span>
                          </td>
                          <td className="text-start fw-bold" style={{color: '#0f172a'}}>{vRow.variant || '-'}</td>
                          <td>{vRow.in_date || '-'}</td>
                          <td>{vRow.out_date || '-'}</td>
                          <td className="fw-bold">{vRow.qty ? Number(vRow.qty).toLocaleString() : '0'}</td>
                          <td>
                            <span className="execution-status-dot">{vRow.status || '-'}</span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default Traceability;
