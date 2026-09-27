import { BrowserRouter, Routes, Route } from "react-router-dom";
import { RegistryProvider } from "./context/RegistryContext";

import Landing from "./pages/Landing";
import Login from "./pages/Login";

import CitizenDashboard from "./pages/citizen/CitizenDashboard";
import ParcelSearch from "./pages/citizen/ParcelSearch";
import ParcelDetails from "./pages/citizen/ParcelDetails";
import TransferRequest from "./pages/citizen/TransferRequest";
import TrackStatus from "./pages/citizen/TrackStatus";
import MyApplications from "./pages/citizen/MyApplications";
import RaiseDispute from "./pages/citizen/RaiseDispute";
import Transactions from "./pages/citizen/Transactions";

import RegistrarDashboard from "./pages/registrar/RegistrarDashboard";
import Requests from "./pages/registrar/Requests";
import RequestDetails from "./pages/registrar/RequestDetails";
import Verification from "./pages/registrar/Verification";
import DisputeReview from "./pages/registrar/DisputeReview";

export default function App() {
  return (
    <BrowserRouter>
      <RegistryProvider>
        <Routes>
          <Route path="/" element={<Landing />} />
          <Route path="/login" element={<Login />} />

          {/* Citizen routes */}
          <Route path="/citizen/dashboard" element={<CitizenDashboard />} />
          <Route path="/citizen/parcels" element={<ParcelSearch />} />
          <Route path="/citizen/parcels/:id" element={<ParcelDetails />} />
          <Route path="/citizen/transfer" element={<TransferRequest />} />
          <Route path="/citizen/track" element={<TrackStatus />} />
          <Route path="/citizen/applications" element={<MyApplications />} />
          <Route path="/citizen/dispute" element={<RaiseDispute />} />
          <Route path="/citizen/transactions" element={<Transactions />} />

          {/* Registrar routes */}
          <Route path="/registrar/dashboard" element={<RegistrarDashboard />} />
          <Route path="/registrar/requests" element={<Requests />} />
          <Route path="/registrar/requests/:id" element={<RequestDetails />} />
          <Route path="/registrar/verify/:id" element={<Verification />} />
          <Route path="/registrar/disputes" element={<DisputeReview />} />
        </Routes>
      </RegistryProvider>
    </BrowserRouter>
  );
}
