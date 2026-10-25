import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './App.css'
import { AuthProvider } from './context/AuthContext.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'
import AppLayout from './components/layout/AppLayout.jsx'
import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Parcels from './pages/Parcels.jsx'
import ParcelDetails from './pages/ParcelDetails.jsx'
import EvaluationDashboard from './pages/EvaluationDashboard.jsx'
import TransferRequests from './pages/TransferRequests.jsx'
import TransferRequestDetails from './pages/TransferRequestDetails.jsx'
import RegistrarTransfers from './pages/RegistrarTransfers.jsx'
import Landing from './pages/Landing.jsx'

const supportedRoles = ['CITIZEN', 'REGISTRAR', 'ADMIN']

function AppRoutes() {
  return (
    <Routes>
      <Route element={<Landing />} path="/" />
      <Route element={<Login />} path="/login" />
      <Route element={<Register />} path="/register" />
      <Route element={<Navigate replace to="/" />} path="/health" />
      <Route element={<ProtectedRoute allowedRoles={supportedRoles} />}>
        <Route element={<AppLayout />}>
          <Route element={<Dashboard />} path="dashboard" />
          <Route element={<Parcels />} path="parcels" />
          <Route element={<ParcelDetails />} path="parcels/:parcelId" />
          <Route element={<EvaluationDashboard />} path="evaluation" />
          <Route element={<TransferRequests />} path="transfers" />
          <Route element={<TransferRequestDetails />} path="transfers/:requestId" />
          <Route element={<ProtectedRoute allowedRoles={['REGISTRAR']} />} path="registrar/transfers">
            <Route element={<RegistrarTransfers />} index />
          </Route>
        </Route>
      </Route>
      <Route element={<Navigate replace to="/" />} path="*" />
    </Routes>
  )
}

function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  )
}

export default App
