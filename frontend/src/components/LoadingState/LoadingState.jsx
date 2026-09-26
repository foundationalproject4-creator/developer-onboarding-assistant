import { useState, useEffect } from 'react'
import './LoadingState.css'

const STEPS = [
  'Cloning repository',
  'Parsing file structure',
  'Detecting tech stack',
  'Analyzing architecture',
  'Generating insights',
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
      <div className="loading-spinner-wrap" aria-hidden="true">
        <div className="loading-spinner" />
        <div className="loading-pulse" />
      </div>

      <div className="loading-text">
        <h3>Analyzing Repository</h3>
        <p>{STEPS[activeStep]}…</p>
      </div>

      <div className="loading-steps" aria-hidden="true">
        {STEPS.map((step, i) => (
          <span
            key={step}
            className={
              'loading-step' +
              (i < activeStep ? ' done' : i === activeStep ? ' active' : '')
            }
          >
            {i < activeStep ? '✓ ' : ''}{step}
          </span>
        ))}
      </div>
    </div>
  )
}
