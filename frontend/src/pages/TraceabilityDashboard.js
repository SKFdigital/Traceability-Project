import React, { useEffect, useState } from 'react';

import { useNavigate } from 'react-router-dom';

import './Traceability.css';

const API =
  'https://scm-backend-pshv.onrender.com';

const TraceabilityDashboard = () => {

  const navigate = useNavigate();

  const [loading, setLoading] = useState(false);

  const [allMos, setAllMos] = useState([]);

  const [filteredMos, setFilteredMos] =
    useState([]);

  const [search, setSearch] = useState('');

  // =====================================================
  // LOAD MASTER
  // =====================================================

  useEffect(() => {

    loadMaster();

  }, []);

  const loadMaster = async () => {

    try {

      setLoading(true);

      const response = await fetch(
        `${API}/traceability_all_mos`
      );

      const result = await response.json();

      if (result.status === 'success') {

        setAllMos(result.data);

        setFilteredMos(result.data);
      }

    } catch (error) {

      console.error(error);

    } finally {

      setLoading(false);
    }
  };

  // =====================================================
  // SEARCH
  // =====================================================

  const handleSearch = (value) => {

    setSearch(value);

    if (!value) {

      setFilteredMos(allMos);

      return;
    }

    const filtered = allMos.filter((item) => {

      return (
        item.mo
          ?.toLowerCase()
          .includes(value.toLowerCase())

        ||

        item.family
          ?.toLowerCase()
          .includes(value.toLowerCase())
      );
    });

    setFilteredMos(filtered);
  };

  // =====================================================
  // OPEN FLOW
  // =====================================================

  const openFlow = (mo) => {

    navigate(`/traceability/${mo}`);
  };

  // =====================================================
  // UI
  // =====================================================

  return (

    <div className="traceability-container">

      <div className="header-section">

        <h1>
          MO Traceability Dashboard
        </h1>

        <input
          className="search-box"
          placeholder="Search MO / Bearing Family..."
          value={search}
          onChange={(e) =>
            handleSearch(e.target.value)
          }
        />

      </div>

      {loading && (
        <div className="loading-box">
          Loading Traceability...
        </div>
      )}

      <div className="table-wrapper">

        <table>

          <thead>

            <tr>

              <th>MO</th>

              <th>Bearing Family</th>

              <th>Start Date</th>

              <th>End Date</th>

              <th>SHO Qty</th>

              <th>Transit Qty</th>

              <th>Channel</th>

              <th>Channel Qty</th>

              <th>Output Qty</th>

              <th>Status</th>

              <th>Total Stages</th>

              <th>Action</th>

            </tr>

          </thead>

          <tbody>

            {filteredMos.map((row, index) => (

              <tr key={index}>

                <td>{row.mo}</td>

                <td>{row.family}</td>

                <td>
                  {row.start_date || '-'}
                </td>

                <td>
                  {row.end_date || '-'}
                </td>

                <td>{row.sho_qty}</td>

                <td>{row.transit_qty}</td>

                <td>{row.channel}</td>

                <td>{row.channel_qty}</td>

                <td>{row.output_qty}</td>

                <td>{row.status}</td>

                <td>{row.total_stages}</td>

                <td>

                  <button
                    onClick={() =>
                      openFlow(row.mo)
                    }
                  >
                    View Flow
                  </button>

                </td>

              </tr>

            ))}

          </tbody>

        </table>

      </div>

    </div>
  );
};

export default TraceabilityDashboard;
