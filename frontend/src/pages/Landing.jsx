import { Link } from 'react-router-dom'

const STEPS = [
  {
    title: 'Sign in and look up a parcel',
    text: 'Browse parcel details and ownership entries available in the registry application.',
  },
  {
    title: 'Submit an ownership-transfer request',
    text: 'Eligible users can submit a request through the transfer process.',
  },
  {
    title: 'An authorized registrar reviews the request',
    text: 'Registrar accounts can review requests using the protected review workflow.',
  },
  {
    title: 'Follow the request status',
    text: 'Review request history and its recorded status. Blockchain processing is not available in this build.',
  },
]

const FEATURES = [
  {
    title: 'Property records',
    text: 'Explore parcel information available in the application. No sample or fabricated property records are shown.',
  },
  {
    title: 'Ownership history',
    text: 'Review ownership entries returned by the API; these records are not independent proof of legal title.',
  },
  {
    title: 'Transfer tracking',
    text: 'Submit and follow transfer requests. Registrar approval alone does not complete a blockchain transfer.',
  },
  {
    title: 'Document integrity',
    text: 'Document upload, hashing, and verification are not implemented in this build.',
  },
]

export default function Landing() {
  return (
    <>
      <a className="skip-link" href="#landing-content">Skip to main content</a>
      <header className="app-header">
        <div className="app-header-inner">
          <Link className="brand" to="/">
            <span aria-hidden="true" className="brand-mark">LR</span>
            <span>Land Registry</span>
          </Link>
          <nav aria-label="Main navigation" className="landing-site-nav">
            <a href="#how-it-works-heading">How it works</a>
            <Link to="/login">Sign in</Link>
            <Link to="/register">Create account</Link>
          </nav>
        </div>
      </header>
      <main className="landing-page" id="landing-content">
        <section className="hero">
          <p className="eyebrow">Land record management</p>
          <h1 className="hero-title">Land records, made easier to understand.</h1>
          <p className="hero-intro">
            Explore a transparent land registry prototype designed to help users manage property records,
            review ownership history, and track transfer requests.
          </p>
          <div className="hero-actions">
            <Link className="primary-button" to="/parcels">Explore Land Records</Link>
            <Link className="secondary-button" to="/login">Sign In</Link>
          </div>
        </section>

      <section className="landing-section" aria-labelledby="how-it-works-heading">
        <h2 className="landing-section-title" id="how-it-works-heading">
          How it works
        </h2>
        <ol className="how-it-works">
          {STEPS.map((step) => (
            <li key={step.title}>
              <h3>{step.title}</h3>
              <p>{step.text}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="landing-section" aria-labelledby="features-heading">
        <h2 className="landing-section-title" id="features-heading">
          What this prototype covers
        </h2>
        <div className="feature-grid">
          {FEATURES.map((feature) => (
            <article className="feature-card" key={feature.title}>
              <h3>{feature.title}</h3>
              <p>{feature.text}</p>
            </article>
          ))}
        </div>
      </section>

        <section className="notice" aria-labelledby="transparency-heading">
          <h2 className="notice-title" id="transparency-heading">Academic prototype</h2>
          <p>
            This is not an official government service. It does not represent verified real-world property records,
            establish legal ownership, or claim production blockchain capabilities.
          </p>
        </section>
      </main>
      <footer className="app-footer">
        <div className="app-footer-inner">
          <p>Land Registry Management System - Academic prototype</p>
        </div>
      </footer>
    </>
  )
}
