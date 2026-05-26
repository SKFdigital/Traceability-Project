import React, { useEffect, useState } from 'react';
import './Traceability.css';

const API =
  'https://scm-backend-pshv.onrender.com';

const Traceability = () => {

  const [allMos, setAllMos] = useState([]);

  const [filteredMos, setFilteredMos] = useState([]);

  const [search, setSearch] = useState('');

  const [selectedMo, setSelectedMo] = useState(null);

  const [loading, setLoading] = useState(false);

  // =====================================================
  // LOAD ALL MOs
  // =====================================================

  useEffect(() => {

    fetchAllMos();

  }, []);

  const fetchAllMos = async () => {

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

    const filtered = allMos.filter((item) =>
      item.mo.toLowerCase().includes(
        value.toLowerCase()
      )
    );

    setFilteredMos(filtered);
  };

  // =====================================================
  // FETCH SINGLE MO DETAIL
  // =====================================================

  const openMoDetails = async (mo) => {

    try {

      setLoading(true);

      const response = await fetch(
        `${API}/traceability_report/${mo}`
      );

      const result = await response.json();

      if (
        result.status === 'success' &&
        result.data.length > 0
      ) {

        setSelectedMo(result.data[0]);
      }

    } catch (error) {

      console.error(error);

    } finally {

      setLoading(false);
    }
  };

  // =====================================================
  // UI
  // =====================================================

  return (

    <div className="traceability-container">

      <h1>MO Traceability Dashboard</h1>

      <input
        className="search-box"
        placeholder="Search MO Number..."
        value={search}
        onChange={(e) =>
          handleSearch(e.target.value)
        }
      />

      {loading && (
        <p>Loading...</p>
      )}

      {/* ================================================= */}
      {/* MASTER TABLE */}
      {/* ================================================= */}

      <div className="table-wrapper">

        <table>

          <thead>

            <tr>
              <th>MO</th>
              <th>Total Stages</th>
              <th>Latest Activity</th>
              <th>Total Output</th>
              <th>Action</th>
            </tr>

          </thead>

          <tbody>

            {filteredMos.map((row, index) => (

              <tr key={index}>

                <td>{row.mo}</td>

                <td>{row.total_stages}</td>

                <td>
                  {row.latest_activity || '-'}
                </td>

                <td>
                  {row.total_output || 0}
                </td>

                <td>

                  <button
                    onClick={() =>
                      openMoDetails(row.mo)
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

      {/* ================================================= */}
      {/* DETAIL TABLE */}
      {/* ================================================= */}

      {selectedMo && (

        <div className="details-section">

          <h2>
            MO Flow : {selectedMo.mo}
          </h2>

          <div className="table-wrapper">

            <table>

              <thead>

                <tr>

                  <th>Stage</th>

                  <th>Department</th>

                  <th>Channel</th>

                  <th>Date</th>

                  <th>Shift</th>

                  <th>Production</th>

                  <th>Cumulative</th>

                  <th>Approved Qty</th>

                  <th>Returned Qty</th>

                  <th>Output Qty</th>

                  <th>Towards Packaging</th>

                  <th>End Buffer</th>

                  <th>Next Station</th>

                  <th>Status</th>

                  <th>Remark</th>

                </tr>

              </thead>

              <tbody>

                {selectedMo.stages.map(
                  (stage, idx) => (

                    <tr key={idx}>

                      <td>
                        {stage.stage || '-'}
                      </td>

                      <td>
                        {stage.department || '-'}
                      </td>

                      <td>
                        {stage.channel || '-'}
                      </td>

                      <td>
                        {stage.date ||
                          stage.in_date ||
                          '-'}
                      </td>

                      <td>
                        {stage.shift || '-'}
                      </td>

                      <td>
                        {stage.production || '-'}
                      </td>

                      <td>
                        {stage.cumulative_production || '-'}
                      </td>

                      <td>
                        {stage.quantity || '-'}
                      </td>

                      <td>
                        {stage.returned_qty || '-'}
                      </td>

                      <td>
                        {stage.output_quantity || '-'}
                      </td>

                      <td>
                        {stage.towards_packaging || '-'}
                      </td>

                      <td>
                        {stage.end_buffer || '-'}
                      </td>

                      <td>
                        {stage.next_station || '-'}
                      </td>

                      <td>
                        {stage.status || '-'}
                      </td>

                      <td>
                        {stage.remark || '-'}
                      </td>

                    </tr>
                  )
                )}

              </tbody>

            </table>

          </div>

        </div>
      )}
    </div>
  );
};

export default Traceability;
```
