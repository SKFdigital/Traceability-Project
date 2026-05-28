import React, { useState, useEffect } from 'react';
import './Traceability.css';

const API = 'https://scm-backend-pshv.onrender.com';

const Traceability = () => {
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
          flow_data: json.data.rows || []
        });
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // 1. Filter the data based on search
  const filteredSummary = summaryData.filter(item => 
    (item.mo && item.mo.toLowerCase().includes(search.toLowerCase())) ||
    (item.base_product && String(item.base_product).toLowerCase().includes(search.toLowerCase()))
  );

  // 2. SORT the data by MO, AND THEN by Product Variant. 
  // This ensures identical product variants sit next to each other so RowSpan works perfectly.
  const sortedSummary = [...filteredSummary].sort((a, b) => {
    if (a.mo !== b.mo) {
      return (a.mo || '').localeCompare(b.mo || '');
    }
    return String(a.base_product || '').localeCompare(String(b.base_product || ''));
  });

  // 3. Row Span Logic for MO Column
  const getMoRowSpan = (dataArray, currentIndex) => {
    const currentMo = dataArray[currentIndex].mo;
    if (currentIndex > 0 && dataArray[currentIndex - 1].mo === currentMo) {
      return 0; // Already spanned from a row above
    }
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span].mo === currentMo) {
      span++;
    }
    return span;
  };

  // 4. NEW: Row Span Logic for Channel Column (Only groups identical families inside the same MO)
  const getChannelRowSpan = (dataArray, currentIndex) => {
    const currentMo = dataArray[currentIndex].mo;
    const currentFamily = dataArray[currentIndex].base_product;
    
    // Check if previous row was exactly the same MO + Variant
    if (currentIndex > 0 && 
        dataArray[currentIndex - 1].mo === currentMo && 
        dataArray[currentIndex - 1].base_product === currentFamily) {
      return 0; // Already spanned from a row above
    }
    
    let span = 1;
    while (
      currentIndex + span < dataArray.length && 
      dataArray[currentIndex + span].mo === currentMo &&
      dataArray[currentIndex + span].base_product === currentFamily
    ) {
      span++;
    }
    return span;
  };

  return (
    <div className="traceability-container">
      <div className="header-section">
        <div>
          <h1>MO Traceability Tracking</h1>
          <p className="sub-tag">
            {selectedMoFlow ? `Detailed Route Flow / Order: ${selectedMoFlow.mo}` : "Production Order Global KPI Summary Dashboard"}
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
              placeholder="Filter Dashboard Summary..."
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
                
                {/* SHO - Out Date Removed */}
                <th>Qty</th>
                <th>In Date</th>
                
                {/* TB - In Date Removed */}
                <th>Qty</th>
                <th>Out Date</th>
                
                {/* Channel Section */}
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

                    {/* IM/OM Separation */}
                    <td className="fw-bold">{row.base_product}</td>
                    <td className="qty-cell">{row.qty_req > 0 ? Number(row.qty_req).toLocaleString() : '-'}</td>
                    <td className="fw-bold">{row.component_type}</td>
                    
                    {/* SHO & TB */}
                    <td>{row.sho_qty ? Number(row.sho_qty).toLocaleString() : '-'}</td>
                    <td>{row.sho_in || '-'}</td>
                    {/* sho_out removed */}
                    
                    <td>{row.tb_qty ? Number(row.tb_qty).toLocaleString() : '-'}</td>
                    {/* tb_in removed */}
                    <td>{row.tb_out || '-'}</td>
                    
                    {/* Merged Channel Section (Spans ONLY matching Base Products) */}
                    {channelSpan > 0 && (
                      <>
                        <td rowSpan={channelSpan} className="merged-channel-cell fw-bold">
                          {row.ch_qty ? Number(row.ch_qty).toLocaleString() : '-'}
                        </td>
                        <td rowSpan={channelSpan} className="merged-channel-cell">{row.ch_in || '-'}</td>
                        <td rowSpan={channelSpan} className="merged-channel-cell">{row.ch_out || '-'}</td>
                      </>
                    )}
                    
                    {/* Status */}
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
                    No matching Production Tracking data frames located.
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
                <th>Department / Specific Location</th>
                <th>Product / Part Sub Variant</th>
                <th>In Date</th>
                <th>Out Date</th>
                <th>Qty In</th>
                <th>Qty Out</th>
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
                    <td>{row.department}</td>
                    <td>{row.product || '-'}</td>
                    <td>{row.in_date || '-'}</td>
                    <td>{row.out_date || '-'}</td>
                    <td>{row.qty_in ? Number(row.qty_in).toLocaleString() : 0}</td>
                    <td>{row.qty_out ? Number(row.qty_out).toLocaleString() : 0}</td>
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

export default Traceability;
