export default function StatusBadge({ status }) {
  const className =
    status === "Completed" || status === "Resolved"
      ? "status-completed"
      : status === "Rejected"
      ? "status-rejected"
      : "status-pending";

  return <span className={className}>{status}</span>;
}