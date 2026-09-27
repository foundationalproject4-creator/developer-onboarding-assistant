import './sections.css'

export default function DevWorkflow({ data }) {
  const { summary, steps, conventions } = data

  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Development Workflow</h2>
        <p>How the team works together — branching, commits, and reviews.</p>
      </div>

      {/* Summary */}
      <div className="card" style={{ marginBottom: 24 }}>
        <p style={{ fontSize: 15, color: 'var(--text)', lineHeight: 1.75, margin: 0 }}>{summary}</p>
      </div>

      {/* Steps */}
      <ol className="step-list" style={{ marginBottom: 24 }}>
        {steps.map(step => (
          <li key={step.step} className="step-item">
            <span className="step-number" aria-hidden="true">{step.step}</span>
            <div className="step-body">
              <h4>{step.title}</h4>
              <p>{step.detail}</p>
            </div>
          </li>
        ))}
      </ol>

      {/* Conventions */}
      <div className="card">
        <div className="section-label" style={{ marginBottom: 8 }}>Team Conventions</div>
        <ul style={{ margin: 0, padding: 0, listStyle: 'none' }}>
          {conventions.map((c, i) => (
            <li key={i} className="convention-item">
              <span className="convention-arrow" aria-hidden="true">→</span>
              {c}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
