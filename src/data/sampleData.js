export const currentUser = { name: "Archana", role: "Citizen" };

export const parcels = [
  { id: "LP-001", location: "Indore", area: "1200 sq.ft", status: "Registered", owner: "Sample User" },
  { id: "LP-002", location: "Ujjain", area: "1800 sq.ft", status: "Registered", owner: "Sample Buyer" },
  { id: "LP-003", location: "Bhopal", area: "950 sq.ft", status: "Pending", owner: "Sample Seller" },
];

export const transferRequests = [
  { id: "TR-001", parcelId: "LP-001", from: "Sample Seller", to: "Sample Buyer", status: "Completed" },
  { id: "TR-002", parcelId: "LP-002", from: "Owner A", to: "Owner B", status: "Pending" },
];

export const disputes = [
  { id: "DP-001", parcelId: "LP-003", reason: "Incorrect area recorded", status: "Pending" },
];

export const transactions = [
  { txnId: "TXN-8F72A91", parcelId: "LP-001", action: "Ownership Transfer", status: "Confirmed", block: "#1042" },
];
