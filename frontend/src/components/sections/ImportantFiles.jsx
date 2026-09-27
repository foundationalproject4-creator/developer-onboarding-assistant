import AnalysisSource from '../common/AnalysisSource'
import './sections.css'

export default function ImportantFiles({ data, analysis }) {
  // `data` is List[ImportantFileExplanation]: [{path, purpose}]
  return (
    <div className="section-root">
      <div className="section-header">
        <div className="section-title-row">
          <h2>Important Files</h2>
          <AnalysisSource analysis={analysis} field="important_files" />
        </div>
        <p>Key files to read first when onboarding to this project.</p>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {(data ?? []).map((file, i) => (
          <div key={file.path ?? i} className="card">
            <div className="if-card">
              <div className="if-card-icon" aria-hidden="true">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16H3.75A1.75 1.75 0 0 1 2 14.25V1.75Z" fill="var(--surface-2)" stroke="var(--border)" strokeWidth="1.25"/>
                </svg>
              </div>
              <div className="if-card-body">
                <div className="if-card-path-row">
                  <span className="filepath">{file.path}</span>
                </div>
                <p className="if-card-desc">{file.purpose}</p>
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
