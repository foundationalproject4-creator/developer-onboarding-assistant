import './sections.css'

export default function ProjectOverview({ data }) {
  const {
    name, description, language, license, stars, forks, openIssues, lastUpdated, topics,
  } = data

  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Project Overview</h2>
        <p>High-level summary of the repository.</p>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 16, flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontFamily: 'var(--mono)', fontWeight: 600, fontSize: 18, color: 'var(--text-h)', marginBottom: 8 }}>
              {name}
            </div>
            <p style={{ fontSize: 15, lineHeight: 1.65, color: 'var(--text)', maxWidth: 620 }}>{description}</p>
          </div>
        </div>

        <div className="badge-row" style={{ marginTop: 16 }}>
          <span className="badge badge-accent">⬡ {language}</span>
          <span className="badge badge-neutral">⚖ {license}</span>
          <span className="badge badge-neutral">★ {stars}</span>
          <span className="badge badge-neutral">⑂ {forks} forks</span>
          <span className="badge badge-neutral">◎ {openIssues} open issues</span>
          <span className="badge badge-neutral">Updated {lastUpdated}</span>
        </div>
      </div>

      <div className="card">
        <div style={{ fontWeight: 600, fontSize: 14, color: 'var(--text-h)', marginBottom: 12 }}>Topics</div>
        <div className="badge-row" style={{ marginTop: 0 }}>
          {topics.map(t => (
            <span key={t} className="badge badge-blue">{t}</span>
          ))}
        </div>
      </div>
    </div>
  )
}
