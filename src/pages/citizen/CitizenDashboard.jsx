import { parcels, transactions, currentUser } from "../../data/sampleData";
import StatusBadge from "../../components/StatusBadge";

export default function CitizenDashboard() {
  return (
    <div style={{ fontFamily: "sans-serif", padding: 20 }}>
      <h2>Welcome, {currentUser.name}</h2>

      <div style={{ display: "flex", gap: 16, margin: "20px 0" }}>
        <div style={{ border: "1px solid #ccc", padding: 16, borderRadius: 8 }}>
          {parcels.length} Parcels
        </div>
        <div style={{ border: "1px solid #ccc", padding: 16, borderRadius: 8 }}>
          1 Pending
        </div>
        <div style={{ border: "1px solid #ccc", padding: 16, borderRadius: 8 }}>
          2 Completed
        </div>
      </div>

      <h3>Recent Transactions</h3>
      <table border="1" cellPadding="8" style={{ borderCollapse: "collapse" }}>
        <thead>
          <tr>
            <th>Txn ID</th>
            <th>Parcel</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {transactions.map((t) => (
            <tr key={t.txnId}>
              <td>{t.txnId}</td>
              <td>{t.parcelId}</td>
              <td><StatusBadge status={t.status} /></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}