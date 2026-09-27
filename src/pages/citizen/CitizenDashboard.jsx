import { Link } from "react-router-dom";
import { parcels, transactions, currentUser } from "../../data/sampleData";

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

      <nav style={{ marginBottom: 20, display: "flex", gap: 12 }}>
        <Link to="/citizen/parcels">My Properties</Link>
        <Link to="/citizen/transfer">Transfer Request</Link>
        <Link to="/citizen/track">Track Status</Link>
        <Link to="/citizen/applications">My Applications</Link>
        <Link to="/citizen/dispute">Raise Dispute</Link>
      </nav>

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
              <td>{t.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}