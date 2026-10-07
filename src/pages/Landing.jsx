import { Link } from "react-router-dom";

export default function Landing() {
  return (
    <div
      style={{
        minHeight: "100vh",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        textAlign: "center",
        fontFamily: "sans-serif",
      }}
    >
      <div>
        <h1 style={{ fontSize: "42px", marginBottom: "35px" }}>
          BLOCKCHAIN ACCESS CONTROL SYSTEM
        </h1>

        <div>
          <Link to="/login">
            <button
              style={{
                marginRight: "12px",
                padding: "12px 25px",
                fontSize: "16px",
                cursor: "pointer",
              }}
            >
              Get Started
            </button>
          </Link>

          <Link to="/login">
            <button
              style={{
                padding: "12px 25px",
                fontSize: "16px",
                cursor: "pointer",
              }}
            >
              Login
            </button>
          </Link>
        </div>
      </div>
    </div>
  );
}