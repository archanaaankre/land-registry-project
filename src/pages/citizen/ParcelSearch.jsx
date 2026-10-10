import { useState } from "react";
import { Link } from "react-router-dom";
import { parcels } from "../../data/sampleData";

export default function ParcelSearch() {
  const [query, setQuery] = useState("");

  const filtered = parcels.filter(
    (p) =>
      p.id.toLowerCase().includes(query.toLowerCase()) ||
      p.location.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <div style={{ fontFamily: "sans-serif", padding: 20 }}>
      <h2>Search Land Parcel</h2>

      <input
        placeholder="Search by Parcel ID or Location"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        style={{ padding: 8, width: 300, marginBottom: 20 }}
      />

      <table border="1" cellPadding="8" style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th>Parcel ID</th>
            <th>Location</th>
            <th>Area</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {filtered.map((p) => (
            <tr key={p.id}>
              <td>
                <Link to={`/citizen/parcels/${p.id}`}>{p.id}</Link>
              </td>
              <td>{p.location}</td>
              <td>{p.area}</td>
              <td>{p.status}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}