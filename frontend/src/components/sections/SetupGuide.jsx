import { useState } from 'react'
import './sections.css'

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1800)
    })
  }

  return (
    <button
      className={`copy-btn${copied ? ' copied' : ''}`}
      onClick={handleCopy}
      aria-label={copied ? 'Copied to clipboard' : 'Copy command'}
      type="button"
    >
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  )
}

export default function SetupGuide({ data }) {
  // `data` is List[str] — each string is one setup instruction
  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Setup Guide</h2>
        <p>Step-by-step instructions to get the project running locally.</p>
      </div>

      <ol className="step-list">
        {(data ?? []).map((instruction, i) => (
          <li key={i} className="step-item">
            <span className="step-number" aria-hidden="true">{i + 1}</span>
            <div className="step-body">
              <div className="code-block">
                <CopyButton text={instruction} />
                <code>{instruction}</code>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
