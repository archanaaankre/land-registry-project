import { Link } from "react-router-dom";
import { useRegistry } from "../../context/RegistryContext";
import StatusBadge from "../../components/StatusBadge";

export default function RegistrarDashboard() {
  const { requestList } = useRegistry();
  const pending = requestList.filter((r) => r.status === "Pending").length;
  const completed = requestList.filter((r) => r.status === "Completed").length;

  return (
    <div style={{ fontFamily: "sans-serif", padding: 20 }}>
      <h2>Registrar Dashboard</h2>

      <div style={{ display: "flex", gap: 16, margin: "20px 0" }}>
        <div style={{ border: "1px solid #ccc", padding: 16, borderRadius: 8 }}>
          Pending Requests: {pending}
        </div>
        <div style={{ border: "1px solid #ccc", padding: 16, borderRadius: 8 }}>
          Approved: {completed}
        </div>
      </div>

      <h3>Pending Transfers</h3>
      <table border="1" cellPadding="8" style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th>Request ID</th>
            <th>Parcel</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {requestList
            .filter((r) => r.status === "Pending")
            .map((r) => (
              <tr key={r.id}>
                <td>
                  <Link to={`/registrar/verify/${r.id}`}>{r.id}</Link>
                </td>
                <td>{r.parcelId}</td>
                <td><StatusBadge status={r.status} /></td>
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}