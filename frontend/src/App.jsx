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
            <span className="app-brand-icon" aria-hidden="true">⬡</span>
            <span className="app-brand-name">Developer Onboarding Assistant</span>
          </div>
          <div className="app-header-tagline">
            Understand any repository in seconds
          </div>
        </div>
      </header>

      {/* ── Repo input — always visible ── */}
      <RepoInput onSubmit={handleAnalyze} isLoading={isLoading} />

      {/* ── Main content area ── */}
      <div className="app-body">
        {appState === 'idle' && (
          <div className="app-empty">
            <div className="app-empty-icon" aria-hidden="true">⬡</div>
            <h2>Paste a repository URL to get started</h2>
            <p>
              Enter any public GitHub, GitLab, or Bitbucket repository URL above
              and click <strong>Analyze Repository</strong> to generate a complete
              onboarding guide.
            </p>
            <div className="app-empty-features">
              {[
                ['📋', 'Project Overview'],
                ['🔧', 'Tech Stack'],
                ['🗂', 'File Structure'],
                ['🏗', 'Architecture'],
                ['⚙️', 'Setup Guide'],
                ['🔀', 'Dev Workflow'],
                ['✅', 'Starter Tasks'],
              ].map(([icon, label]) => (
                <span key={label} className="app-empty-feature">
                  <span aria-hidden="true">{icon}</span> {label}
                </span>
              ))}
            </div>
          </div>
        )}

        {appState === 'loading' && <LoadingState />}

        {appState === 'error' && (
          <div className="app-error" role="alert">
            <div className="app-error-icon" aria-hidden="true">⚠</div>
            <h2>Analysis failed</h2>
            <p>{errorMsg}</p>
            <button
              className="app-retry-btn"
              onClick={() => setAppState('idle')}
              type="button"
            >
              Try again
            </button>
          </div>
        )}

        {appState === 'result' && onboardingData && (
          <Dashboard data={onboardingData} />
        )}
      </div>
    </div>
  )
}
