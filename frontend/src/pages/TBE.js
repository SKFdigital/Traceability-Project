import React, { useState, useEffect, useRef } from 'react';
import './TBE.css';

const API = 'https://scm-backend-pshv.onrender.com';

const TBE = () => {
  const [summaryData, setSummaryData] = useState([]);
  const [search, setSearch] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [loading, setLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [error, setError] = useState('');
  
  // Drilldown Breakout States
  const [selectedFamily, setSelectedFamily] = useState(null); 
  const [detailData, setDetailData] = useState([]);
  const [detailLoading, setDetailLoading] = useState(false);

  const timerRef = useRef(null);

  useEffect(() => {
    fetchTBEDashboard();
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  useEffect(() => {
    if (!selectedFamily) {
      setDetailData([]);
      return;
    }

    const fetchVariantDetails = async () => {
      try {
        setDetailLoading(true);
        const url = `${API}/tbe_variant_details?ch=${encodeURIComponent(selectedFamily.ch)}&fam=${encodeURIComponent(selectedFamily.fam)}`;
        const res = await fetch(url);
        if (!res.ok) throw new Error("Could not retrieve variant sequential logs.");
        const json = await res.json();
        setDetailData(json.data || []);
      } catch (err) {
        console.error(err.message);
      } finally {
        setDetailLoading(false);
      }
    };

    fetchVariantDetails();
  }, [selectedFamily]);

  const fetchTBEDashboard = async () => {
    try {
      if (!isInitializing) setLoading(true);
      setError('');

      const res = await fetch(`${API}/tbe_all_mos`);
      if (!res.ok) throw new Error(`Server returned status code: ${res.status}`);
      
      const json = await res.json();
      
      if (json.status === 'initializing') {
        setIsInitializing(true);
        setSummaryData([]);
        if (timerRef.current) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(fetchTBEDashboard, 4000);
      } else {
        setIsInitializing(false);
        setSummaryData(json.data || []);
      }
    } catch (err) {
      setIsInitializing(false);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const filteredSummary = summaryData.filter(item => {
    const matchesSearch = 
      (item.channel_ref && String(item.channel_ref).toLowerCase().includes(search.toLowerCase())) ||
      (item.product_variant && String(item.product_variant).toLowerCase().includes(search.toLowerCase())) ||
      (item.mo_ref && String(item.mo_ref).toLowerCase().includes(search.toLowerCase()));

    let matchesDate = true;
    if (startDate || endDate) {
      const dates = [item.sho_in, item.tb_out, item.ch_in, item.ch_out].filter(d => d && d !== '-');
      
      if (dates.length === 0) {
        matchesDate = false; 
      } else {
        matchesDate = dates.some(d => {
          const dateObj = new Date(d);
          const s = startDate ? new Date(startDate) : new Date('1900-01-01');
          const e = endDate ? new Date(endDate) : new Date('2100-01-01');
          return dateObj >= s && dateObj <= e;
        });
      }
    }

    return matchesSearch && matchesDate;
  });

  const sortedSummary = [...filteredSummary].sort((a, b) => {
    if (a.channel_ref !== b.channel_ref) {
      return String(a.channel_ref || '').localeCompare(String(b.channel_ref || ''));
    }
    if (a.product_variant !== b.product_variant) {
      return String(a.product_variant || '').localeCompare(String(b.product_variant || ''));
    }
    return String(a.ring_type || '').localeCompare(String(b.ring_type || ''));
  });

  const getChannelRowSpan = (dataArray, currentIndex) => {
    const currentRef = dataArray[currentIndex].channel_ref;
    if (!currentRef) return 1;
    if (currentIndex > 0 && dataArray[currentIndex - 1].channel_ref === currentRef) return 0; 
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span].channel_ref === currentRef) {
      span++;
    }
    return span;
  };

  const getFamilyRowSpan = (dataArray, currentIndex) => {
    const currentRef = dataArray[currentIndex].channel_ref;
    const currentFam = dataArray[currentIndex].product_variant;
    if (!currentRef || !currentFam) return 1;
    
    if (currentIndex > 0 && 
        dataArray[currentIndex - 1].channel_ref === currentRef &&
        dataArray[currentIndex - 1].product_variant === currentFam) {
      return 0; 
    }
    let span = 1;
    while (currentIndex + span < dataArray.length && 
           dataArray[currentIndex + span].channel_ref === currentRef &&
           dataArray[currentIndex + span].product_variant === currentFam) {
      span++;
    }
    return span;
  };

  return (
    <div className="traceability-container">
      <div className="header-section">
        <div>
          <h1>TBE Tracking Log</h1>
          <p className="sub-tag">Synchronized Channel & Ring Family Sequencing Matrices</p>
        </div>
        
        <div className="control-actions">
          <input 
            type="date" 
            className="search-box" 
            title="Start Date"
            value={startDate} 
            onChange={(e) => setStartDate(e.target.value)} 
          />
          <span style={{margin: '0 5px', color: '#64748b'}}>to</span>
          <input 
            type="date" 
            className="search-box" 
            title="End Date"
            value={endDate} 
            onChange={(e) => setEndDate(e.target.value)} 
          />

          <button className="back-btn" style={{margin: '0 10px'}} onClick={fetchTBEDashboard} disabled={loading}>
            {loading ? 'Refreshing...' : '🔄 Reload'}
          </button>
          
          <input
            className="search-box"
            placeholder="Search Channel, MO, or Family..."
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
          <p><strong>Compiling Remote Workbook Matrix Caches...</strong></p>
        </div>
      )}

      {loading && !isInitializing && <div className="loading-spinner">Querying server memory buffer...</div>}

      {!loading && !isInitializing && (
        <div className="table-wrapper">
          <table className="trace-table">
            <thead>
              <tr className="super-header">
                <th colSpan="4" className="meta-head">Connection Mapping</th>
                <th colSpan="2" className="sho-head">SHO Department (Split)</th>
                <th colSpan="2" className="tb-head">Transit Buffer (Split)</th>
                <th colSpan="3" className="ch-head">Channel Section (Combined Rollup)</th>
                <th className="meta-head">Status Tracker</th>
              </tr>
              <tr className="sub-header">
                <th>Channel Ref</th>
                <th>MO</th>
                <th>Ring Family</th>
                <th>Ring Type</th>
                <th>Qty</th>
                <th>In Date</th>
                <th>Qty</th>
                <th>Out Date</th>
                <th>Qty</th>
                <th>In Date</th>
                <th>Out Date</th>
                <th>Tracking Status</th>
              </tr>
            </thead>
            <tbody>
              {sortedSummary.map((row, idx) => {
                const channelSpan = getChannelRowSpan(sortedSummary, idx);
                const familySpan = getFamilyRowSpan(sortedSummary, idx);
                const uniqueKey = `${row.channel_ref || 'b'}-${row.product_variant || 'b'}-${row.ring_type || 'b'}-${idx}`;
                
                return (
                  <tr key={uniqueKey} className="data-row">
                    {/* Channel Column */}
                    {channelSpan > 0 && (
                      <td rowSpan={channelSpan} className="merged-mo-cell fw-bold">
                        {row.channel_ref || '-'}
                      </td>
                    )}
                    
                    {/* MO Column */}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-mo-cell text-muted" style={{fontSize: '0.9em'}}>
                        {row.mo_ref || '-'}
                      </td>
                    )}

                    {/* Ring Family Column - Interactive Drilldown Component */}
                    {familySpan > 0 && (
                      <td 
                        rowSpan={familySpan} 
                        className="fw-bold text-primary clickable-family-cell"
                        title="Click to view full variant routing entries"
                        onClick={() => setSelectedFamily({ ch: row.channel_ref, fam: row.product_variant })}
                      >
                        {row.product_variant}
                      </td>
                    )}
                    
                    {/* Ring Type Column */}
                    <td className="fw-bold">{row.ring_type}</td>
                    
                    {/* SHO Split */}
                    <td>{row.sho_qty ? Number(row.sho_qty).toLocaleString() : '0'}</td>
                    <td>{row.sho_in || '-'}</td>
                    
                    {/* TB Split */}
                    <td>{row.tb_qty ? Number(row.tb_qty).toLocaleString() : '0'}</td>
                    <td>{row.tb_out || '-'}</td>
                    
                    {/* Channel Section */}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-channel-cell fw-bold text-success">
                        {row.ch_qty ? Number(row.ch_qty).toLocaleString() : '0'}
                      </td>
                    )}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-channel-cell">{row.ch_in || '-'}</td>
                    )}
                    {familySpan > 0 && (
                      <td rowSpan={familySpan} className="merged-channel-cell">{row.ch_out || '-'}</td>
                    )}
                    
                    {/* Status Tracker */}
                    <td>
                      <span className={`status-badge ${row.status ? row.status.toLowerCase().replace(/\s+/g, '-') : 'in-process'}`}>
                        {row.status || 'In Process'}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {sortedSummary.length === 0 && (
                <tr>
                  <td colSpan="12" className="empty-state">
                    No records found matching the current search criteria or date range.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Redesigned Stacked Layout Detail Breakdown Modal */}
      {selectedFamily && (
        <div className="modal-overlay" onClick={() => setSelectedFamily(null)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <div>
                <h3>Variant Specific Location Breakdown</h3>
                <p className="modal-subheading">Family Scope: <strong>{selectedFamily.fam}</strong></p>
              </div>
              <button className="close-modal-btn" onClick={() => setSelectedFamily(null)}>&times;</button>
            </div>
            <div className="modal-body">
              {detailLoading ? (
                <div className="detail-loading-box">
                  <div className="spinner"></div>
                  <p>Querying breakdown registries...</p>
                </div>
              ) : detailData.length === 0 ? (
                <div className="empty-state">No independent deployment logs located for this variant structure.</div>
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
                      {detailData.map((vRow, vIdx) => (
                        <tr key={vIdx} className="modal-data-row">
                          <td className="text-start text-muted" style={{fontSize: '0.95em'}}>{vRow.mo_ref}</td>
                          <td className="text-start">
                            <span className={`dept-tag ${vRow.department.toLowerCase().replace(/\s+/g, '-')}`}>
                              {vRow.department}
                            </span>
                          </td>
                          <td className="text-start fw-bold" style={{color: '#0f172a'}}>{vRow.variant}</td>
                          <td>{vRow.in_date}</td>
                          <td>{vRow.out_date}</td>
                          <td className="fw-bold">{Number(vRow.qty).toLocaleString()}</td>
                          <td>
                            <span className="execution-status-dot">{vRow.status}</span>
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

export default TBE;
