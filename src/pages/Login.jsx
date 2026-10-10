import { useState } from "react";
import { useNavigate } from "react-router-dom";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const navigate = useNavigate();

  const handleLogin = (e) => {
    e.preventDefault();
    console.log("Email:", email);
    console.log("Password:", password);
    navigate("/citizen/dashboard");
  };

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        background: "#f5f6f8",
        fontFamily: "sans-serif",
      }}
    >
      <div
        style={{
          width: 350,
          padding: 30,
          background: "white",
          borderRadius: 10,
          boxShadow: "0 4px 15px rgba(0,0,0,0.1)",
        }}
      >
        <h2 style={{ textAlign: "center", marginBottom: 30 }}>
          BLOCKCHAIN ACCESS CONTROL
        </h2>

        <form onSubmit={handleLogin}>
          <label>Email / User ID</label>
          <input
            type="text"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            style={{ width: "100%", marginBottom: 15, padding: 10, boxSizing: "border-box" }}
            required
          />

          <label>Password</label>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            style={{ width: "100%", marginBottom: 20, padding: 10, boxSizing: "border-box" }}
            required
          />

          <button
            type="submit"
            style={{
              width: "100%",
              padding: 12,
              background: "#2563eb",
              color: "white",
              border: "none",
              borderRadius: 6,
              cursor: "pointer",
              fontSize: 16,
            }}
          >
            LOGIN
          </button>
        </form>

        {/* ===== TEMPORARY — remove once backend sends real role ===== */}
        <div style={{ marginTop: 24, paddingTop: 16, borderTop: "1px dashed #d1d5db" }}>
          <p style={{ fontSize: 12, color: "#9ca3af", marginBottom: 8 }}>
            Dev testing only — bypasses backend
          </p>
          <div style={{ display: "flex", gap: 8 }}>
            <button
              type="button"
              onClick={() => navigate("/citizen/dashboard")}
              style={{ flex: 1, padding: 8, fontSize: 12 }}
            >
              Citizen
            </button>
            <button
              type="button"
              onClick={() => navigate("/registrar/dashboard")}
              style={{ flex: 1, padding: 8, fontSize: 12 }}
            >
              Registrar
            </button>
            <button
              type="button"
              onClick={() => navigate("/admin/dashboard")}
              style={{ flex: 1, padding: 8, fontSize: 12 }}
            >
              Admin
            </button>
          </div>
        </div>
        {/* ===== END TEMPORARY ===== */}
      </div>
    </div>
  );
}