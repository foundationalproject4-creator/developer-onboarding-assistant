import './sections.css'

export default function Architecture({ data }) {
  const { summary, diagram, components } = data

  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Architecture</h2>
        <p>High-level system design and component responsibilities.</p>
      </div>

      {/* Summary */}
      <div className="card" style={{ marginBottom: 16 }}>
        <p style={{ fontSize: 15, color: 'var(--text)', lineHeight: 1.75, margin: 0 }}>{summary}</p>
      </div>

      {/* Diagram — wrapped in terminal-style code block */}
      <div className="arch-diagram-wrap" style={{ marginBottom: 16 }}>
        <div className="code-block" style={{ margin: 0, borderRadius: 0, border: 'none' }}>
          <code>{diagram}</code>
        </div>
      </div>

      {/* Component responsibilities */}
      <div className="card">
        <div className="section-label" style={{ marginBottom: 16 }}>Component Responsibilities</div>
        <div>
          {components.map(c => (
            <div key={c.name} className="arch-component-row">
              <span className="badge badge-accent" style={{ flexShrink: 0, marginTop: 1 }}>{c.name}</span>
              <span style={{ fontSize: 14, color: 'var(--text)', lineHeight: 1.6 }}>{c.responsibility}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
