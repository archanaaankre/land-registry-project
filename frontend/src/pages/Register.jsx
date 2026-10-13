import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { useAuth } from '../context/useAuth.js'

export default function Register() {
  const { register, status } = useAuth()
  const navigate = useNavigate()
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [submitting, setSubmitting] = useState(false)

  if (status === 'authenticated') {
    return <Navigate to="/dashboard" replace />
  }

  if (status === 'loading') {
    return <main className="auth-page"><p role="status">Checking your session…</p></main>
  }

  async function handleSubmit(event) {
    event.preventDefault()
    setError('')
    setSubmitting(true)
    try {
      await register({ name, email, password })
      navigate('/dashboard', { replace: true })
    } catch (requestError) {
      setError(requestError.message)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="register-title">
        <p className="eyebrow">Land Registry System</p>
        <h1 id="register-title">Create an account</h1>
        <p className="auth-intro">Citizen registration is available online.</p>
        <form className="auth-form" onSubmit={handleSubmit}>
          <label htmlFor="register-name">Full name</label>
          <input
            autoComplete="name"
            id="register-name"
            maxLength={100}
            onChange={(event) => setName(event.target.value)}
            required
            type="text"
            value={name}
          />
          <label htmlFor="register-email">Email address</label>
          <input
            autoComplete="email"
            id="register-email"
            onChange={(event) => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
          <label htmlFor="register-password">Password</label>
          <input
            autoComplete="new-password"
            id="register-password"
            maxLength={128}
            minLength={8}
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="primary-button" disabled={submitting} type="submit">
            {submitting ? 'Creating account…' : 'Create citizen account'}
          </button>
        </form>
        <p className="auth-switch">
          Already registered? <Link to="/login">Sign in</Link>
        </p>
      </section>
    </main>
  )
}
