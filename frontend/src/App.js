import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";

import Login from "./Login";
import MainDashboard from "./pages/MainDashboard";
import Forecasting from "./pages/Forecasting";
import Orders from "./pages/Orders";
import Inventory from "./pages/Inventory";
import Production from "./pages/Production";
import Procurement from "./pages/Procurement";
import Vendor from "./pages/Vendor";
import Finance from "./pages/Finance";
import Logistics from "./pages/Logistics";
import SupplierChatbot from "./pages/SupplierChatbot";

// Import Traceability
import Traceability from "./pages/Traceability";
// Import the NEW TBE Module
import TBE from "./pages/TBE"; // <-- Added this import

// 🔒 THE BOUNCER
const ProtectedRoute = ({ children }) => {
  const token = sessionStorage.getItem("token");
  if (!token) {
    return <Navigate to="/" replace />;
  }
  return children;
};

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Login />} />

        {/* PROTECTED ROUTES */}
        <Route path="/dashboard" element={<ProtectedRoute><MainDashboard /></ProtectedRoute>} />
        <Route path="/forecasting" element={<ProtectedRoute><Forecasting /></ProtectedRoute>} />
        <Route path="/orders" element={<ProtectedRoute><Orders /></ProtectedRoute>} />
        
        {/* TRACEABILITY & TBE ROUTES */}
        <Route path="/traceability" element={<ProtectedRoute><Traceability /></ProtectedRoute>} />
        <Route path="/tbe" element={<ProtectedRoute><TBE /></ProtectedRoute>} /> {/* <-- New Route Added */}

        <Route path="/inventory" element={<ProtectedRoute><Inventory /></ProtectedRoute>} />
        <Route path="/production" element={<ProtectedRoute><Production /></ProtectedRoute>} />
        <Route path="/procurement" element={<ProtectedRoute><Procurement /></ProtectedRoute>} />
        <Route path="/vendor" element={<ProtectedRoute><Vendor /></ProtectedRoute>} />
        <Route path="/finance" element={<ProtectedRoute><Finance /></ProtectedRoute>} />
        <Route path="/logistics" element={<ProtectedRoute><Logistics /></ProtectedRoute>} />
        <Route path="/chatbot" element={<ProtectedRoute><SupplierChatbot /></ProtectedRoute>} />
      </Routes>
    </Router>
  );
}

export default App;
