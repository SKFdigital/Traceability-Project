import React, { useState } from 'react';
import './Traceability.css';

const Traceability = () => {
  const [mo, setMo] = useState('');
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const fetchTraceability = async () => {

    if (!mo) return;

    setLoading(true);
    setError('');
    setData(null);

    try {

      const response = await fetch(
        `https://scm-backend-pshv.onrender.com/traceability_report/${mo}`
      );

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || 'Failed to fetch');
      }

      setData(result);

    } catch (err) {

      console.error(err);
      setError(err.message);

    } finally {

      setLoading(false);

    }
  };

  return (
    <div className="traceability-container">

      <h2>MO Traceability Lookup</h2>

      <div className="search-section">

        <input
          value={mo}
          onChange={(e) => setMo(e.target.value)}
          placeholder="Enter MO Number"
        />

        <button onClick={fetchTraceability}>
          Track MO
        </button>

      </div>

      {loading && (
        <div className="loading">
          Loading traceability...
        </div>
      )}

      {error && (
        <div className="error-box">
          {error}
        </div>
      )}

      {data && (

        <div className="result-card">

          <div className="summary-grid">

            <div>
              <strong>Searched MO</strong>
              <p>{data.searched_mo}</p>
            </div>

            <div>
              <strong>Normalized MO</strong>
              <p>{data.normalized_mo}</p>
            </div>

            <div>
              <strong>Total Records</strong>
              <p>{data.total_records}</p>
            </div>

            <div>
              <strong>Status</strong>
              <p>{data.status}</p>
            </div>

          </div>

          <div className="timeline-table-wrapper">

            <table className="timeline-table">

              <thead>
                <tr>
                  <th>Date</th>
                  <th>Source</th>
                  <th>Sheet/Channel</th>
                  <th>MO</th>
                  <th>Shift</th>
                  <th>Production</th>
                  <th>Approved Qty</th>
                  <th>Returned Qty</th>
                  <th>Status</th>
                  <th>Next Station</th>
                  <th>Remark</th>
                </tr>
              </thead>

              <tbody>

                {data.timeline?.map((row, index) => (

                  <tr key={index}>

                    <td>
                      {row.date || '-'}
                    </td>

                    <td>
                      {row.source || '-'}
                    </td>

                    <td>
                      {row.channel ||
                        row.sheet ||
                        row.source_channel ||
                        '-'}
                    </td>

                    <td>
                      {row.mo || '-'}
                    </td>

                    <td>
                      {row.shift || '-'}
                    </td>

                    <td>
                      {row.production || '-'}
                    </td>

                    <td>
                      {row.qty_approved || '-'}
                    </td>

                    <td>
                      {row.qty_returned || '-'}
                    </td>

                    <td>
                      {row.status || '-'}
                    </td>

                    <td>
                      {row.next_station || '-'}
                    </td>

                    <td>
                      {row.remark || '-'}
                    </td>

                  </tr>

                ))}

              </tbody>

            </table>

          </div>

        </div>

      )}

    </div>
  );
};

export default Traceability;
