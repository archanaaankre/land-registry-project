import { createContext, useContext, useState } from "react";
import { parcels, transferRequests, disputes } from "../data/sampleData";

const RegistryContext = createContext(null);

export function RegistryProvider({ children }) {
  const [parcelList, setParcelList] = useState(parcels);
  const [requestList, setRequestList] = useState(transferRequests);
  const [disputeList, setDisputeList] = useState(disputes);

  const updateRequestStatus = (id, newStatus) => {
    setRequestList((prev) =>
      prev.map((r) => (r.id === id ? { ...r, status: newStatus } : r))
    );
  };

  const addDispute = (parcelId, reason) => {
    const newId = `DP-${String(disputeList.length + 1).padStart(3, "0")}`;
    setDisputeList((prev) => [
      ...prev,
      { id: newId, parcelId, reason, status: "Pending" },
    ]);
    return newId;
  };

  const updateDisputeStatus = (id, newStatus) => {
    setDisputeList((prev) =>
      prev.map((d) => (d.id === id ? { ...d, status: newStatus } : d))
    );
  };

  return (
    <RegistryContext.Provider
      value={{
        parcelList,
        setParcelList,
        requestList,
        setRequestList,
        disputeList,
        setDisputeList,
        updateRequestStatus,
        addDispute,
        updateDisputeStatus,
      }}
    >
      {children}
    </RegistryContext.Provider>
  );
}

export function useRegistry() {
  return useContext(RegistryContext);
}