import { Link } from "react-router-dom";
import { transferRequests } from "../../data/sampleData";

export default function Requests() {
  return (
    <div style={{ fontFamily: "sans-serif", padding: 20 }}>
      <h2>All Transfer Requests</h2>

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
          {transferRequests.map((r) => (
            <tr key={r.id}>
              <td>
                <Link to={`/registrar/verify/${r.id}`}>{r.id}</Link>
              </td>
              <td>{r.parcelId}</td>
              <td>{r.from}</td>
              <td>{r.to}</td>
              <td>{r.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}