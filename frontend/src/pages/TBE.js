import React, { useState, useEffect } from 'react';
import './TBE.css'; // Assuming same CSS file name, or rename to TBE.css

const API = 'https://scm-backend-pshv.onrender.com';

const TBE = () => {
  const [summaryData, setSummaryData] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchTBEDashboard();
  }, []);

  const fetchTBEDashboard = async () => {
    try {
      setLoading(true);
      setError('');
      // Using the new endpoint
      const res = await fetch(`${API}/tbe_all_mos`);
      if (!res.ok) throw new Error('Network error pulling records from pipeline.');
      
      const json = await res.json();
      
      if (json.status === 'initializing') {
        setIsInitializing(true);
        setTimeout(fetchTBEDashboard, 4000);
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

  // 1. Filter Data
  const filteredSummary = summaryData.filter(item => 
    (item.mo_number && item.mo_number.toLowerCase().includes(search.toLowerCase())) ||
    (item.product_variant && String(item.product_variant).toLowerCase().includes(search.toLowerCase()))
  );

  // 2. Sort Data ensuring RowSpans group perfectly by Family
  const sortedSummary = [...filteredSummary].sort((a, b) => {
    if (a.mo_number !== b.mo_number) {
      return (a.mo_number || '').localeCompare(b.mo_number || '');
    }
    return String(a.product_variant || '').localeCompare(String(b.product_variant || ''));
  });

  // 3. Row Span Logic for MO Column
  const getMoRowSpan = (dataArray, currentIndex) => {
    const currentMo = dataArray[currentIndex].mo_number;
    if (!currentMo) return 1; // Don't span empty MOs
    if (currentIndex > 0 && dataArray[currentIndex - 1].mo_number === currentMo) {
      return 0; 
    }
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span].mo_number === currentMo) {
      span++;
    }
    return span;
  };

  // 4. Row Span Logic for Channel Data (Groups IM/OM of the exact same family and channel)
  const getChannelRowSpan = (dataArray, currentIndex) => {
    const currentFamily = dataArray[currentIndex].product_variant;
    const currentChannel = dataArray[currentIndex].channel_ref;
    
    // Check if previous row was exactly the same Family + Channel
    if (currentIndex > 0 && 
        dataArray[currentIndex - 1].product_variant === currentFamily &&
        dataArray[currentIndex - 1].channel_ref === currentChannel) {
      return 0; 
    }
    
    let span = 1;
    while (
      currentIndex + span < dataArray.length && 
      dataArray[currentIndex + span].product_variant === currentFamily &&
      dataArray[currentIndex + span].channel_ref === currentChannel
    ) {
      span++;
    }
    return span;
  };

  return (
    <div className="traceability-container">
      <div className="header-section">
        <div>
          <h1>TBE Transit Buffer Tracking</h1>
          <p className="sub-tag">Priority Base: Ring Wt Transit Buffer</p>
        </div>
        
        <div className="control-actions">
          <input
            className="search-box"
            placeholder="Filter by MO or Family..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={isInitializing}
          />
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}
      
      {isInitializing && (
        <div className="initializing-box">
          <div className="spinner"></div>
          <p><strong>System Backend is warming up...</strong></p>
          <p className="sub-text">Parsing Transit Buffers. Auto-refreshing shortly...</p>
        </div>
      )}

      {loading && !isInitializing && <div className="loading-spinner">Querying Database Pipeline Cache...</div>}

      {!loading && !isInitializing && (
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
                
                {/* SHO */}
                <th>Qty</th>
                <th>In Date</th>
                
                {/* Transit Buffer */}
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
                    
                    {/* MO Cell */}
                    {moSpan > 0 && (
                      <td rowSpan={moSpan} className="merged-mo-cell fw-bold">
                        {row.mo_number || '-'}
                      </td>
                    )}

                    <td className="fw-bold text-primary">{row.product_variant}</td>
                    <td className="qty-cell">{row.target_qty > 0 ? Number(row.target_qty).toLocaleString() : ''}</td>
                    <td className="fw-bold">{row.ring_type}</td>
                    
                    {/* SHO & TB */}
                    <td>{row.sho_qty ? Number(row.sho_qty).toLocaleString() : ''}</td>
                    <td>{row.sho_in}</td>
                    
                    <td>{row.tb_qty ? Number(row.tb_qty).toLocaleString() : ''}</td>
                    <td>{row.tb_out}</td>
                    
                    {/* Merged Channel Section: Spans Matching Base Products */}
                    {channelSpan > 0 && (
                      <>
                        <td rowSpan={channelSpan} className="merged-channel-cell fw-bold">
                          {row.ch_qty !== "" ? Number(row.ch_qty).toLocaleString() : ''}
                        </td>
                        <td rowSpan={channelSpan} className="merged-channel-cell">{row.ch_in}</td>
                        <td rowSpan={channelSpan} className="merged-channel-cell">{row.ch_out}</td>
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
                    No matching TBE Tracking data located.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default TBE;
