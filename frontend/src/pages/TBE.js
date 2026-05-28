import React, { useState, useEffect } from 'react';
import './Traceability.css'; // Reusing your existing CSS for a consistent look

const API = 'https://scm-backend-pshv.onrender.com'; // Update this to your production backend URL later

const TBE = () => {
  const [summaryData, setSummaryData] = useState([]);
  const [selectedMoFlow, setSelectedMoFlow] = useState(null);
  
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchTbeDashboard();
  }, []);

  const fetchTbeDashboard = async () => {
    try {
      setLoading(true);
      setError('');
      // Calling the NEW tbe_all_mos endpoint
      const res = await fetch(`${API}/tbe_all_mos`);
      if (!res.ok) throw new Error('Network error pulling records from TBE pipeline.');
      
      const json = await res.json();
      
      if (json.status === 'initializing') {
        setIsInitializing(true);
        setTimeout(fetchTbeDashboard, 4000); // Retry if backend is warming up
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
      // Calling the NEW tbe_report endpoint
      const res = await fetch(`${API}/tbe_report/${moString.trim()}`);
      if (!res.ok) throw new Error('Could not pull tracking sequence for this TBE order.');
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

  // 1. Filter based on search (MO, Channel, or Base Product)
  const filteredSummary = summaryData.filter(item => 
    (item.mo && item.mo.toLowerCase().includes(search.toLowerCase())) ||
    (item.channel && String(item.channel).toLowerCase().includes(search.toLowerCase())) ||
    (item.base_product && String(item.base_product).toLowerCase().includes(search.toLowerCase()))
  );

  // 2. SORT data sequentially by MO -> Channel -> Component Type. 
  // Crucial for React rowSpan merging logic to function.
  const sortedSummary = [...filteredSummary].sort((a, b) => {
    if (a.mo !== b.mo) return (a.mo || '').localeCompare(b.mo || '');
    if (a.channel !== b.channel) return String(a.channel || '').localeCompare(String(b.channel || ''));
    return String(a.component_type || '').localeCompare(String(b.component_type || ''));
  });

  // 3. Row Span Logic for MO Column
  const getMoRowSpan = (dataArray, currentIndex) => {
    const currentMo = dataArray[currentIndex].mo;
    if (currentIndex > 0 && dataArray[currentIndex - 1].mo === currentMo) {
      return 0; // Handled by row above
    }
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span].mo === currentMo) {
      span++;
    }
    return span;
  };

  // 4. Row Span Logic for Channel Column (Spans within the same MO)
  const getChannelRowSpan = (dataArray, currentIndex) => {
    const currentMo = dataArray[currentIndex].mo;
    const currentChannel = dataArray[currentIndex].channel;
    
    if (currentIndex > 0 && 
        dataArray[currentIndex - 1].mo === currentMo && 
        dataArray[currentIndex - 1].channel === currentChannel) {
      return 0; // Handled by row above
    }
    
    let span = 1;
    while (
      currentIndex + span < dataArray.length && 
      dataArray[currentIndex + span].mo === currentMo &&
      dataArray[currentIndex + span].channel === currentChannel
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
            {selectedMoFlow ? `Detailed Channel Flow / Order: ${selectedMoFlow.mo}` : "Transit Buffer / Entry Global KPI Dashboard"}
          </p>
        </div>
        
        <div className="control-actions">
          {selectedMoFlow ? (
            <button className="back-btn" onClick={() => setSelectedMoFlow(null)}>
              ← Back to TBE Dashboard
            </button>
          ) : (
            <input
              className="search-box"
              placeholder="Filter by MO or Channel..."
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
          <p><strong>TBE Backend is warming up...</strong></p>
          <p className="sub-text">Downloading and parsing master excel configurations. Auto-refreshing...</p>
        </div>
      )}

      {loading && !isInitializing && <div className="loading-spinner">Querying Database Pipeline Cache...</div>}

      {/* VIEW BLOCK 1: MAIN TBE SUMMARY DASHBOARD */}
      {!loading && !isInitializing && !selectedMoFlow && (
        <div className="table-wrapper">
          <table className="trace-table">
            <thead>
              <tr className="super-header">
                <th colSpan="2" className="meta-head">Production Identity</th>
                <th colSpan="2" className="sho-head">Product Detail</th>
                <th colSpan="2" className="ch-head">TBE Metrics</th>
                <th colSpan="3" className="tb-head">Timeline & Status</th>
              </tr>
              <tr className="sub-header">
                <th>MO Number</th>
                <th>Channel ID</th>
                <th>Product Family</th>
                <th>Component</th>
                <th>Total Rings</th>
                <th>Total Net Weight (kg)</th>
                <th>First Scan In</th>
                <th>Last Scan Out</th>
                <th>Calibration Status</th>
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
                    
                    {/* Spanned Channel Cell */}
                    {channelSpan > 0 && (
                      <td rowSpan={channelSpan} className="merged-channel-cell fw-bold" style={{ textAlign: "center" }}>
                        CH-{(row.channel || 'N/A').toString()}
                      </td>
                    )}

                    <td className="fw-bold">{row.base_product || '-'}</td>
                    <td>{row.component_type || '-'}</td>
                    
                    <td className="qty-cell">{row.total_rings > 0 ? Number(row.total_rings).toLocaleString() : '-'}</td>
                    <td className="qty-cell">{row.total_net_weight > 0 ? Number(row.total_net_weight).toLocaleString() : '-'}</td>
                    
                    <td>{row.in_date || '-'}</td>
                    <td>{row.out_date || '-'}</td>
                    
                    <td>
                      <span className={`status-badge ${row.status ? row.status.toLowerCase().replace(/\s+/g, '-') : 'in-queue'}`}>
                        {row.status || 'In Queue'}
                      </span>
                    </td>
                  </tr>
                );
              })}
              {sortedSummary.length === 0 && (
                <tr>
                  <td colSpan="9" className="empty-state">
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
                <th>Specific Location</th>
                <th>Product Scan</th>
                <th>Date</th>
                <th>Shift</th>
                <th>Gross Weight (kg)</th>
                <th>Net Weight (kg)</th>
                <th>Ring Weight (kg)</th>
                <th>Rings Logged</th>
                <th>Audit Status</th>
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
                    <td>{row.department || '-'}</td>
                    <td>{row.product || '-'}</td>
                    <td>{row.date || '-'}</td>
                    <td>{row.shift || '-'}</td>
                    <td>{row.gross_weight ? Number(row.gross_weight).toLocaleString() : 0}</td>
                    <td>{row.net_weight ? Number(row.net_weight).toLocaleString() : 0}</td>
                    <td>{row.ring_weight ? Number(row.ring_weight).toLocaleString() : 0}</td>
                    <td>{row.rings ? Number(row.rings).toLocaleString() : 0}</td>
                    <td>
                      <span className={`status-badge ${row.status ? row.status.toLowerCase().replace(/\s+/g, '-') : 'pending'}`}>
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
