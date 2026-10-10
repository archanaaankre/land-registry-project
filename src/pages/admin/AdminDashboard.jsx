import { useRegistry } from "../../context/RegistryContext";

export default function AdminDashboard() {
  const { parcelList, requestList, disputeList } = useRegistry();

  return (
    <div style={{ fontFamily: "sans-serif", padding: 20 }}>
      <h2>Admin Dashboard</h2>

      <div style={{ display: "flex", gap: 16, margin: "20px 0" }}>
        <div style={{ border: "1px solid #ccc", padding: 16, borderRadius: 8 }}>
          Total Parcels: {parcelList.length}
        </div>
        <div style={{ border: "1px solid #ccc", padding: 16, borderRadius: 8 }}>
          Total Requests: {requestList.length}
        </div>
        <div style={{ border: "1px solid #ccc", padding: 16, borderRadius: 8 }}>
          Total Disputes: {disputeList.length}
        </div>
      </div>

      
    </div>
  );
}