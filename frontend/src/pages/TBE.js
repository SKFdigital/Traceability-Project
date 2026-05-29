import React, { useState, useEffect } from 'react';
import './Traceability.css';

const API = 'https://scm-backend-pshv.onrender.com';

const TBE = () => {
  const [summaryData, setSummaryData] = useState([]);
  const [selectedMoFlow, setSelectedMoFlow] = useState(null);

  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [isInitializing, setIsInitializing] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchSummaryDashboard();
  }, []);

  // =====================================================
  // FETCH SUMMARY
  // =====================================================
  const fetchSummaryDashboard = async () => {
    try {
      setLoading(true);
      setError('');

      const res = await fetch(`${API}/traceability_all_mos`);

      if (!res.ok) {
        throw new Error('Network error pulling TBE records.');
      }

      const json = await res.json();

      if (json.status === 'initializing') {
        setIsInitializing(true);

        setTimeout(() => {
          fetchSummaryDashboard();
        }, 4000);

      } else if (json.status === 'success') {
        setIsInitializing(false);
        setSummaryData(json.data || []);
      }

    } catch (err) {
      setError(err.message);

    } finally {
      setLoading(false);
    }
  };

  // =====================================================
  // FETCH DETAIL FLOW
  // =====================================================
  const handleViewDetail = async (moString) => {
    if (!moString) return;

    try {
      setLoading(true);
      setError('');

      const res = await fetch(
        `${API}/traceability_report/${moString.trim()}`
      );

      if (!res.ok) {
        throw new Error(
          'Could not load detailed route flow.'
        );
      }

      const json = await res.json();

      if (json.status === 'success') {

        const timeline =
          json.data?.timeline || [];

        setSelectedMoFlow({
          mo: moString,
          flow_data: timeline
        });
      }

    } catch (err) {
      setError(err.message);

    } finally {
      setLoading(false);
    }
  };

  // =====================================================
  // FILTERING
  // =====================================================
  const filteredSummary = summaryData.filter((item) => {

    const searchLower = search.toLowerCase();

    return (
      (item.mo || '')
        .toLowerCase()
        .includes(searchLower)

      ||

      (item.final_variant || '')
        .toLowerCase()
        .includes(searchLower)

      ||

      (item.component_type || '')
        .toLowerCase()
        .includes(searchLower)
    );
  });

  // =====================================================
  // SORTING
  // =====================================================
  const sortedSummary = [...filteredSummary].sort((a, b) => {

    if (a.mo !== b.mo) {
      return (a.mo || '').localeCompare(b.mo || '');
    }

    if (a.final_variant !== b.final_variant) {
      return (a.final_variant || '')
        .localeCompare(b.final_variant || '');
    }

    return (a.component_type || '')
      .localeCompare(b.component_type || '');
  });

  // =====================================================
  // MO ROW SPAN
  // =====================================================
  const getMoRowSpan = (dataArray, currentIndex) => {

    const currentMo = dataArray[currentIndex].mo;

    if (
      currentIndex > 0 &&
      dataArray[currentIndex - 1].mo === currentMo
    ) {
      return 0;
    }

    let span = 1;

    while (
      currentIndex + span < dataArray.length &&
      dataArray[currentIndex + span].mo === currentMo
    ) {
      span++;
    }

    return span;
  };

  // =====================================================
  // FAMILY ROW SPAN
  // =====================================================
  const getFamilyRowSpan = (dataArray, currentIndex) => {

    const currentMo =
      dataArray[currentIndex].mo;

    const currentFamily =
      dataArray[currentIndex].final_variant;

    if (
      currentIndex > 0 &&
      dataArray[currentIndex - 1].mo === currentMo &&
      dataArray[currentIndex - 1].final_variant === currentFamily
    ) {
      return 0;
    }

    let span = 1;

    while (
      currentIndex + span < dataArray.length &&
      dataArray[currentIndex + span].mo === currentMo &&
      dataArray[currentIndex + span].final_variant === currentFamily
    ) {
      span++;
    }

    return span;
  };

  // =====================================================
  // RENDER
  // =====================================================
  return (
    <div className="traceability-container">

      {/* ========================================= */}
      {/* HEADER */}
      {/* ========================================= */}
      <div className="header-section">

        <div>
          <h1>TBE Calibration Tracking</h1>

          <p className="sub-tag">
            {
              selectedMoFlow
                ? `Detailed Route Flow / MO : ${selectedMoFlow.mo}`
                : 'Transit Buffer / Channel Synchronization Dashboard'
            }
          </p>
        </div>

        <div className="control-actions">

          {
            selectedMoFlow ? (

              <button
                className="back-btn"
                onClick={() => setSelectedMoFlow(null)}
              >
                ← Back to Summary Dashboard
              </button>

            ) : (

              <input
                className="search-box"
                placeholder="Search MO / Family / IM / OM..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                disabled={isInitializing}
              />

            )
          }

        </div>
      </div>

      {/* ========================================= */}
      {/* ERROR */}
      {/* ========================================= */}
      {
        error && (
          <div className="error-box">
            {error}
          </div>
        )
      }

      {/* ========================================= */}
      {/* INITIALIZING */}
      {/* ========================================= */}
      {
        isInitializing && (
          <div className="initializing-box">

            <div className="spinner"></div>

            <p>
              <strong>
                TBE backend engine warming up...
              </strong>
            </p>

            <p className="sub-text">
              Downloading and indexing production sheets...
            </p>

          </div>
        )
      }

      {/* ========================================= */}
      {/* LOADING */}
      {/* ========================================= */}
      {
        loading &&
        !isInitializing && (
          <div className="loading-spinner">
            Loading TBE pipeline cache...
          </div>
        )
      }

      {/* ========================================= */}
      {/* SUMMARY TABLE */}
      {/* ========================================= */}
      {
        !loading &&
        !selectedMoFlow &&
        !isInitializing && (

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
                    SHO Department
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
                    Channel Section (Combined)
                  </th>

                  <th
                    className="meta-head"
                  >
                    System Status
                  </th>

                </tr>

                <tr className="sub-header">

                  <th>MO Number</th>
                  <th>Product Family</th>
                  <th>Ring Type</th>
                  <th>Target Qty</th>

                  <th>Qty</th>
                  <th>In Date</th>

                  <th>Qty</th>
                  <th>Out Date</th>

                  <th>Qty</th>
                  <th>In Date</th>
                  <th>Out Date</th>

                  <th>Status</th>

                </tr>

              </thead>

              <tbody>

                {
                  sortedSummary.map((row, idx) => {

                    const moSpan =
                      getMoRowSpan(sortedSummary, idx);

                    const familySpan =
                      getFamilyRowSpan(sortedSummary, idx);

                    return (

                      <tr
                        key={idx}
                        className="data-row"
                      >

                        {/* ===================== */}
                        {/* MO */}
                        {/* ===================== */}
                        {
                          moSpan > 0 && (
                            <td
                              rowSpan={moSpan}
                              className="merged-mo-cell"
                            >

                              <button
                                className="mo-link-btn"
                                onClick={() =>
                                  handleViewDetail(row.mo)
                                }
                              >
                                {row.mo}
                              </button>

                            </td>
                          )
                        }

                        {/* ===================== */}
                        {/* FAMILY */}
                        {/* ===================== */}
                        {
                          familySpan > 0 && (
                            <td
                              rowSpan={familySpan}
                              className="merged-channel-cell fw-bold"
                            >
                              {row.final_variant || '-'}
                            </td>
                          )
                        }

                        {/* ===================== */}
                        {/* COMPONENT */}
                        {/* ===================== */}
                        <td className="fw-bold">
                          {row.component_type || '-'}
                        </td>

                        {/* ===================== */}
                        {/* TARGET */}
                        {/* ===================== */}
                        <td className="qty-cell">
                          {
                            row.qty_req !== undefined &&
                            row.qty_req !== null
                              ? Number(row.qty_req).toLocaleString()
                              : '-'
                          }
                        </td>

                        {/* ===================== */}
                        {/* SHO */}
                        {/* ===================== */}
                        <td>
                          {
                            row.sho_qty !== undefined &&
                            row.sho_qty !== null
                              ? Number(row.sho_qty).toLocaleString()
                              : '-'
                          }
                        </td>

                        <td>
                          {row.sho_in || '-'}
                        </td>

                        {/* ===================== */}
                        {/* TB */}
                        {/* ===================== */}
                        <td>
                          {
                            row.tb_qty !== undefined &&
                            row.tb_qty !== null
                              ? Number(row.tb_qty).toLocaleString()
                              : '-'
                          }
                        </td>

                        <td>
                          {row.tb_out || '-'}
                        </td>

                        {/* ===================== */}
                        {/* CHANNEL */}
                        {/* ===================== */}
                        {
                          familySpan > 0 && (
                            <>
                              <td
                                rowSpan={familySpan}
                                className="merged-channel-cell"
                              >
                                {
                                  row.ch_qty !== undefined &&
                                  row.ch_qty !== null
                                    ? Number(row.ch_qty).toLocaleString()
                                    : '-'
                                }
                              </td>

                              <td
                                rowSpan={familySpan}
                                className="merged-channel-cell"
                              >
                                {row.ch_in || '-'}
                              </td>

                              <td
                                rowSpan={familySpan}
                                className="merged-channel-cell"
                              >
                                {row.ch_out || '-'}
                              </td>
                            </>
                          )
                        }

                        {/* ===================== */}
                        {/* STATUS */}
                        {/* ===================== */}
                        <td>

                          <span
                            className={`status-badge ${(row.status || '')
                              .toLowerCase()
                              .replace(/\s+/g, '-')}`}
                          >
                            {row.status || '-'}
                          </span>

                        </td>

                      </tr>
                    );
                  })
                }

                {/* ================================= */}
                {/* EMPTY */}
                {/* ================================= */}
                {
                  sortedSummary.length === 0 && (
                    <tr>
                      <td
                        colSpan="12"
                        className="empty-state"
                      >
                        No TBE tracking records found.
                      </td>
                    </tr>
                  )
                }

              </tbody>

            </table>

          </div>
        )
      }

      {/* ========================================= */}
      {/* DETAIL FLOW */}
      {/* ========================================= */}
      {
        !loading &&
        selectedMoFlow && (

          <div className="table-wrapper">

            <table className="trace-table">

              <thead>

                <tr className="sub-header">

                  <th>MO</th>
                  <th>Department</th>
                  <th>Product</th>
                  <th>Channel</th>
                  <th>Date</th>
                  <th>Production</th>
                  <th>Cumulative</th>

                </tr>

              </thead>

              <tbody>

                {
                  selectedMoFlow.flow_data.map(
                    (row, index) => {

                      return (

                        <tr
                          key={index}
                          className="data-row"
                        >

                          {
                            index === 0 && (
                              <td
                                rowSpan={
                                  selectedMoFlow.flow_data.length
                                }
                                className="merged-mo-cell"
                              >
                                <strong>
                                  {selectedMoFlow.mo}
                                </strong>
                              </td>
                            )
                          }

                          <td>
                            {row.department || '-'}
                          </td>

                          <td>
                            {row.product || '-'}
                          </td>

                          <td>
                            {row.channel || '-'}
                          </td>

                          <td>
                            {row.date || '-'}
                          </td>

                          <td>
                            {
                              row.production !== undefined
                                ? Number(row.production).toLocaleString()
                                : '-'
                            }
                          </td>

                          <td>
                            {
                              row.cumulative !== undefined
                                ? Number(row.cumulative).toLocaleString()
                                : '-'
                            }
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

    </div>
  );
};

export default TBE;
