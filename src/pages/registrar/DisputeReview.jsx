import { useRegistry } from "../../context/RegistryContext";
import StatusBadge from "../../components/StatusBadge";

export default function DisputeReview() {
  const { disputeList, updateDisputeStatus } = useRegistry();

  return (
    <div style={{ fontFamily: "sans-serif", padding: 20 }}>
      <h2>Dispute Review</h2>

      <table border="1" cellPadding="8" style={{ borderCollapse: "collapse", width: "100%" }}>
        <thead>
          <tr>
            <th>Dispute ID</th>
            <th>Parcel</th>
            <th>Reason</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody>
          {disputeList.map((d) => (
            <tr key={d.id}>
              <td>{d.id}</td>
              <td>{d.parcelId}</td>
              <td>{d.reason}</td>
              <td><StatusBadge status={d.status} /></td>
              <td>
                {d.status === "Pending" ? (
                  <>
                    <button
                      onClick={() => updateDisputeStatus(d.id, "Resolved")}
                      style={{ marginRight: 8, padding: "4px 10px" }}
                    >
                      Resolve
                    </button>
                    <button
                      onClick={() => updateDisputeStatus(d.id, "Rejected")}
                      style={{ padding: "4px 10px" }}
                    >
                      Reject
                    </button>
                  </>
                ) : (
                  <span>—</span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}