import { useRegistry } from "../../context/RegistryContext";
import StatusBadge from "../../components/StatusBadge";

export default function Transactions() {
  const { requestList } = useRegistry();

  // Only show completed transfers as "blockchain transactions"
  const completed = requestList.filter((r) => r.status === "Completed");

  return (
    <div style={{ fontFamily: "sans-serif", padding: 20 }}>
      <h2>Blockchain Transaction History</h2>

      {completed.length === 0 ? (
        <p>No completed transactions yet.</p>
      ) : (
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
            {completed.map((r) => (
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
      )}
    </div>
  );
}