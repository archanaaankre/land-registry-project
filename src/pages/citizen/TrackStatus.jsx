import { useState } from "react";
import { useRegistry } from "../../context/RegistryContext";

export default function TrackStatus() {
  const { requestList } = useRegistry();
  const [refId, setRefId] = useState("");
  const [result, setResult] = useState(null);
  const [searched, setSearched] = useState(false);

  const handleSearch = (e) => {
    e.preventDefault();
    const found = requestList.find(
      (r) => r.id.toLowerCase() === refId.trim().toLowerCase()
    );
    setResult(found || null);
    setSearched(true);
  };

  return (
    <div style={{ fontFamily: "sans-serif", padding: 20, maxWidth: 400 }}>
      <h2>Track Application Status</h2>

      <form onSubmit={handleSearch}>
        <label>Reference Number</label>
        <input
          placeholder="e.g. TR-001"
          value={refId}
          onChange={(e) => setRefId(e.target.value)}
          style={{ width: "100%", padding: 8, marginBottom: 12 }}
        />
        <button type="submit" style={{ padding: "8px 16px" }}>Track</button>
      </form>

      {searched && (
        <div style={{ marginTop: 20 }}>
          {result ? (
            <>
              <p><strong>Request ID:</strong> {result.id}</p>
              <p><strong>Parcel:</strong> {result.parcelId}</p>
              <p><strong>From:</strong> {result.from}</p>
              <p><strong>To:</strong> {result.to}</p>
              <p><strong>Status:</strong> {result.status}</p>
            </>
          ) : (
            <p>No application found with that reference number.</p>
          )}
        </div>
      )}
    </div>
  );
}