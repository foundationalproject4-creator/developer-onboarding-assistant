import './sections.css'

const CATEGORY_BADGE = {
  language:     'badge-accent',
  framework:    'badge-blue',
  tool:         'badge-neutral',
  database:     'badge-green',
  ai:           'badge-accent',
  frontend:     'badge-blue',
  backend:      'badge-green',
  'build tool': 'badge-neutral',
  server:       'badge-neutral',
  analyzer:     'badge-orange',
  styling:      'badge-neutral',
}

export default function TechStack({ data }) {
  // `data` is List[TechStackItem]: [{name, category, role}]
  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Technology Stack</h2>
        <p>Libraries, frameworks, and tools used in this project.</p>
      </div>

      <div className="card-grid">
        {(data ?? []).map((tech, i) => (
          <div key={tech.name ?? i} className="card">
            <div className="ts-card-header">
              <span className="ts-card-name">{tech.name}</span>
              {tech.category && (
                <span className={`badge ${CATEGORY_BADGE[tech.category?.toLowerCase()] ?? 'badge-neutral'}`}>
                  {tech.category}
                </span>
              )}
            </div>
            <p className="ts-card-desc">{tech.role}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
