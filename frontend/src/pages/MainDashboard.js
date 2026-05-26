import { useNavigate } from "react-router-dom";
import "./MainDashboard.css";

export default function MainDashboard() {
  const navigate = useNavigate();

  const modules = [
    {
      title: "AI Forecasting",
      desc: "Demand prediction using machine learning",
      path: "/forecasting",
      icon: "📈",
    },
    {
      title: "Order Management",
      desc: "Customer & internal order tracking",
      path: "/orders",
      icon: "📑",
    },
    {
      title: "Smart Inventory",
      desc: "Automated stock optimization",
      path: "/inventory",
      icon: "📦",
    },
    {
      title: "Production Planning",
      desc: "AI-based production scheduling",
      path: "/production",
      icon: "🏭",
    },
    {
      title: "SCM Procurement",
      desc: "Procurement based on production schedule",
      path: "/procurement",
      icon: "🧾",
    },
    {
      title: "Vendor Management",
      desc: "Supplier performance & contracts",
      path: "/vendor",
      icon: "🤝",
    },
    {
      title: "Finance & Payments",
      desc: "Automated billing & payments",
      path: "/finance",
      icon: "💳",
    },
    {
      title: "Logistics Optimization",
      desc: "Route & transportation optimization",
      path: "/logistics",
      icon: "🚚",
    },
    {
      title: "Supplier Chatbot",
      desc: "AI chatbot for supplier search",
      path: "/chatbot",
      icon: "🤖",
    },
    // --- ADDED TRACEABILITY MODULE BELOW ---
    {
      title: "MO Traceability",
      desc: "End-to-end manufacturing order tracking",
      path: "/traceability",
      icon: "🔍",
    },
  ];

  return (
    <div className="dashboard-container">
      <header className="dashboard-header">
        <h1>AI-Driven Supply Chain Management System</h1>
        <p>End-to-End Optimization Platform for Manufacturing</p>
      </header>

      <div className="dashboard-grid">
        {modules.map((mod) => (
          <div
            key={mod.path}
            className="dashboard-card"
            onClick={() => navigate(mod.path)}
          >
            <div className="card-icon">{mod.icon}</div>
            <h3>{mod.title}</h3>
            <p>{mod.desc}</p>
          </div>
        ))}
      </div>
    </div>
  );
}
