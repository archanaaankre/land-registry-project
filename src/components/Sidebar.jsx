import { Link, useLocation } from "react-router-dom";

const citizenLinks = [
  { to: "/citizen/dashboard", label: "Dashboard" },
  { to: "/citizen/parcels", label: "My Properties" },
  { to: "/citizen/transfer", label: "Transfer Request" },
  { to: "/citizen/track", label: "Track Status" },
  { to: "/citizen/applications", label: "My Applications" },
  { to: "/citizen/dispute", label: "Raise Dispute" },
];

const registrarLinks = [
  { to: "/registrar/dashboard", label: "Dashboard" },
  { to: "/registrar/requests", label: "All Requests" },
  { to: "/registrar/disputes", label: "Dispute Review" },
];

export default function Sidebar({ role }) {
  const location = useLocation();
  const links = role === "Registrar" ? registrarLinks : citizenLinks;

  return (
    <div
      style={{
        width: 200,
        background: "white",
        borderRight: "1px solid #e5e7eb",
        padding: "16px 12px",
        minHeight: "calc(100vh - 57px)",
      }}
    >
      {links.map((link) => {
        const active = location.pathname === link.to;
        return (
          <Link
            key={link.to}
            to={link.to}
            style={{
              display: "block",
              padding: "10px 12px",
              marginBottom: 4,
              borderRadius: 6,
              fontSize: 14,
              fontWeight: 500,
              background: active ? "#eff6ff" : "transparent",
              color: active ? "#2563eb" : "#374151",
            }}
          >
            {link.label}
          </Link>
        );
      })}
    </div>
  );
}