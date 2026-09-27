import { useState } from 'react'
import RepoInput from './components/RepoInput/RepoInput'
import LoadingState from './components/LoadingState/LoadingState'
import Dashboard from './components/Dashboard/Dashboard'
import { fetchOnboardingData } from './data/mockData'
import './App.css'

/**
 * App state machine:
 *   idle ──[submit]──▶ loading ──[success]──▶ result
 *                              └──[error]──▶  error ──[retry]──▶ idle
 */
export default function App() {
  const [appState, setAppState] = useState('idle')   // 'idle' | 'loading' | 'result' | 'error'
  const [onboardingData, setOnboardingData] = useState(null)
  const [errorMsg, setErrorMsg] = useState('')

  async function handleAnalyze(url) {
    setErrorMsg('')
    setAppState('loading')
    try {
      const data = await fetchOnboardingData(url)
      setOnboardingData(data)
      setAppState('result')
    } catch (err) {
      setErrorMsg(err?.message ?? 'Something went wrong. Please try again.')
      setAppState('error')
    }
  }

  const isLoading = appState === 'loading'

  return (
    <div className="app-layout">
      {/* ── Header ── */}
      <header className="app-header">
        <div className="app-header-inner">
          <div className="app-brand">
            {/* SVG hex logo */}
            <svg className="app-brand-logo" viewBox="0 0 32 32" fill="none" aria-hidden="true" xmlns="http://www.w3.org/2000/svg">
              <path
                d="M16 2L28.124 9V23L16 30L3.876 23V9L16 2Z"
                fill="var(--accent-bg)"
                stroke="var(--accent)"
                strokeWidth="1.5"
              />
              <path
                d="M11 13l3 3-3 3M17 19h4"
                stroke="var(--accent)"
                strokeWidth="1.75"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="app-brand-name">Developer Onboarding Assistant</span>
          </div>

          <div className="app-header-right">
            <div className="app-header-badge">
              <span className="app-header-badge-dot" aria-hidden="true" />
              AI-powered
            </div>
          </div>
        </div>
      </header>

      {/* ── Main content area ── */}
      <div className="app-body">
        {appState === 'idle' && (
          <section className="app-hero" aria-label="Get started">
            <div className="app-hero-content">
              <div className="app-hero-eyebrow" aria-hidden="true">
                <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor">
                  <circle cx="5" cy="5" r="5" />
                </svg>
                IBM watsonx.ai · Repository Analysis
              </div>

              <h1 className="app-hero-title">
                Understand Any<br />
                <span>Codebase in Minutes</span>
              </h1>

              <p className="app-hero-subtitle">
                AI-powered repository analysis that turns unfamiliar codebases into
                structured developer onboarding guides — automatically.
              </p>

              <div className="app-hero-input-area">
                <RepoInput onSubmit={handleAnalyze} isLoading={isLoading} />
              </div>

              <div className="app-hero-capabilities" aria-label="Included in every guide">
                {[
                  'Architecture',
                  'Tech Stack',
                  'Important Files',
                  'Setup Guide',
                  'Dev Workflow',
                  'Starter Tasks',
                  'Project Structure',
                ].map(label => (
                  <span key={label} className="app-hero-cap">
                    <span className="app-hero-cap-check" aria-hidden="true">✓</span>
                    {label}
                  </span>
                ))}
              </div>
            </div>
          </section>
        )}

        {appState === 'loading' && <LoadingState />}

        {appState === 'error' && (
          <div className="app-error" role="alert">
            <div className="app-error-card">
              <div className="app-error-icon-wrap" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
              </div>
              <h2 className="app-error-title">Analysis failed</h2>
              <p className="app-error-msg">{errorMsg}</p>
              <button
                className="app-retry-btn"
                onClick={() => setAppState('idle')}
                type="button"
              >
                Try again
              </button>
            </div>
          </div>
        )}

        {appState === 'result' && onboardingData && (
          <Dashboard data={onboardingData} />
        )}
      </div>
    </div>
  )
}
