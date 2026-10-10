import { Link } from "react-router-dom";
import { useRegistry } from "../../context/RegistryContext";
import StatusBadge from "../../components/StatusBadge";

export default function MyApplications() {
  const { requestList } = useRegistry();

  return (
    <div style={{ fontFamily: "sans-serif", padding: 20 }}>
      <h2>My Applications</h2>

      <table border="1" cellPadding="8" style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th>Request ID</th>
            <th>Parcel</th>
            <th>From</th>
            <th>To</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {requestList.map((r) => (
            <tr key={r.id}>
              <td>{r.id}</td>
              <td>{r.parcelId}</td>
              <td>{r.from}</td>
              <td>{r.to}</td>
              <td><StatusBadge status={r.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ marginTop: 16 }}>
        <Link to="/citizen/dashboard">Back to Dashboard</Link>
      </div>
    </div>
  );
}