import './sections.css'

export default function Architecture({ data }) {
  const { summary, diagram, components } = data

  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Architecture</h2>
        <p>High-level system design and component responsibilities.</p>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <p style={{ fontSize: 15, color: 'var(--text)', lineHeight: 1.7, margin: 0 }}>{summary}</p>
      </div>

      <div className="code-block" style={{ marginBottom: 16 }}>
        <code>{diagram}</code>
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-h)', marginBottom: 14 }}>
          Component Responsibilities
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {components.map(c => (
            <div key={c.name} style={{ display: 'flex', gap: 14, alignItems: 'flex-start' }}>
              <span className="badge badge-accent" style={{ flexShrink: 0, marginTop: 2 }}>{c.name}</span>
              <span style={{ fontSize: 14, color: 'var(--text)', lineHeight: 1.6 }}>{c.responsibility}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
