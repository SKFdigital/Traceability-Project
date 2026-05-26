import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";

import Login from "./Login"; 
import MainDashboard from "./pages/MainDashboard";
import Forecasting from "./pages/Forecasting";
import Orders from "./pages/Orders";
import Traceability from './pages/Traceability'; // Adjust this path if your file is in a subfolder
import Inventory from "./pages/Inventory";
import Production from "./pages/Production";
import Procurement from "./pages/Procurement";
import Vendor from "./pages/Vendor";
import Finance from "./pages/Finance";
import Logistics from "./pages/Logistics";
import SupplierChatbot from "./pages/SupplierChatbot";

// 🔒 THE BOUNCER: This component checks if the user is actually logged in
const ProtectedRoute = ({ children }) => {
  // Check sessionStorage (which clears when the tab is closed)
  const token = sessionStorage.getItem("token");
  
  // If there is no token, kick them instantly back to the login page
  if (!token) {
    return <Navigate to="/" replace />;
  }
  
  // If they have a token, let them see the page
  return children;
};

function App() {
  return (
    <Router>
      <Routes>
        {/* PUBLIC ROUTE: Anyone can access the login page */}
        <Route path="/" element={<Login />} />

        {/* 🔒 PROTECTED ROUTES: You must have a token to see these */}
        <Route path="/dashboard" element={<ProtectedRoute><MainDashboard /></ProtectedRoute>} />
        <Route path="/forecasting" element={<ProtectedRoute><Forecasting /></ProtectedRoute>} />
        <Route path="/orders" element={<ProtectedRoute><Orders /></ProtectedRoute>} />
        <Route path="/traceability" element={<Traceability />} />  
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
