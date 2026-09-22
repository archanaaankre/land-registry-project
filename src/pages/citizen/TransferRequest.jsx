import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { parcels } from "../../data/sampleData";

export default function TransferRequest() {
  const navigate = useNavigate();
  const [form, setForm] = useState({
    parcelId: "",
    currentOwner: "",
    newOwner: "",
    reason: "Sale",
    declaration: false,
  });
  const [submitted, setSubmitted] = useState(false);

  const handleChange = (e) => {
    const { name, value, type, checked } = e.target;
    setForm((prev) => ({
      ...prev,
      [name]: type === "checkbox" ? checked : value,
    }));
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!form.declaration) {
      alert("Please confirm the declaration before submitting.");
      return;
    }
    // Phase 1: no backend yet — just simulate success
    setSubmitted(true);
  };

  if (submitted) {
    return (
      <div style={{ fontFamily: "sans-serif", padding: 20 }}>
        <h2>Request submitted successfully.</h2>
        <p><strong>Request ID:</strong> TR-{Math.floor(Math.random() * 900 + 100)}</p>
        <p><strong>Status:</strong> ● Pending Registrar Approval</p>
        <button onClick={() => navigate("/citizen/dashboard")} style={{ padding: "8px 16px", marginTop: 12 }}>
          Back to Dashboard
        </button>
      </div>
    );
  }

  return (
    <div style={{ fontFamily: "sans-serif", padding: 20, maxWidth: 400 }}>
      <h2>Transfer Land Ownership</h2>
      <form onSubmit={handleSubmit}>
        <label>Parcel ID</label>
        <select name="parcelId" value={form.parcelId} onChange={handleChange} style={{ width: "100%", padding: 8, marginBottom: 12 }} required>
          <option value="">Select a parcel</option>
          {parcels.map((p) => (
            <option key={p.id} value={p.id}>{p.id}</option>
          ))}
        </select>

        <label>Current Owner</label>
        <input name="currentOwner" value={form.currentOwner} onChange={handleChange} style={{ width: "100%", padding: 8, marginBottom: 12 }} required />

        <label>New Owner</label>
        <input name="newOwner" value={form.newOwner} onChange={handleChange} style={{ width: "100%", padding: 8, marginBottom: 12 }} required />

        <label>Transfer Reason</label>
        <select name="reason" value={form.reason} onChange={handleChange} style={{ width: "100%", padding: 8, marginBottom: 12 }}>
          <option>Sale</option>
          <option>Inheritance</option>
          <option>Gift</option>
        </select>

        <label>Upload Document</label>
        <input type="file" style={{ width: "100%", marginBottom: 12 }} />

        <label style={{ display: "block", marginBottom: 16 }}>
          <input type="checkbox" name="declaration" checked={form.declaration} onChange={handleChange} />
          {" "}I confirm that the information is correct.
        </label>

        <button type="submit" style={{ padding: "10px 20px", width: "100%" }}>Submit Request</button>
      </form>
    </div>
  );
}