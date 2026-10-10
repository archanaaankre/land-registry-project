import { useEffect, useState } from 'react'
import './App.css'
import { apiGet } from './services/api.js'

function App() {
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

export default App
