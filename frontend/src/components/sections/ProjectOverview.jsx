import AnalysisSource from '../common/AnalysisSource'
import './sections.css'

export default function ProjectOverview({ data, analysis }) {
  // `data` is the `project_overview` string from the backend
  // `analysis` is the full response, used only for provenance
  return (
    <div className="section-root po-section">
      <div className="section-header">
        <div className="section-title-row">
          <h2>Project Overview</h2>
          <AnalysisSource analysis={analysis} field="project_overview" />
        </div>
        <p>
          This dashboard turns an unfamiliar repository into a structured onboarding
          guide, so you can orient yourself in seconds instead of hours. The summary
          below is generated from the analysed codebase rather than written by hand.
        </p>
      </div>

      <div className="card po-overview-card">
        <p>{data || 'No overview available.'}</p>
      </div>
    </div>
  )
}
