import './sections.css'

const CATEGORY_BADGE = {
  Frontend: 'badge-blue',
  Backend: 'badge-green',
  'Build Tool': 'badge-neutral',
  Language: 'badge-accent',
  Server: 'badge-neutral',
  Analyzer: 'badge-orange',
  AI: 'badge-accent',
  Styling: 'badge-neutral',
}

export default function TechStack({ data }) {
  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Technology Stack</h2>
        <p>Libraries, frameworks, and tools used in this project.</p>
      </div>

      <div className="card-grid">
        {data.map(tech => (
          <div key={tech.name} className="card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
              <span style={{ fontWeight: 600, fontSize: 15, color: 'var(--text-h)' }}>{tech.name}</span>
              <span className={`badge ${CATEGORY_BADGE[tech.category] ?? 'badge-neutral'}`}>
                {tech.category}
              </span>
            </div>
            <p style={{ fontSize: 13, color: 'var(--text)', lineHeight: 1.6, margin: '0 0 10px' }}>
              {tech.description}
            </p>
            <span className="badge badge-neutral" style={{ fontFamily: 'var(--mono)' }}>
              v{tech.version}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}
