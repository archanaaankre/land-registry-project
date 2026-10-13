import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'

export default function ProtectedRoute({ allowedRoles }) {
  const { user, status, sessionError, retrySessionCheck } = useAuth()
  const location = useLocation()

  if (status === 'loading') {
    return <main className="auth-page"><p role="status">Checking your session…</p></main>
  }

  if (status === 'error') {
    return (
      <main className="auth-page">
        <section className="auth-card" role="alert">
          <h1>Could not verify your session</h1>
          <p>{sessionError}</p>
          <button className="primary-button" onClick={retrySessionCheck} type="button">
            Try again
          </button>
        </section>
      </main>
    )
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />
  }

  return <Outlet />
}
