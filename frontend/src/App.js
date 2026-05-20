import { BrowserRouter as Router, Routes, Route } from "react-router-dom";

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

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/dashboard" element={<MainDashboard />} />

        <Route path="/forecasting" element={<Forecasting />} />
        <Route path="/orders" element={<Orders />} />
        <Route path="/inventory" element={<Inventory />} />
        <Route path="/production" element={<Production />} />
        <Route path="/procurement" element={<Procurement />} />
        <Route path="/vendor" element={<Vendor />} />
        <Route path="/finance" element={<Finance />} />
        <Route path="/logistics" element={<Logistics />} />
        <Route path="/chatbot" element={<SupplierChatbot />} />
      </Routes>
    </Router>
  );
}

export default App;
