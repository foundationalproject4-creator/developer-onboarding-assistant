import './sections.css'

export default function ImportantFiles({ data }) {
  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Important Files</h2>
        <p>Key files to read first when onboarding to this project.</p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {data.map(file => (
          <div key={file.path} className="card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
              <span className="filepath">{file.path}</span>
              <span className="badge badge-accent">{file.role}</span>
            </div>
            <p style={{ fontSize: 14, color: 'var(--text)', lineHeight: 1.65, margin: 0 }}>
              {file.description}
            </p>
          </div>
        ))}
      </div>
    </div>
  )
}
