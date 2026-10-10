import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { transferRequests } from "../../data/sampleData";

export default function Verification() {
  const { id } = useParams();
  const navigate = useNavigate();
  const request = transferRequests.find((r) => r.id === id);
  const [decision, setDecision] = useState(null);

  if (!request) {
    return <div style={{ padding: 20 }}>Request not found.</div>;
  }

  const handleDecision = (choice) => {
    // Phase 1: local only — doesn't persist to sampleData yet.
    // Real persistence comes in Phase 2 with Context.
    setDecision(choice);
  };

  if (decision) {
    return (
      <div style={{ fontFamily: "sans-serif", padding: 20 }}>
        <h2>Request {decision === "approve" ? "Approved" : "Rejected"}</h2>
        {decision === "approve" && (
          <>
            <p><strong>Blockchain Transaction:</strong> TXN-{Math.random().toString(36).slice(2, 8).toUpperCase()}</p>
            <p><strong>Status:</strong> ✓ Committed</p>
          </>
        )}
        <button onClick={() => navigate("/registrar/dashboard")} style={{ padding: "8px 16px", marginTop: 12 }}>
          Back to Dashboard
        </button>
      </div>
    );
  }

  return (
    <div style={{ fontFamily: "sans-serif", padding: 20, maxWidth: 400 }}>
      <h2>Transfer Request Verification</h2>
      <p><strong>Request ID:</strong> {request.id}</p>
      <p><strong>Parcel ID:</strong> {request.parcelId}</p>
      <p><strong>Current Owner:</strong> {request.from}</p>
      <p><strong>New Owner:</strong> {request.to}</p>

      <div style={{ margin: "16px 0" }}>
        <p>✓ Sale Agreement</p>
        <p>✓ Identity Document</p>
        <p>✓ Document Integrity Verified</p>
        <p>✓ Current owner verified</p>
      </div>

      <button onClick={() => handleDecision("reject")} style={{ padding: "10px 20px", marginRight: 12 }}>
        Reject
      </button>
      <button onClick={() => handleDecision("approve")} style={{ padding: "10px 20px" }}>
        Approve
      </button>
    </div>
  );
}