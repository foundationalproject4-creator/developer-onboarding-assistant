import './sections.css'

export default function DevWorkflow({ data }) {
  const { summary, steps, conventions } = data

  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Development Workflow</h2>
        <p>How the team works together — branching, commits, and reviews.</p>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <p style={{ fontSize: 15, color: 'var(--text)', lineHeight: 1.7, margin: 0 }}>{summary}</p>
      </div>

      <ol className="step-list" style={{ marginBottom: 20 }}>
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

      <div className="card">
        <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-h)', marginBottom: 12 }}>
          Team Conventions
        </div>
        <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
          {conventions.map((c, i) => (
            <li key={i} style={{ display: 'flex', gap: 10, fontSize: 14, color: 'var(--text)', lineHeight: 1.6 }}>
              <span style={{ color: 'var(--accent)', flexShrink: 0 }}>→</span>
              {c}
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}
