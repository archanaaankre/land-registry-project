import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useRegistry } from "../../context/RegistryContext";

export default function RaiseDispute() {
  const { parcelList, addDispute } = useRegistry();
  const navigate = useNavigate();
  const [parcelId, setParcelId] = useState("");
  const [reason, setReason] = useState("");
  const [submittedId, setSubmittedId] = useState(null);

  const handleSubmit = (e) => {
    e.preventDefault();
    const newId = addDispute(parcelId, reason);
    setSubmittedId(newId);
  };

  if (submittedId) {
    return (
      <div style={{ fontFamily: "sans-serif", padding: 20 }}>
        <h2>Dispute filed successfully.</h2>
        <p><strong>Dispute ID:</strong> {submittedId}</p>
        <p><strong>Status:</strong> ● Pending Registrar Review</p>
        <button onClick={() => navigate("/citizen/dashboard")} style={{ padding: "8px 16px", marginTop: 12 }}>
          Back to Dashboard
        </button>
      </div>
    );
  }

  return (
    <div style={{ fontFamily: "sans-serif", padding: 20, maxWidth: 400 }}>
      <h2>Raise a Dispute</h2>
      <form onSubmit={handleSubmit}>
        <label>Parcel ID</label>
        <select
          value={parcelId}
          onChange={(e) => setParcelId(e.target.value)}
          style={{ width: "100%", padding: 8, marginBottom: 12 }}
          required
        >
          <option value="">Select a parcel</option>
          {parcelList.map((p) => (
            <option key={p.id} value={p.id}>{p.id}</option>
          ))}
        </select>

        <label>Reason for Dispute</label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          rows={4}
          style={{ width: "100%", padding: 8, marginBottom: 12 }}
          placeholder="e.g. Incorrect area recorded, ownership mismatch..."
          required
        />

        <button type="submit" style={{ padding: "10px 20px", width: "100%" }}>
          Submit Dispute
        </button>
      </form>
    </div>
  );
}