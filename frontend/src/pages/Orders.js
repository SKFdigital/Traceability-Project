const API_BASE_URL = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";
import { useEffect, useMemo, useState } from "react";
import "./Orders.css";

function Orders() {
  const [orders, setOrders] = useState([]);
  const [editingId, setEditingId] = useState(null);

  // 🔍 Search & Sort
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState("expected_delivery_date");
  const [sortOrder, setSortOrder] = useState("asc");

  // 📅 Month/Sheet Filter
  const [monthFilter, setMonthFilter] = useState("All");
  const [monthOptions, setMonthOptions] = useState(["All"]);

  const [formData, setFormData] = useState({
    customer_name: "",
    customer_location: "",
    product_name: "",
    quantity: "",
    expected_delivery_date: "",
    status: "",
  });

  // ================= FETCH ORDERS =================
  const fetchOrders = async () => {
    try {
      // ✅ FIXED: Changed double quotes to backticks
      const res = await fetch(`${API_BASE_URL}/get_orders`);
      const data = await res.json();
      setOrders(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error("Fetch failed:", err);
    }
  };

  // ================= FETCH SHEET NAMES =================
  const fetchSheetNames = async () => {
    try {
      // ✅ FIXED: Changed double quotes to backticks
      const res = await fetch(`${API_BASE_URL}/get_sheet_names`);
      const data = await res.json();
      const sheets = Array.isArray(data) ? data : data.sheets || [];

      const monthOrder = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
      ];

      const sortedSheets = sheets
        .filter((s) => s !== "ALL" && /^[A-Za-z]{3}-\d{2}$/.test(s))
        .sort((a, b) => {
          const [ma, ya] = a.split("-");
          const [mb, yb] = b.split("-");
          const yearDiff = parseInt(ya, 10) - parseInt(yb, 10);
          if (yearDiff !== 0) return yearDiff;
          return monthOrder.indexOf(ma) - monthOrder.indexOf(mb);
        });

      setMonthOptions(["All", ...sortedSheets]);

      // Auto-select current month
      const now = new Date();
      const currentMonth = `${now.toLocaleString("default", { month: "short" })}-${now.getFullYear().toString().slice(2)}`;
      if (sortedSheets.includes(currentMonth)) {
        setMonthFilter(currentMonth);
      }
    } catch (err) {
      console.error("Failed to fetch sheet names:", err);
    }
  };

  // ================= LOAD DATA =================
  useEffect(() => {
    const loadData = async () => {
      await fetchSheetNames();
      await fetchOrders();
    };
    loadData();
  }, []);

  // ================= REFRESH BUTTON =================
  const handleRefresh = async () => {
    await fetchSheetNames();
    await fetchOrders();
    alert("✅ Orders and sheet list refreshed successfully!");
  };

  // ================= FORM HANDLING =================
  const handleChange = (e) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleSubmit = async () => {
    if (!formData.expected_delivery_date) {
      alert("Please enter expected delivery date!");
      return;
    }

    // ✅ FIXED: Changed the baseline fallback line to backticks
    const url = editingId
      ? `${API_BASE_URL}/update_order/${editingId}`
      : `${API_BASE_URL}/add_order`;

    const method = editingId ? "PUT" : "POST";

    try {
      await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData),
      });
    } catch (err) {
      console.error("Add/Update failed:", err);
      alert("Failed to save order.");
    }

    setFormData({
      customer_name: "",
      customer_location: "",
      product_name: "",
      quantity: "",
      expected_delivery_date: "",
      status: "",
    });

    setEditingId(null);
    fetchOrders();
  };

  // ================= EDIT / DELETE =================
  const handleEdit = (order) => {
    setEditingId(order.id);
    setFormData({
      customer_name: order.customer_name,
      customer_location: order.customer_location || "",
      product_name: order.product_name,
      quantity: order.quantity,
      expected_delivery_date: order.expected_delivery_date,
      status: order.status || "",
    });
  };

  const handleDelete = async (id) => {
    try {
      await fetch(`${API_BASE_URL}/delete_order/${id}`, { method: "DELETE" });
      fetchOrders();
    } catch (err) {
      console.error("Delete failed:", err);
    }
  };

  // ================= IMPORT FROM GOOGLE SHEET =================
  const handleImport = async () => {
    try {
      // ✅ FIXED: Changed double quotes to backticks
      const res = await fetch(`${API_BASE_URL}/import_orders_google_sheet`, {
        method: "POST",
      });
      const data = await res.json();
      const msg = data.message || data.detail || `Imported ${data.imported_count || 0}`;
      alert(msg);
      await fetchSheetNames();
      fetchOrders();
    } catch (err) {
      console.error("Import failed:", err);
      alert("Import failed. Check backend logs.");
    }
  };

  // ================= SEARCH & FILTER =================
  const filteredOrders = useMemo(() => {
    let result = orders;

    if (search) {
      result = result.filter((o) =>
        Object.values(o)
          .filter(Boolean)
          .join(" ")
          .toLowerCase()
          .includes(search.toLowerCase())
      );
    }

    if (monthFilter !== "All") {
      result = result.filter((o) => {
        if (o.sheet_name && o.sheet_name === monthFilter) return true;
        if (!o.expected_delivery_date) return false;
        try {
          const date = new Date(o.expected_delivery_date);
          const monthShort = date.toLocaleString("default", { month: "short" });
          const yearShort = date.getFullYear().toString().slice(2);
          const monthYearWithHyphen = `${monthShort}-${yearShort}`;
          return monthYearWithHyphen === monthFilter;
        } catch {
          return false;
        }
      });
    }

    return result;
  }, [orders, search, monthFilter]);

  // ================= STATUS OPTIONS & COLORS =================
  const statusOptions = [
    "Pending",
    "In Work",
    "Out for Delivery",
    "Delivered",
    "Completed",
    "Issue",
  ];

  const statusColors = {
    Pending: "#f97316", // orange
    "In Work": "#2563eb", // blue
    "Out for Delivery": "#facc15", // amber
    Delivered: "#16a34a", // green
    Completed: "#7e22ce", // purple
    Issue: "#dc2626", // red
  };

  // ================= UPDATE STATUS INLINE =================
  const handleStatusChange = async (orderId, newStatus) => {
    try {
      await fetch(`${API_BASE_URL}/update_order/${orderId}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ...orders.find((o) => o.id === orderId),
          status: newStatus,
        }),
      });
      fetchOrders();
    } catch (err) {
      console.error("Failed to update status:", err);
    }
  };

  // ================= SUMMARY CARDS =================
  const summary = useMemo(() => {
    const total = filteredOrders.length;

    const completed = filteredOrders.filter((o) =>
      ["completed", "out for delivery", "delivered"].some((k) =>
        o.status?.toLowerCase().includes(k)
      )
    ).length;

    const pending = filteredOrders.filter((o) =>
      ["pending", "in work", "issue"].some((k) =>
        o.status?.toLowerCase().includes(k)
      )
    ).length;

    return { total, completed, pending };
  }, [filteredOrders]);

  // ================= SORT =================
  const sortedOrders = useMemo(() => {
    return [...filteredOrders].sort((a, b) => {
      let valA = a[sortBy];
      let valB = b[sortBy];

      if (sortBy.includes("date")) {
        valA = valA ? new Date(valA) : new Date(0);
        valB = valB ? new Date(valB) : new Date(0);
      }

      if (valA < valB) return sortOrder === "asc" ? -1 : 1;
      if (valA > valB) return sortOrder === "asc" ? 1 : -1;
      return 0;
    });
  }, [filteredOrders, sortBy, sortOrder]);

  const handleSort = (column) => {
    if (sortBy === column) {
      setSortOrder(sortOrder === "asc" ? "desc" : "asc");
    } else {
      setSortBy(column);
      setSortOrder("asc");
    }
  };

  return (
    <div className="orders-page">
      <h2>📦 Order Management</h2>

      {/* 🔍 Search */}
      <input
        className="search-input"
        placeholder="Search orders..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />

      {/* 📅 Month Filter */}
      <select
        className="search-input"
        value={monthFilter}
        onChange={(e) => setMonthFilter(e.target.value)}
      >
        {monthOptions.map((m) => (
          <option key={m} value={m}>{m}</option>
        ))}
      </select>

      {/* 🔄 Buttons */}
      <div style={{ display: "flex", gap: "10px", margin: "10px 0" }}>
        <button onClick={handleImport} style={{ padding: "8px 12px" }}>
          Import Orders from Google Sheet
        </button>
        <button
          onClick={handleRefresh}
          style={{
            padding: "8px 12px",
            backgroundColor: "#059669",
            color: "white",
            border: "none",
            borderRadius: "6px",
          }}
        >
          🔄 Refresh Orders
        </button>
      </div>

      {/* 📊 Summary Cards */}
      <div style={{ display: "flex", gap: "15px", marginBottom: "20px" }}>
        <div style={{ flex: 1, background: "#f1f5f9", padding: "12px", borderRadius: "8px", textAlign: "center" }}>
          <h3 style={{ margin: "0", color: "#1e293b" }}>Total Orders</h3>
          <p style={{ fontSize: "20px", fontWeight: "bold" }}>{summary.total}</p>
        </div>
        <div style={{ flex: 1, background: "#ede9fe", padding: "12px", borderRadius: "8px", textAlign: "center" }}>
          <h3 style={{ margin: "0", color: "#5b21b6" }}>Completed / Delivered</h3>
          <p style={{ fontSize: "20px", fontWeight: "bold" }}>{summary.completed}</p>
        </div>
        <div style={{ flex: 1, background: "#ffedd5", padding: "12px", borderRadius: "8px", textAlign: "center" }}>
          <h3 style={{ margin: "0", color: "#9a3412" }}>Pending / In Work / Issue</h3>
          <p style={{ fontSize: "20px", fontWeight: "bold" }}>{summary.pending}</p>
        </div>
      </div>

      {/* ===== FORM ===== */}
      <div className="order-form">
        <input name="customer_name" placeholder="Customer Name" value={formData.customer_name} onChange={handleChange} />
        <input name="customer_location" placeholder="Customer Location" value={formData.customer_location} onChange={handleChange} />
        <input name="product_name" placeholder="Product Name" value={formData.product_name} onChange={handleChange} />
        <input name="quantity" type="number" placeholder="Quantity" value={formData.quantity} onChange={handleChange} />
        <input name="expected_delivery_date" type="date" value={formData.expected_delivery_date} onChange={handleChange} />
        <select name="status" value={formData.status} onChange={handleChange}>
          <option value="">Select Status</option>
          {statusOptions.map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>

        <button onClick={handleSubmit}>
          {editingId ? "Update Order" : "Add Order"}
        </button>
      </div>

      {/* ===== TABLE ===== */}
      <table className="orders-table">
        <thead>
          <tr>
            <th onClick={() => handleSort("customer_name")}>Customer</th>
            <th onClick={() => handleSort("customer_location")}>Location</th>
            <th onClick={() => handleSort("product_name")}>Product</th>
            <th onClick={() => handleSort("quantity")}>Qty</th>
            <th onClick={() => handleSort("expected_delivery_date")}>Delivery</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>

        <tbody>
          {sortedOrders.length === 0 ? (
            <tr>
              <td colSpan="7" style={{ textAlign: "center" }}>No orders found</td>
            </tr>
          ) : (
            sortedOrders.map((o) => (
              <tr key={o.id}>
                <td>{o.customer_name}</td>
                <td>{o.customer_location}</td>
                <td>{o.product_name}</td>
                <td>{o.quantity}</td>
                <td>{o.expected_delivery_date}</td>
                <td>
                  <select
                    value={o.status || ""}
                    onChange={(e) => handleStatusChange(o.id, e.target.value)}
                    style={{
                      backgroundColor: statusColors[o.status] || "#e5e7eb",
                      color: "white",
                      padding: "4px 8px",
                      borderRadius: "8px",
                      border: "none",
                      fontWeight: "bold",
                    }}
                  >
                    <option value="">Select</option>
                    {statusOptions.map((s) => (
                      <option key={s} value={s}>{s}</option>
                    ))}
                  </select>
                </td>
                <td>
                  <button className="edit" onClick={() => handleEdit(o)}>Edit</button>
                  <button className="delete" onClick={() => handleDelete(o.id)}>Delete</button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export default Orders;