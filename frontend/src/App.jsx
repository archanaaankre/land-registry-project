import { useEffect, useState } from 'react'
import { BrowserRouter, Navigate, Outlet, Route, Routes } from 'react-router-dom'
import './App.css'
import { AuthProvider } from './context/AuthContext.jsx'
import ProtectedRoute from './components/ProtectedRoute.jsx'
import Login from './pages/Login.jsx'
import Register from './pages/Register.jsx'
import Dashboard from './pages/Dashboard.jsx'
import Parcels from './pages/Parcels.jsx'
import ParcelDetails from './pages/ParcelDetails.jsx'
import EvaluationDashboard from './pages/EvaluationDashboard.jsx'
import TransferRequests from './pages/TransferRequests.jsx'
import TransferRequestDetails from './pages/TransferRequestDetails.jsx'
import RegistrarTransfers from './pages/RegistrarTransfers.jsx'
import { apiGet } from './services/api.js'

const supportedRoles = ['CITIZEN', 'REGISTRAR', 'ADMIN']

function BackendStatus() {
  const [health, setHealth] = useState({ state: 'loading' })

  useEffect(() => {
    const controller = new AbortController()

    apiGet('/health', { signal: controller.signal })
      .then(({ data, status }) => {
        setHealth({ state: 'success', data, status })
      })
      .catch((error) => {
        if (error.name !== 'AbortError') {
          setHealth({ state: 'error', message: error.message, status: error.status })
        }
      })

    return () => controller.abort()
  }, [])

  return (
    <main className="health-page">
      <section className="health-card" aria-labelledby="page-title">
        <p className="eyebrow">Frontend connection test</p>
        <h1 id="page-title">Land Registry System</h1>
        <p className="intro">This is the frontend application.</p>

        {health.state === 'loading' && (
          <p className="connection-message" role="status">
            Connecting to the Flask backend…
          </p>
        )}

        {health.state === 'success' && (
          <div className="connection-result success" role="status">
            <h2>Backend connected successfully</h2>
            <dl>
              <div>
                <dt>HTTP status</dt>
                <dd>{health.status}</dd>
              </div>
              <div>
                <dt>Service status</dt>
                <dd>{health.data.status}</dd>
              </div>
              <div>
                <dt>Service</dt>
                <dd>{health.data.service}</dd>
              </div>
            </dl>
          </div>
        )}

        {health.state === 'error' && (
          <p className="connection-result error" role="alert">
            Backend connection failed{health.status ? ` (HTTP ${health.status})` : ''}:{' '}
            {health.message}
          </p>
        )}
      </section>
    </main>
  )
}

function AppRoutes() {
  return (
    <Routes>
      <Route element={<ProtectedRoute allowedRoles={supportedRoles} />}>
        <Route element={<Outlet />} path="/">
          <Route element={<Navigate replace to="/dashboard" />} index />
          <Route element={<Dashboard />} path="dashboard" />
          <Route element={<Parcels />} path="parcels" />
          <Route element={<ParcelDetails />} path="parcels/:parcelId" />
          <Route element={<EvaluationDashboard />} path="evaluation" />
          <Route element={<TransferRequests />} path="transfers" />
          <Route element={<TransferRequestDetails />} path="transfers/:requestId" />
          <Route
            element={<ProtectedRoute allowedRoles={['REGISTRAR']} />}
            path="registrar/transfers"
          >
            <Route element={<RegistrarTransfers />} index />
          </Route>
        </Route>
      </Route>
      <Route element={<Login />} path="/login" />
      <Route element={<Register />} path="/register" />
      <Route element={<BackendStatus />} path="/health" />
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
