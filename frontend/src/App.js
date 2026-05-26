import { BrowserRouter as Router, Routes, Route, Navigate } from "react-router-dom";

import Login from "./Login";

import MainDashboard from "./pages/MainDashboard";
import Forecasting from "./pages/Forecasting";
import Orders from "./pages/Orders";

import TraceabilityDashboard from "./pages/TraceabilityDashboard";
import TraceabilityFlow from "./pages/TraceabilityFlow";

import Inventory from "./pages/Inventory";
import Production from "./pages/Production";
import Procurement from "./pages/Procurement";
import Vendor from "./pages/Vendor";
import Finance from "./pages/Finance";
import Logistics from "./pages/Logistics";
import SupplierChatbot from "./pages/SupplierChatbot";

// 🔒 THE BOUNCER: This component checks if the user is actually logged in
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

        {/* PUBLIC ROUTE */}
        <Route
          path="/"
          element={<Login />}
        />

        {/* PROTECTED ROUTES */}

        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <MainDashboard />
            </ProtectedRoute>
          }
        />

        <Route
          path="/forecasting"
          element={
            <ProtectedRoute>
              <Forecasting />
            </ProtectedRoute>
          }
        />

        <Route
          path="/orders"
          element={
            <ProtectedRoute>
              <Orders />
            </ProtectedRoute>
          }
        />

        {/* TRACEABILITY DASHBOARD */}

        <Route
          path="/traceability"
          element={
            <ProtectedRoute>
              <TraceabilityDashboard />
            </ProtectedRoute>
          }
        />

        {/* TRACEABILITY FLOW */}

        <Route
          path="/traceability/:mo"
          element={
            <ProtectedRoute>
              <TraceabilityFlow />
            </ProtectedRoute>
          }
        />

        <Route
          path="/inventory"
          element={
            <ProtectedRoute>
              <Inventory />
            </ProtectedRoute>
          }
        />

        <Route
          path="/production"
          element={
            <ProtectedRoute>
              <Production />
            </ProtectedRoute>
          }
        />

        <Route
          path="/procurement"
          element={
            <ProtectedRoute>
              <Procurement />
            </ProtectedRoute>
          }
        />

        <Route
          path="/vendor"
          element={
            <ProtectedRoute>
              <Vendor />
            </ProtectedRoute>
          }
        />

        <Route
          path="/finance"
          element={
            <ProtectedRoute>
              <Finance />
            </ProtectedRoute>
          }
        />

        <Route
          path="/logistics"
          element={
            <ProtectedRoute>
              <Logistics />
            </ProtectedRoute>
          }
        />

        <Route
          path="/chatbot"
          element={
            <ProtectedRoute>
              <SupplierChatbot />
            </ProtectedRoute>
          }
        />

      </Routes>

    </Router>
  );
}

export default App;
