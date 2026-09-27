import { useState } from 'react'
import './RepoInput.css'

// owner and repo segments must each be at least 1 non-slash, non-whitespace character
// and the URL must not end with just a trailing slash after the repo name
const URL_PATTERN = /^https?:\/\/(github\.com|gitlab\.com|bitbucket\.org)\/([^\s/]+)\/([^\s/]+?)\/?$/i

export default function RepoInput({ onSubmit, isLoading }) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')

  function validate(value) {
    if (!value.trim()) return 'Please enter a repository URL.'
    if (!URL_PATTERN.test(value.trim()))
      return 'Enter a valid GitHub, GitLab, or Bitbucket URL.'
    return ''
  }

  function handleSubmit(e) {
    e.preventDefault()
    const err = validate(url)
    if (err) { setError(err); return }
    setError('')
    onSubmit(url.trim())
  }

  function handleChange(e) {
    setUrl(e.target.value)
    if (error) setError('')
  }

  return (
    <div className="repo-input-wrapper">
      <div className="repo-input-inner">
        <form
          className="repo-input-form"
          onSubmit={handleSubmit}
          noValidate
          aria-label="Analyze repository"
        >
          <div className={`repo-input-row${error ? ' has-error' : ''}`}>
            {/* Git branch icon */}
            <span className="repo-input-icon" aria-hidden="true">
              <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="4" cy="3.5" r="1.5" />
                <circle cx="4" cy="12.5" r="1.5" />
                <circle cx="12" cy="5.5" r="1.5" />
                <path d="M4 5v5" />
                <path d="M12 7c0 3-3.5 4-8 4" />
              </svg>
            </span>

            <input
              id="repo-url"
              type="url"
              className="repo-input-field"
              placeholder="https://github.com/owner/repository"
              value={url}
              onChange={handleChange}
              disabled={isLoading}
              aria-describedby={error ? 'repo-url-error' : undefined}
              aria-invalid={!!error}
              autoComplete="off"
              spellCheck={false}
            />

            <button
              type="submit"
              className="repo-input-btn"
              disabled={isLoading}
              aria-label={isLoading ? 'Analyzing repository…' : 'Analyze Repository'}
            >
              <span className="repo-input-btn-inner">
                {isLoading && <span className="repo-input-spinner" aria-hidden="true" />}
                {isLoading ? 'Analyzing…' : 'Analyze Repository'}
              </span>
            </button>
          </div>

          {error && (
            <p id="repo-url-error" className="repo-input-error" role="alert">
              {error}
            </p>
          )}
        </form>
      </div>
    </div>
  )
}
