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
      }}
    >
      {children}
    </RegistryContext.Provider>
  );
}

export function useRegistry() {
  return useContext(RegistryContext);
}