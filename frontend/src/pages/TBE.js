import React, { useState, useEffect, useRef } from 'react';
import './TBE.css';

const API = 'https://scm-backend-pshv.onrender.com';

const TBE = () => {
  const [summaryData, setSummaryData] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [error, setError] = useState('');
  
  const timerRef = useRef(null);

  useEffect(() => {
    fetchTBEDashboard();
    
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
  }, []);

  const fetchTBEDashboard = async () => {
    try {
      if (!isInitializing) setLoading(true);
      setError('');

      const res = await fetch(`${API}/tbe_all_mos`);
      if (!res.ok) throw new Error('Network error pulling records from pipeline.');
      
      const json = await res.json();
      
      if (json.status === 'initializing') {
        setIsInitializing(true);
        setSummaryData([]);
        timerRef.current = setTimeout(fetchTBEDashboard, 4000);
      } else if (json.status === 'success') {
        setIsInitializing(false);
        setSummaryData(json.data || []);
      } else if (json.status === 'failed') {
        setIsInitializing(false);
        setError(json.message || 'The data pipeline extraction failed.');
        setSummaryData([]);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // 1. Dynamic Filtering (Filters by Channel Reference or Product Family)
  const filteredSummary = summaryData.filter(item => 
    (item.channel_ref && String(item.channel_ref).toLowerCase().includes(search.toLowerCase())) ||
    (item.product_variant && String(item.product_variant).toLowerCase().includes(search.toLowerCase()))
  );

  // 2. Multi-tier Sorting (Ensures layout stability for merging rows)
  const sortedSummary = [...filteredSummary].sort((a, b) => {
    if (a.channel_ref !== b.channel_ref) {
      return String(a.channel_ref || '').localeCompare(String(b.channel_ref || ''));
    }
    if (a.product_variant !== b.product_variant) {
      return String(a.product_variant || '').localeCompare(String(b.product_variant || ''));
    }
    return String(a.ring_type || '').localeCompare(String(b.ring_type || ''));
  });

  // 3. Row Span Generation: Channel Column
  const getChannelRowSpan = (dataArray, currentIndex) => {
    const currentRef = dataArray[currentIndex].channel_ref;
    if (!currentRef) return 1; 
    if (currentIndex > 0 && dataArray[currentIndex - 1].channel_ref === currentRef) {
      return 0; 
    }
    let span = 1;
    while (currentIndex + span < dataArray.length && dataArray[currentIndex + span].channel_ref === currentRef) {
      span++;
    }
    return span;
  };

  // 4. Row Span Generation: Channel Data Block (Qty, In, Out)
  const getBlockRowSpan = (dataArray, currentIndex) => {
    const currentRef = dataArray[currentIndex].channel_ref;
    const currentFamily = dataArray[currentIndex].product_variant;
    
    if (currentIndex > 0 && 
        dataArray[currentIndex - 1].channel_ref === currentRef &&
        dataArray[currentIndex - 1].product_variant === currentFamily) {
      return 0; 
    }
    
    let span = 1;
    while (
      currentIndex + span < dataArray.length && 
      dataArray[currentIndex + span].channel_ref === currentRef &&
      dataArray[currentIndex + span].product_variant === currentFamily
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
          <p className="sub-tag">7-Day Run Sequence Matrix</p>
        </div>
        
        <div className="control-actions">
          <input
            className="search-box"
            placeholder="Filter by Channel or Family..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            disabled={isInitializing}
          />
        </div>
      </div>

      {error && <div className="error-box">⚠️ {error}</div>}
      
      {isInitializing && (
        <div className="initializing-box">
          <div className="spinner"></div>
          <p><strong>Preparing Data Pipelines...</strong></p>
          <p className="sub-text">Grouping temporal sequences and running 7-day batch analysis...</p>
        </div>
      )}

      {loading && !isInitializing && <div className="loading-spinner">Synchronizing pipeline data stream...</div>}

      {!loading && !isInitializing && (
        <div className="table-wrapper">
          <table className="trace-table">
            <thead>
              <tr className="super-header">
                <th colSpan="3" className="meta-head">Production Metadata</th>
                <th colSpan="2" className="sho-head">SHO Department</th>
                <th colSpan="2" className="tb-head">Transit Buffer</th>
                <th colSpan="3" className="ch-head">Channel Section (Combined)</th>
                <th className="meta-head">System Status</th>
              </tr>
              <tr className="sub-header">
                <th>Channel Ref</th>
                <th>Product Variant</th>
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
                const blockSpan = getBlockRowSpan(sortedSummary, idx);
                
                const rowKey = `${row.channel_ref || 'null'}-${row.product_variant || 'null'}-${row.ring_type || 'null'}-${idx}`;
                
                return (
                  <tr key={rowKey} className="data-row">
                    {channelSpan > 0 && (
                      <td rowSpan={channelSpan} className="merged-mo-cell fw-bold">
                        {row.channel_ref || '-'}
                      </td>
                    )}

                    <td className="fw-bold text-primary">{row.product_variant}</td>
                    <td className="fw-bold">{row.ring_type}</td>
                    
                    <td>{row.sho_qty ? Number(row.sho_qty).toLocaleString() : '-'}</td>
                    <td>{row.sho_in || '-'}</td>
                    
                    <td>{row.tb_qty ? Number(row.tb_qty).toLocaleString() : '-'}</td>
                    <td>{row.tb_out || '-'}</td>
                    
                    {blockSpan > 0 && (
                      <>
                        <td rowSpan={blockSpan} className="merged-channel-cell fw-bold">
                          {row.ch_qty ? Number(row.ch_qty).toLocaleString() : '0'}
                        </td>
                        <td rowSpan={blockSpan} className="merged-channel-cell">{row.ch_in || '-'}</td>
                        <td rowSpan={blockSpan} className="merged-channel-cell">{row.ch_out || '-'}</td>
                      </>
                    )}
                    
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
                  <td colSpan="11" className="empty-state">
                    No matching TBE Tracking data located. Verify your source sheets are populated.
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
