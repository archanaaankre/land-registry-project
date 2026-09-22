import { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function Login() {
  const [role, setRole] = useState("Citizen");
  const navigate = useNavigate();

  const handleLogin = (e) => {
    e.preventDefault();
    if (role === "Citizen") navigate("/citizen/dashboard");
    else navigate("/registrar/dashboard");
  };

  return (
    <div style={{ maxWidth: 320, margin: "80px auto", fontFamily: "sans-serif" }}>
      <h2>LAND REGISTRY LOGIN</h2>
      <form onSubmit={handleLogin}>
        <label>Email / User ID</label>
        <input style={{ width: "100%", marginBottom: 12, padding: 8 }} />
        <label>Password</label>
        <input type="password" style={{ width: "100%", marginBottom: 12, padding: 8 }} />
        <label>Select Role</label>
        <select
          value={role}
          onChange={(e) => setRole(e.target.value)}
          style={{ width: "100%", marginBottom: 20, padding: 8 }}
        >
          <option>Citizen</option>
          <option>Registrar</option>
          <option>Admin</option>
        </select>
        <button type="submit" style={{ width: "100%", padding: 10 }}>LOGIN</button>
      </form>
    </div>
  );
}