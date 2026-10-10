import { useParams, Link } from "react-router-dom";
import { parcels } from "../../data/sampleData";

export default function ParcelDetails() {
  const { id } = useParams();
  const parcel = parcels.find((p) => p.id === id);

  if (!parcel) {
    return <div style={{ padding: 20 }}>Parcel not found.</div>;
  }

  return (
    <div style={{ fontFamily: "sans-serif", padding: 20 }}>
      <h2>Land Parcel Details</h2>
      <p><strong>Parcel ID:</strong> {parcel.id}</p>
      <p><strong>Location:</strong> {parcel.location}</p>
      <p><strong>Area:</strong> {parcel.area}</p>
      <p><strong>Status:</strong> {parcel.status}</p>
      <p><strong>Current Owner:</strong> {parcel.owner}</p>

      <div style={{ marginTop: 20 }}>
        <Link to="/citizen/transfer">
          <button style={{ padding: "8px 16px" }}>Request Transfer</button>
        </Link>
      </div>
    </div>
  );
}