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
        <form onSubmit={handleSubmit} noValidate aria-label="Analyze repository">
          <label htmlFor="repo-url" className="repo-input-label">
            Repository URL
          </label>
          <div className="repo-input-row">
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
              aria-label={isLoading ? 'Analyzing…' : 'Analyze Repository'}
            >
              {isLoading ? 'Analyzing…' : 'Analyze Repository'}
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
