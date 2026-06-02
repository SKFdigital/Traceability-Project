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
      setLoading(true);
      setError('');
      const res = await fetch(`${API}/traceability_report/${moString.trim()}`);
      if (!res.ok) throw new Error('Could not pull variant flow.');
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

  const filteredSummary = summaryData.filter(item => 
    (item.mo && item.mo.toLowerCase().includes(search.toLowerCase())) ||
    (item.base_product && String(item.base_product).toLowerCase().includes(search.toLowerCase()))
  );

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

  return (
    <div className="traceability-container">
      <div className="header-section">
        <div>
          <h1>MO Traceability Tracking</h1>
          <p className="sub-tag">
            {selectedMoFlow ? `Variant Breakdown / MO: ${selectedMoFlow.mo}` : "Global Order Summary by Family"}
          </p>
        </div>
        
        <div className="control-actions">
          {selectedMoFlow ? (
            <button className="back-btn" onClick={() => setSelectedMoFlow(null)}>
              ← Back to Summary
            </button>
          ) : (
            <input
              className="search-box"
              placeholder="Search MO or Family..."
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
        </div>
      )}

      {/* MAIN DASHBOARD: GROUPED BY FAMILY (BASE PRODUCT) */}
      {!loading && !isInitializing && !selectedMoFlow && (
        <div className="table-wrapper">
          <table className="trace-table">
            <thead>
              <tr className="super-header">
                <th colSpan="3" className="meta-head">Order Details</th>
                <th colSpan="2" className="sho-head">SHO Target</th>
                <th colSpan="2" className="tb-head">Transit Buffer</th>
                <th colSpan="2" className="ch-head">Channel Section</th>
                <th className="meta-head">Overall Status</th>
              </tr>
              <tr className="sub-header">
                <th>MO Number</th>
                <th>Family (Base Product)</th>
                <th>Target Qty</th>
                <th>Qty</th>
                <th>In Date</th>
                <th>Qty</th>
                <th>Out Date</th>
                <th>Qty</th>
                <th>Out Date</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredSummary.map((row, idx) => {
                const moSpan = getMoRowSpan(filteredSummary, idx);
                return (
                  <tr key={idx} className="data-row">
                    {moSpan > 0 && (
                      <td rowSpan={moSpan} className="merged-mo-cell">
                        <button className="mo-link-btn" onClick={() => handleViewDetail(row.mo)}>
                          {row.mo}
                        </button>
                      </td>
                    )}
                    <td className="fw-bold">{row.base_product}</td>
                    <td className="qty-cell">{row.qty_req > 0 ? Number(row.qty_req).toLocaleString() : '-'}</td>
                    
                    <td>{row.sho_qty ? Number(row.sho_qty).toLocaleString() : '-'}</td>
                    <td>{row.sho_date}</td>
                    
                    <td>{row.tb_qty ? Number(row.tb_qty).toLocaleString() : '-'}</td>
                    <td>{row.tb_date}</td>
                    
                    <td className="fw-bold">{row.ch_qty ? Number(row.ch_qty).toLocaleString() : '-'}</td>
                    <td>{row.ch_date}</td>
                    
                    <td>
                      <span className={`status-badge ${row.status.toLowerCase().replace(/\s+/g, '-')}`}>
                        {row.status}
                      </span>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* DRILLDOWN: EXACT TBE FORMAT BY FINAL VARIANT */}
      {!loading && selectedMoFlow && (
        <div className="table-wrapper">
          <table className="trace-table">
            <thead>
              <tr className="super-header">
                <th colSpan="2" className="meta-head">Variant Details</th>
                <th colSpan="2" className="sho-head">SHO Dept</th>
                <th colSpan="2" className="tb-head">Transit Buffer</th>
                <th colSpan="2" className="ch-head">Channel Processing</th>
                <th className="meta-head">Final Status</th>
              </tr>
              <tr className="sub-header">
                <th>Final Variant</th>
                <th>Req Qty</th>
                <th>SHO Qty</th>
                <th>Last Date</th>
                <th>TB Qty</th>
                <th>Last Date</th>
                <th>Chan Qty</th>
                <th>Last Date</th>
                <th>Status</th>
              </tr>
            </thead>
            <tbody>
              {selectedMoFlow.flow_data.map((row, index) => (
                <tr key={index} className="data-row">
                  <td className="fw-bold" style={{ color: '#0284c7' }}>{row.variant}</td>
                  <td className="qty-cell">{row.qty_req > 0 ? Number(row.qty_req).toLocaleString() : '-'}</td>
                  
                  <td>{row.sho_qty > 0 ? Number(row.sho_qty).toLocaleString() : '-'}</td>
                  <td>{row.sho_date}</td>
                  
                  <td>{row.tb_qty > 0 ? Number(row.tb_qty).toLocaleString() : '-'}</td>
                  <td>{row.tb_date}</td>
                  
                  <td className="fw-bold">{row.ch_qty > 0 ? Number(row.ch_qty).toLocaleString() : '-'}</td>
                  <td>{row.ch_date}</td>
                  
                  <td>
                    <span className={`status-badge ${row.status.toLowerCase().replace(/\s+/g, '-')}`}>
                      {row.status}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default Traceability;
