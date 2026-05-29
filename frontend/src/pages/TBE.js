import React, { useState, useEffect } from 'react';
import './Traceability.css';

const API = 'https://scm-backend-pshv.onrender.com';

const TBE = () => {
  const [summaryData, setSummaryData] = useState([]);
  const [selectedMoFlow, setSelectedMoFlow] = useState(null);
  
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
      if (!res.ok) throw new Error('Network error pulling records from pipeline.');
      
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
      setLoading(true);
      setError('');
      const res = await fetch(`${API}/traceability_report/${moString.trim()}`);
      if (!res.ok) throw new Error('Could not pull tracking sequence for this production order.');
      const json = await res.json();
      
      if (json.status === 'success') {
        setSelectedMoFlow({
          mo: json.data.mo,
          flow_data: json.data.timeline || [] 
        });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // 1. Filter using the EXACT keys from the backend: 'mo' and 'final_variant'
  const filteredSummary = summaryData.filter(item => 
    (item.mo && String(item.mo).toLowerCase().includes(search.toLowerCase())) ||
    (item.final_variant && String(item.final_variant).toLowerCase().includes(search.toLowerCase()))
  );

  // 2. Sort by 'mo' and 'final_variant'
  const sortedSummary = [...filteredSummary].sort((a, b) => {
    if (a.mo !== b.mo) {
      return (a.mo || '').localeCompare(b.mo || '');
    }
    return String(a.final_variant || '').localeCompare(String(b.final_variant || ''));
  });

  // 3. Row Span Logic for MO Column
  const getMoRowSpan = (dataArray, currentIndex) => {
    const currentMo = dataArray[currentIndex].mo;
    if (currentIndex > 0 && dataArray[currentIndex - 1].mo === currentMo) {
      return 0; 
    }
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span].mo === currentMo) {
      span++;
    }
    return span;
  };

  // 4. Row Span Logic for Channel Column
  const getChannelRowSpan = (dataArray, currentIndex) => {
    const currentMo = dataArray[currentIndex].mo;
    const currentFamily = dataArray[currentIndex].final_variant;
    
    if (currentIndex > 0 && 
        dataArray[currentIndex - 1].mo === currentMo && 
        dataArray[currentIndex - 1].final_variant === currentFamily) {
      return 0; 
    }
    
    let span = 1;
    while (
      currentIndex + span < dataArray.length && 
      dataArray[currentIndex + span].mo === currentMo &&
      dataArray[currentIndex + span].final_variant === currentFamily
    ) {
      span++;
    }
    return span;
  };

  return (
    <div className="traceability-container">
      <div className="header-section">
        <div>
          <h1>TBE Calibration Tracking</h1>
          <p className="sub-tag">
            {selectedMoFlow ? `Detailed Route Flow / Order: ${selectedMoFlow.mo}` : "Transit Buffer / Channel Synchronization Dashboard"}
          </p>
        </div>
        
        <div className="control-actions">
          {selectedMoFlow ? (
            <button className="back-btn" onClick={() => setSelectedMoFlow(null)}>
              ← Back to Summary Dashboard
            </button>
          ) : (
            <input
              className="search-box"
              placeholder="Filter by MO or Variant..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              disabled={isInitializing}
            />
          )}
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}
      
      {isInitializing && (
        <div className="initializing-box">
          <div className="spinner"></div>
          <p><strong>System Backend is warming up...</strong></p>
          <p className="sub-text">Downloading and parsing master excel configurations. Auto-refreshing in a few moments...</p>
        </div>
      )}

      {loading && !isInitializing && <div className="loading-spinner">Querying Database Pipeline Cache...</div>}

      {/* VIEW BLOCK 1: MAIN SUMMARY DASHBOARD */}
      {!loading && !isInitializing && !selectedMoFlow && (
        <div className="table-wrapper">
          <table className="trace-table">
            <thead>
              <tr className="super-header">
                <th colSpan="4" className="meta-head">Order Metadata</th>
                <th colSpan="2" className="sho-head">SHO Department</th>
                <th colSpan="2" className="tb-head">Transit Buffer</th>
                <th colSpan="3" className="ch-head">Channel Section (Combined)</th>
                <th className="meta-head">System Status</th>
              </tr>
              <tr className="sub-header">
                <th>MO Number</th>
                <th>Product Variant</th>
                <th>Target Qty</th>
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
                const moSpan = getMoRowSpan(sortedSummary, idx);
                const channelSpan = getChannelRowSpan(sortedSummary, idx);
                
                return (
                  <tr key={idx} className="data-row">
                    {/* Spanned MO Cell */}
                    {moSpan > 0 && (
                      <td rowSpan={moSpan} className="merged-mo-cell">
                        <button className="mo-link-btn" onClick={() => handleViewDetail(row.mo)}>
                          {row.mo}
                        </button>
                      </td>
                    )}

                    {/* Meta Section - Using matched keys */}
                    <td className="fw-bold">{row.final_variant || '-'}</td>
                    <td className="qty-cell">{row.qty_req && row.qty_req !== "-" ? Number(row.qty_req).toLocaleString() : '-'}</td>
                    <td className="fw-bold">{row.component_type || '-'}</td>
                    
                    {/* SHO & TB - Using matched keys */}
                    <td>{row.sho_qty ? Number(row.sho_qty).toLocaleString() : '-'}</td>
                    <td>{row.sho_in || '-'}</td>
                    
                    <td>{row.tb_qty ? Number(row.tb_qty).toLocaleString() : '-'}</td>
                    <td>{row.tb_out || '-'}</td>
                    
                    {/* Merged Channel Section - Using matched keys */}
                    {channelSpan > 0 && (
                      <>
                        <td rowSpan={channelSpan} className="merged-channel-cell fw-bold">
                          {row.ch_qty ? Number(row.ch_qty).toLocaleString() : '-'}
                        </td>
                        <td rowSpan={channelSpan} className="merged-channel-cell">{row.ch_in || '-'}</td>
                        <td rowSpan={channelSpan} className="merged-channel-cell">{row.ch_out || '-'}</td>
                      </>
                    )}
                    
                    {/* Status - Using matched keys */}
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
                    No matching TBE Tracking data located.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* VIEW BLOCK 2: TARGET DRILLDOWN DETAILED FLOW */}
      {!loading && selectedMoFlow && selectedMoFlow.flow_data && (
        <div className="table-wrapper">
          <table className="trace-table">
            <thead>
              <tr className="sub-header">
                <th>MO Reference</th>
                <th>Product Variant</th>
                <th>Ring Type</th>
                <th>SHO Qty Completed</th>
                <th>Transit Buffer Qty</th>
                <th>Total Channel Qty</th>
                <th>Execution Status</th>
              </tr>
            </thead>
            <tbody>
              {selectedMoFlow.flow_data.map((row, index) => {
                const isFirstRow = index === 0;
                return (
                  <tr key={index} className="data-row">
                    {isFirstRow && (
                      <td rowSpan={selectedMoFlow.flow_data.length} className="merged-mo-cell">
                        <strong>{selectedMoFlow.mo}</strong>
                      </td>
                    )}
                    {/* Detailed view also needs the updated keys */}
                    <td>{row.final_variant || '-'}</td>
                    <td><strong>{row.component_type || '-'}</strong></td>
                    <td>{row.sho_qty ? Number(row.sho_qty).toLocaleString() : 0}</td>
                    <td>{row.tb_qty ? Number(row.tb_qty).toLocaleString() : 0}</td>
                    <td>{row.ch_qty ? Number(row.ch_qty).toLocaleString() : 0}</td>
                    <td>
                      <span className={`status-badge ${row.status ? row.status.toLowerCase().replace(/\s+/g, '-') : 'in-process'}`}>
                        {row.status || '-'}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default TBE;
