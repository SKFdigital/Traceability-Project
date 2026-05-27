import React, { useState, useEffect } from 'react';
import './Traceability.css';

const API = 'https://scm-backend-pshv.onrender.com';

const Traceability = () => {
  // Navigation & Data Management States
  const [summaryData, setSummaryData] = useState([]);
  const [selectedMoFlow, setSelectedMoFlow] = useState(null);
  
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Fetch Summary Dashboard Data automatically on Mount
  useEffect(() => {
    fetchSummaryDashboard();
  }, []);

  const fetchSummaryDashboard = async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API}/traceability_all_mos`);
      if (!res.ok) throw new Error('Failed to retrieve summary tracking records.');
      const json = await res.json();
      if (json.status === 'success') {
        setSummaryData(json.data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Trigger Detailed Flow View on click of specific MO identifier
  const handleViewDetail = async (moString) => {
    try {
      setLoading(true);
      setError('');
      const res = await fetch(`${API}/traceability_report/${moString.trim()}`);
      if (!res.ok) throw new Error('Could not pull tracking log sequence information.');
      const json = await res.json();
      if (json.status === 'success') {
        setSelectedMoFlow(json.data);
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // Filter Summary results matching Search Criteria keyword entry queries
  const filteredSummary = summaryData.filter(item => 
    item.mo.toLowerCase().includes(search.toLowerCase()) ||
    item.base_product.toLowerCase().includes(search.toLowerCase())
  );

  return (
    <div className="traceability-container">
      {/* ---------------------------------------------------
          HEADER CONTROLS ACTION SECTION
         --------------------------------------------------- */}
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
            />
          )}
        </div>
      </div>

      {error && <div className="error-box">{error}</div>}
      {loading && <div className="loading-spinner">Querying Database Pipeline Cache...</div>}

      {/* ---------------------------------------------------
          VIEW BLOCK 1: MAIN EXHAUSTIVE SUMMARY DASHBOARD
         --------------------------------------------------- */}
      {!loading && !selectedMoFlow && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr className="super-header">
                <th colSpan="3">Order Metadata</th>
                <th colSpan="3" className="sho-head">SHO Department</th>
                <th colSpan="3" className="tb-head">Transit Buffer</th>
                <th colSpan="3" className="ch-head">Channel Section</th>
                <th>System Status</th>
              </tr>
              <tr>
                <th>MO Number</th>
                <th>Type</th>
                <th>Product</th>
                <th className="sho-head">Qty</th>
                <th className="sho-head">In Date</th>
                <th className="sho-head">Out Date</th>
                <th className="tb-head">Qty</th>
                <th className="tb-head">In Date</th>
                <th className="tb-head">Out Date</th>
                <th className="ch-head">Qty</th>
                <th className="ch-head">In Date</th>
                <th className="ch-head">Out Date</th>
                <th>Tracking Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredSummary.map((row, idx) => (
                <tr key={idx}>
                  <td>
                    <button className="mo-link-btn" onClick={() => handleViewDetail(row.mo)}>
                      {row.mo}
                    </button>
                  </td>
                  <td><strong>{row.component_type}</strong></td>
                  <td>{row.base_product}</td>
                  <td>{row.sho_qty.toLocaleString()}</td>
                  <td>{row.sho_in}</td>
                  <td>{row.sho_out}</td>
                  <td>{row.tb_qty.toLocaleString()}</td>
                  <td>{row.tb_in}</td>
                  <td>{row.tb_out}</td>
                  <td>{row.ch_qty.toLocaleString()}</td>
                  <td>{row.ch_in}</td>
                  <td>{row.ch_out}</td>
                  <td>
                    <span className={`status-badge ${row.status.toLowerCase().replace(/\s+/g, '-')}`}>
                      {row.status}
                    </span>
                  </td>
                </tr>
              ))}
              {filteredSummary.length === 0 && (
                <tr>
                  <td colSpan="13" style={{ textAlign: 'center', padding: '30px' }}>
                    No matching Production Tracking data frames located.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* ---------------------------------------------------
          VIEW BLOCK 2: TARGET DRILLDOWN DETAILED FLOW
         --------------------------------------------------- */}
      {!loading && selectedMoFlow && (
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
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
                  <tr key={index}>
                    {isFirstRow && (
                      <td rowSpan={selectedMoFlow.flow_data.length} className="mo-cell">
                        <strong>{selectedMoFlow.mo}</strong>
                      </td>
                    )}
                    <td>{row.department}</td>
                    <td>{row.product || '-'}</td>
                    <td>{row.in_date || '-'}</td>
                    <td>{row.out_date || '-'}</td>
                    <td>{row.qty_in?.toLocaleString()}</td>
                    <td>{row.qty_out?.toLocaleString()}</td>
                    <td>
                      <span className={`status-badge ${row.status?.toLowerCase().replace(' ', '-')}`}>
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
