import { Link } from "react-router-dom";

export default function Landing() {
  return (
    <div style={{ textAlign: "center", padding: "60px 20px", fontFamily: "sans-serif" }}>
      <h1>BLOCKCHAIN LAND REGISTRY</h1>
      <p>Secure • Transparent • Traceable</p>
      <p>A blockchain-based platform for secure and verifiable land records.</p>
      <div style={{ marginTop: 24 }}>
        <Link to="/login">
          <button style={{ marginRight: 12, padding: "10px 20px" }}>Get Started</button>
        </Link>
        <Link to="/login">
          <button style={{ padding: "10px 20px" }}>Login</button>
        </Link>
      </div>
      <div style={{ marginTop: 60 }}>
        <h3>Why Blockchain?</h3>
        <ul style={{ listStyle: "none", padding: 0 }}>
          <li>✓ Tamper-evident records</li>
          <li>✓ Transparent transaction history</li>
          <li>✓ Secure access control</li>
          <li>✓ Document integrity verification</li>
        </ul>
      </div>
    </div>
  );
}