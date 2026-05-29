import React, { useState, useEffect } from 'react';

const TBE = () => {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');

  // Fetch data from the FastAPI backend
  useEffect(() => {
    const fetchData = async () => {
      try {
        // Adjust the URL/Port if your backend runs on a different port
        const response = await fetch('http://localhost:8000/traceability_all_mos');
        if (!response.ok) {
          throw new Error(`Network Error: ${response.status}`);
        }
        const result = await response.json();
        
        // Handle backend initialization state
        if (result.status === 'initializing') {
          setError(result.message);
        } else {
          setData(result.data);
          setError(null);
        }
      } catch (err) {
        setError('Failed to connect to the TBE backend pipeline.');
      } finally {
        setLoading(false);
      }
    };

    fetchData();
    // Optional: Auto-refresh every 5 minutes to stay synced with backend cache
    const interval = setInterval(fetchData, 300000); 
    return () => clearInterval(interval);
  }, []);

  // Filter logic for the search bar
  const filteredData = data.filter((row) => {
    const searchString = `${row.mo_number} ${row.product_variant} ${row.ring_type}`.toLowerCase();
    return searchString.includes(searchTerm.toLowerCase());
  });

  return (
    <div style={{ padding: '20px', fontFamily: 'Arial, sans-serif' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
        <div>
          <h1 style={{ margin: 0, color: '#0f172a' }}>TBE Calibration Tracking</h1>
          <p style={{ margin: 0, color: '#64748b' }}>Transit Buffer / Channel Synchronization Dashboard</p>
        </div>
        <input
          type="text"
          placeholder="Filter by MO or Variant..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          style={{ padding: '8px 12px', width: '300px', borderRadius: '4px', border: '1px solid #cbd5e1' }}
        />
      </div>

      {loading ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#64748b' }}>Loading TBE Matrix...</div>
      ) : error ? (
        <div style={{ textAlign: 'center', padding: '40px', color: '#b91c1c', backgroundColor: '#fef2f2', borderRadius: '4px' }}>
          {error}
        </div>
      ) : (
        <div style={{ overflowX: 'auto', border: '1px solid #e2e8f0', borderRadius: '4px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '14px', textAlign: 'center' }}>
            
            {/* TOP HEADER ROW: GROUPED COLUMNS WITH COLORS MATCHING YOUR IMAGE 2 */}
            <thead>
              <tr style={{ color: '#ffffff', fontWeight: 'bold' }}>
                <th colSpan="4" style={{ backgroundColor: '#1e293b', padding: '12px', borderRight: '1px solid #cbd5e1' }}>
                  Order Metadata
                </th>
                <th colSpan="2" style={{ backgroundColor: '#1d4ed8', padding: '12px', borderRight: '1px solid #cbd5e1' }}>
                  SHO Department
                </th>
                <th colSpan="2" style={{ backgroundColor: '#9a3412', padding: '12px', borderRight: '1px solid #cbd5e1' }}>
                  Transit Buffer
                </th>
                <th colSpan="3" style={{ backgroundColor: '#047857', padding: '12px', borderRight: '1px solid #cbd5e1' }}>
                  Channel Section (Combined)
                </th>
                <th colSpan="1" style={{ backgroundColor: '#0f172a', padding: '12px' }}>
                  System Status
                </th>
              </tr>
              
              {/* SUB HEADER ROW */}
              <tr style={{ backgroundColor: '#f8fafc', color: '#334155', borderBottom: '2px solid #cbd5e1' }}>
                {/* Order Metadata */}
                <th style={styles.th}>MO Number</th>
                <th style={styles.th}>Product Variant</th>
                <th style={styles.th}>Target Qty</th>
                <th style={{...styles.th, borderRight: '2px solid #cbd5e1'}}>Ring Type</th>
                
                {/* SHO Department */}
                <th style={styles.th}>Qty</th>
                <th style={{...styles.th, borderRight: '2px solid #cbd5e1'}}>In Date</th>
                
                {/* Transit Buffer */}
                <th style={styles.th}>Qty</th>
                <th style={{...styles.th, borderRight: '2px solid #cbd5e1'}}>Out Date</th>
                
                {/* Channel Section */}
                <th style={styles.th}>Qty</th>
                <th style={styles.th}>In Date</th>
                <th style={{...styles.th, borderRight: '2px solid #cbd5e1'}}>Out Date</th>
                
                {/* System Status */}
                <th style={styles.th}>Tracking Status</th>
              </tr>
            </thead>

            {/* TABLE BODY */}
            <tbody>
              {filteredData.length === 0 ? (
                <tr>
                  <td colSpan="12" style={{ padding: '30px', color: '#64748b', fontStyle: 'italic' }}>
                    No matching TBE Tracking data located.
                  </td>
                </tr>
              ) : (
                filteredData.map((row, index) => (
                  <tr key={index} style={{ borderBottom: '1px solid #e2e8f0', backgroundColor: index % 2 === 0 ? '#ffffff' : '#f8fafc' }}>
                    
                    {/* Order Metadata */}
                    <td style={styles.td}>{row.mo_number}</td>
                    <td style={{...styles.td, fontWeight: 'bold'}}>{row.product_variant}</td>
                    <td style={styles.td}>{row.target_qty}</td>
                    <td style={{...styles.td, fontWeight: 'bold', borderRight: '2px solid #e2e8f0'}}>{row.ring_type}</td>
                    
                    {/* SHO Department */}
                    <td style={styles.td}>{row.sho_qty.toLocaleString()}</td>
                    <td style={{...styles.td, borderRight: '2px solid #e2e8f0'}}>{row.sho_in_date}</td>
                    
                    {/* Transit Buffer */}
                    <td style={styles.td}>{row.tb_qty.toLocaleString()}</td>
                    <td style={{...styles.td, borderRight: '2px solid #e2e8f0'}}>{row.tb_out_date}</td>
                    
                    {/* Channel Section */}
                    <td style={styles.td}>{row.ch_qty.toLocaleString()}</td>
                    <td style={styles.td}>{row.ch_in_date}</td>
                    <td style={{...styles.td, borderRight: '2px solid #e2e8f0'}}>{row.ch_out_date}</td>
                    
                    {/* System Status */}
                    <td style={{
                      ...styles.td, 
                      fontWeight: 'bold',
                      color: row.tracking_status === 'Completed' ? '#166534' : 
                             row.tracking_status === 'In Process' ? '#b45309' : '#475569'
                    }}>
                      {row.tracking_status}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

// Reusable styles for table cells to keep the JSX clean
const styles = {
  th: {
    padding: '12px 8px',
    borderBottom: '1px solid #cbd5e1',
    fontWeight: '600'
  },
  td: {
    padding: '12px 8px',
    color: '#334155'
  }
};

export default TBE;
