import Navbar from "./Navbar";
import Sidebar from "./Sidebar";

export default function Layout({ role, children }) {
  return (
    <div>
      <Navbar role={role} />
      <div style={{ display: "flex" }}>
        <Sidebar role={role} />
        <div style={{ flex: 1 }}>{children}</div>
      </div>
    </div>
  );
}