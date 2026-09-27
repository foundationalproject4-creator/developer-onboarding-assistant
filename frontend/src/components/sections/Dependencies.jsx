import './sections.css'

const TYPE_BADGE = {
  prod:     'badge-green',
  dev:      'badge-neutral',
  peer:     'badge-blue',
  optional: 'badge-orange',
}

export default function Dependencies({ data }) {
  // `data` is List[DependencyExplanation]: [{name, purpose}]
  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Dependencies</h2>
        <p>Project dependencies and what they are used for.</p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {(data ?? []).map((dep, i) => (
          <div key={dep.name ?? i} className="card">
            <div className="if-card">
              <div className="if-card-body">
                <div className="if-card-path-row">
                  <span className="filepath">{dep.name}</span>
                  {dep.type && (
                    <span className={`badge ${TYPE_BADGE[dep.type] ?? 'badge-neutral'}`}>
                      {dep.type}
                    </span>
                  )}
                </div>
                <p className="if-card-desc">{dep.purpose}</p>
              </div>
            </div>
          </div>
        ))}
        {(!data || data.length === 0) && (
          <div className="card">
            <p style={{ color: 'var(--text-muted)', margin: 0 }}>No dependency information available.</p>
          </div>
        )}
      </div>
    </div>
  )
}
