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
      aria-label={copied ? 'Copied' : 'Copy commands'}
      type="button"
    >
      {copied ? '✓ Copied' : 'Copy'}
    </button>
  )
}

export default function SetupGuide({ data }) {
  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Setup Guide</h2>
        <p>Step-by-step instructions to get the project running locally.</p>
      </div>

      <ol className="step-list">
        {data.map(step => (
          <li key={step.step} className="step-item">
            <span className="step-number" aria-hidden="true">{step.step}</span>
            <div className="step-body">
              <h4>{step.title}</h4>
              <div className="code-block">
                <CopyButton text={step.commands.join('\n')} />
                <code>{step.commands.join('\n')}</code>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </div>
  )
}
