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

      {/* Main description card */}
      <div className="card po-hero-card" style={{ marginBottom: 16 }}>
        <div className="po-repo-name">{name}</div>
        <p className="po-repo-desc">{description}</p>

        <div className="badge-row" style={{ marginTop: 16 }}>
          <span className="badge badge-accent">{language}</span>
          <span className="badge badge-neutral">⚖ {license}</span>
          <span className="badge badge-neutral">★ {stars}</span>
          <span className="badge badge-neutral">⑂ {forks} forks</span>
          <span className="badge badge-neutral">◎ {openIssues} open issues</span>
          <span className="badge badge-neutral">Updated {lastUpdated}</span>
        </div>
      </div>

      {/* Topics */}
      <div className="card">
        <div className="section-label">Repository Topics</div>
        <div className="badge-row" style={{ marginTop: 0 }}>
          {topics.map(t => (
            <span key={t} className="badge badge-blue">{t}</span>
          ))}
        </div>
      </div>
    </div>
  )
}
