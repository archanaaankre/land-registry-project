import { useNavigate } from "react-router-dom";

export default function Navbar({ role }) {
  const navigate = useNavigate();

  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "14px 24px",
        background: "white",
        borderBottom: "1px solid #e5e7eb",
      }}
    >
      <strong style={{ fontSize: 16 }}>Land Registry</strong>
      <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
        <span style={{ fontSize: 14, color: "#6b7280" }}>{role}</span>
        <button onClick={() => navigate("/")} style={{ padding: "6px 14px" }}>
          Logout
        </button>
      </div>
    </div>
  );
}