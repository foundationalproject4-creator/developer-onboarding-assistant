import { useState, useEffect } from 'react'
import './LoadingState.css'

const STEPS = [
  { label: 'Scanning repository',       icon: 'scan' },
  { label: 'Detecting technologies',    icon: 'tech' },
  { label: 'Mapping project structure', icon: 'map' },
  { label: 'Analyzing architecture',    icon: 'arch' },
  { label: 'Generating onboarding guide', icon: 'gen' },
]

export default function LoadingState() {
  const [activeStep, setActiveStep] = useState(0)

  useEffect(() => {
    const id = setInterval(() => {
      setActiveStep(s => Math.min(s + 1, STEPS.length - 1))
    }, 550)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="loading-root" role="status" aria-live="polite" aria-label="Analyzing repository">
      {/* Animated hex logo */}
      <div className="loading-logo-wrap" aria-hidden="true">
        <svg className="loading-hex" viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path
            className="loading-hex-bg"
            d="M32 4L58.248 18V46L32 60L5.752 46V18L32 4Z"
          />
          <path
            className="loading-hex-ring"
            d="M32 4L58.248 18V46L32 60L5.752 46V18L32 4Z"
          />
          <path
            className="loading-hex-code"
            d="M22 26l7 6-7 6M34 38h8"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <div className="loading-hex-pulse" />
      </div>

      <div className="loading-text">
        <h2 className="loading-title">Analyzing Repository</h2>
        <p className="loading-subtitle" aria-live="polite">
          {STEPS[activeStep].label}&hellip;
        </p>
      </div>

      {/* Progress bar */}
      <div className="loading-progress-wrap" aria-hidden="true">
        <div
          className="loading-progress-bar"
          style={{ width: `${((activeStep + 1) / STEPS.length) * 100}%` }}
        />
      </div>

      {/* Steps list */}
      <ol className="loading-steps" aria-hidden="true">
        {STEPS.map((step, i) => {
          const state = i < activeStep ? 'done' : i === activeStep ? 'active' : 'pending'
          return (
            <li key={step.label} className={`loading-step loading-step--${state}`}>
              <span className="loading-step-indicator">
                {state === 'done' ? (
                  <svg viewBox="0 0 12 12" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M2.5 6l2.5 2.5 4.5-5" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" stroke="currentColor" />
                  </svg>
                ) : state === 'active' ? (
                  <span className="loading-step-dot" />
                ) : (
                  <span className="loading-step-num">{i + 1}</span>
                )}
              </span>
              <span className="loading-step-label">{step.label}</span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
