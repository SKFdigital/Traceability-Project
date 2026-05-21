import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import "./Login.css";

const API_BASE_URL = process.env.REACT_APP_API_URL || "http://127.0.0.1:8000";

function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const navigate = useNavigate(); 

  // 🔥 This forces the browser to delete any old lingering tokens 
  // from previous buggy logins the moment the login page opens.
  useEffect(() => {
    localStorage.removeItem("token");
    localStorage.removeItem("role");
  }, []);

  const handleLogin = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
        }),
      });

      const data = await response.json();

      if (response.ok) {
        // ✅ Save to sessionStorage (clears when tab closes)
        // Note: Using data.access_token because that's what FastAPI returns!
        sessionStorage.setItem("token", data.access_token || data.token);
        sessionStorage.setItem("role", data.role || "admin");

        console.log("Login success:", data);

        // ✅ REDIRECT TO MAIN DASHBOARD
        navigate("/dashboard");
      } else {
        alert(data.detail || "Invalid email or password");
      }
    } catch (error) {
      console.error("Login error:", error);
      alert("Error connecting to server");
    }
  };

  return (
    <div className="login-container">
      <h2>SCM System Login</h2>

      <input
        type="email"
        placeholder="Email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
      />

      <input
        type="password"
        placeholder="Password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />

      <button onClick={handleLogin}>Login</button>
    </div>
  );
}

export default Login;
