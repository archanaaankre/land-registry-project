import { BrowserRouter, Routes, Route } from "react-router-dom";
import { RegistryProvider } from "./context/RegistryContext";
import Layout from "./components/Layout";

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

          {/* Citizen routes — wrapped in Layout */}
          <Route path="/citizen/dashboard" element={<Layout role="Citizen"><CitizenDashboard /></Layout>} />
          <Route path="/citizen/parcels" element={<Layout role="Citizen"><ParcelSearch /></Layout>} />
          <Route path="/citizen/parcels/:id" element={<Layout role="Citizen"><ParcelDetails /></Layout>} />
          <Route path="/citizen/transfer" element={<Layout role="Citizen"><TransferRequest /></Layout>} />
          <Route path="/citizen/track" element={<Layout role="Citizen"><TrackStatus /></Layout>} />
          <Route path="/citizen/applications" element={<Layout role="Citizen"><MyApplications /></Layout>} />
          <Route path="/citizen/dispute" element={<Layout role="Citizen"><RaiseDispute /></Layout>} />
          <Route path="/citizen/transactions" element={<Layout role="Citizen"><Transactions /></Layout>} />

          {/* Registrar routes — wrapped in Layout */}
          <Route path="/registrar/dashboard" element={<Layout role="Registrar"><RegistrarDashboard /></Layout>} />
          <Route path="/registrar/requests" element={<Layout role="Registrar"><Requests /></Layout>} />
          <Route path="/registrar/requests/:id" element={<Layout role="Registrar"><RequestDetails /></Layout>} />
          <Route path="/registrar/verify/:id" element={<Layout role="Registrar"><Verification /></Layout>} />
          <Route path="/registrar/disputes" element={<Layout role="Registrar"><DisputeReview /></Layout>} />
        </Routes>
      </RegistryProvider>
    </BrowserRouter>
  );
}