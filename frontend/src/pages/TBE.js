import React, { useEffect, useState } from 'react';
import './Traceability.css';

const API = 'https://scm-backend-pshv.onrender.com';

const TBE = () => {

  const [summaryData, setSummaryData] = useState([]);
  const [selectedMoFlow, setSelectedMoFlow] = useState(null);

  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    fetchSummaryDashboard();
  }, []);

  const fetchSummaryDashboard = async () => {

    try {

      setLoading(true);

      const res = await fetch(
        `${API}/traceability_all_mos`
      );

      if (!res.ok) {
        throw new Error(
          'Failed fetching TBE dashboard'
        );
      }

      const json = await res.json();

      setSummaryData(json.data || []);

    } catch (err) {

      setError(err.message);

    } finally {

      setLoading(false);
    }
  };

  const handleViewDetail = async (mo) => {

    try {

      setLoading(true);

      const res = await fetch(
        `${API}/traceability_report/${mo}`
      );

      if (!res.ok) {
        throw new Error(
          'Failed loading MO detail'
        );
      }

      const json = await res.json();

      setSelectedMoFlow({
        mo,
        flow_data:
          json.data?.timeline || []
      });

    } catch (err) {

      setError(err.message);

    } finally {

      setLoading(false);
    }
  };

  const filteredSummary = summaryData.filter(
    (item) => {

      const s = search.toLowerCase();

      return (
        item.mo?.toLowerCase().includes(s)
        ||
        item.final_variant
          ?.toLowerCase()
          .includes(s)
        ||
        item.component_type
          ?.toLowerCase()
          .includes(s)
      );
    }
  );

  const sortedSummary = [...filteredSummary]
    .sort((a, b) => {

      if (a.mo !== b.mo) {
        return a.mo.localeCompare(b.mo);
      }

      if (
        a.final_variant
        !==
        b.final_variant
      ) {
        return a.final_variant.localeCompare(
          b.final_variant
        );
      }

      return a.component_type.localeCompare(
        b.component_type
      );
    });

  const getMoRowSpan = (
    data,
    currentIndex
  ) => {

    const currentMo =
      data[currentIndex].mo;

    if (
      currentIndex > 0
      &&
      data[currentIndex - 1].mo
      === currentMo
    ) {
      return 0;
    }

    let span = 1;

    while (
      currentIndex + span < data.length
      &&
      data[currentIndex + span].mo
      === currentMo
    ) {
      span++;
    }

    return span;
  };

  const getFamilyRowSpan = (
    data,
    currentIndex
  ) => {

    const currentMo =
      data[currentIndex].mo;

    const currentFamily =
      data[currentIndex].final_variant;

    if (
      currentIndex > 0
      &&
      data[currentIndex - 1].mo
      === currentMo
      &&
      data[currentIndex - 1]
        .final_variant
      === currentFamily
    ) {
      return 0;
    }

    let span = 1;

    while (
      currentIndex + span < data.length
      &&
      data[currentIndex + span].mo
      === currentMo
      &&
      data[currentIndex + span]
        .final_variant
      === currentFamily
    ) {
      span++;
    }

    return span;
  };

  return (

    <div className="traceability-container">

      <div className="header-section">

        <div>

          <h1>
            TBE Calibration Tracking
          </h1>

          <p className="sub-tag">

            {
              selectedMoFlow
                ? `Detailed Flow / ${selectedMoFlow.mo}`
                : 'Transit Buffer / Channel Synchronization Dashboard'
            }

          </p>

        </div>

        <div className="control-actions">

          {
            selectedMoFlow ? (

              <button
                className="back-btn"
                onClick={() =>
                  setSelectedMoFlow(null)
                }
              >
                ← Back
              </button>

            ) : (

              <input
                className="search-box"
                placeholder="Search MO / Family / IM / OM"
                value={search}
                onChange={(e) =>
                  setSearch(e.target.value)
                }
              />

            )
          }

        </div>

      </div>

      {
        error && (
          <div className="error-box">
            {error}
          </div>
        )
      }

      {
        loading && (
          <div className="loading-spinner">
            Loading Dashboard...
          </div>
        )
      }

      {/* SUMMARY TABLE */}
      {
        !loading
        &&
        !selectedMoFlow
        &&
        (
          <div className="table-wrapper">

            <table className="trace-table">

              <thead>

                <tr className="super-header">

                  <th
                    colSpan="4"
                    className="meta-head"
                  >
                    Order Metadata
                  </th>

                  <th
                    colSpan="2"
                    className="sho-head"
                  >
                    SHO
                  </th>

                  <th
                    colSpan="2"
                    className="tb-head"
                  >
                    Transit Buffer
                  </th>

                  <th
                    colSpan="3"
                    className="ch-head"
                  >
                    Channel Section
                  </th>

                  <th
                    className="meta-head"
                  >
                    Status
                  </th>

                </tr>

                <tr className="sub-header">

                  <th>MO</th>

                  <th>
                    Bearing Family
                  </th>

                  <th>Type</th>

                  <th>
                    Target Qty
                  </th>

                  <th>Qty</th>

                  <th>
                    In Date
                  </th>

                  <th>Qty</th>

                  <th>
                    Out Date
                  </th>

                  <th>Qty</th>

                  <th>
                    In Date
                  </th>

                  <th>
                    Out Date
                  </th>

                  <th>Status</th>

                </tr>

              </thead>

              <tbody>

                {
                  sortedSummary.length === 0 && (

                    <tr>

                      <td
                        colSpan="12"
                        className="empty-state"
                      >
                        No TBE records found
                      </td>

                    </tr>
                  )
                }

                {
                  sortedSummary.map(
                    (row, idx) => {

                      const moSpan =
                        getMoRowSpan(
                          sortedSummary,
                          idx
                        );

                      const familySpan =
                        getFamilyRowSpan(
                          sortedSummary,
                          idx
                        );

                      return (

                        <tr
                          key={`${row.mo}-${row.final_variant}-${row.component_type}-${idx}`}
                          className="data-row"
                        >

                          {
                            moSpan > 0 && (

                              <td
                                rowSpan={moSpan}
                                className="merged-mo-cell"
                              >

                                <button
                                  className="mo-link-btn"
                                  onClick={() =>
                                    handleViewDetail(
                                      row.mo
                                    )
                                  }
                                >
                                  {row.mo}
                                </button>

                              </td>
                            )
                          }

                          {
                            familySpan > 0 && (

                              <td
                                rowSpan={familySpan}
                                className="merged-channel-cell fw-bold"
                              >
                                {row.final_variant}
                              </td>

                            )
                          }

                          <td>
                            <strong>
                              {
                                row.component_type
                              }
                            </strong>
                          </td>

                          <td>
                            {
                              Number(
                                row.qty_req || 0
                              ).toLocaleString()
                            }
                          </td>

                          <td>
                            {
                              Number(
                                row.sho_qty || 0
                              ).toLocaleString()
                            }
                          </td>

                          <td>
                            {
                              row.sho_in || '-'
                            }
                          </td>

                          <td>
                            {
                              Number(
                                row.tb_qty || 0
                              ).toLocaleString()
                            }
                          </td>

                          <td>
                            {
                              row.tb_out || '-'
                            }
                          </td>

                          {
                            familySpan > 0 && (
                              <>
                                <td
                                  rowSpan={familySpan}
                                  className="merged-channel-cell"
                                >
                                  {
                                    Number(
                                      row.ch_qty || 0
                                    ).toLocaleString()
                                  }
                                </td>

                                <td
                                  rowSpan={familySpan}
                                  className="merged-channel-cell"
                                >
                                  {
                                    row.ch_in || '-'
                                  }
                                </td>

                                <td
                                  rowSpan={familySpan}
                                  className="merged-channel-cell"
                                >
                                  {
                                    row.ch_out || '-'
                                  }
                                </td>
                              </>
                            )
                          }

                          <td>

                            <span
                              className={`status-badge ${(row.status || '')
                                .toLowerCase()
                                .replace(/\s+/g, '-')}`}
                            >
                              {row.status}
                            </span>

                          </td>

                        </tr>
                      );
                    }
                  )
                }

              </tbody>

            </table>

          </div>
        )
      }

      {/* DETAIL TABLE */}
      {
        !loading
        &&
        selectedMoFlow
        &&
        (
          <div className="table-wrapper">

            <table className="trace-table">

              <thead>

                <tr className="sub-header">

                  <th>
                    Department
                  </th>

                  <th>
                    Product
                  </th>

                  <th>
                    Channel
                  </th>

                  <th>
                    Date
                  </th>

                  <th>
                    Production
                  </th>

                  <th>
                    Cumulative
                  </th>

                </tr>

              </thead>

              <tbody>

                {
                  selectedMoFlow.flow_data
                    .length === 0 && (

                    <tr>

                      <td
                        colSpan="6"
                        className="empty-state"
                      >
                        No flow rows found
                      </td>

                    </tr>
                  )
                }

                {
                  selectedMoFlow.flow_data.map(
                    (row, idx) => (

                      <tr
                        key={idx}
                        className="data-row"
                      >

                        <td>
                          {
                            row.department
                          }
                        </td>

                        <td>
                          {
                            row.product
                          }
                        </td>

                        <td>
                          {
                            row.channel
                          }
                        </td>

                        <td>
                          {
                            row.date
                          }
                        </td>

                        <td>
                          {
                            Number(
                              row.production || 0
                            ).toLocaleString()
                          }
                        </td>

                        <td>
                          {
                            Number(
                              row.cumulative || 0
                            ).toLocaleString()
                          }
                        </td>

                      </tr>
                    )
                  )
                }

              </tbody>

            </table>

          </div>
        )
      }

    </div>
  );
};

export default TBE;
