/**
 * Trust-signal UI: a source badge plus a collapsible "Why trust this?" panel.
 *
 * Every value rendered here comes from fields the backend ALREADY returns in
 * `OnboardingKnowledge` (see ai/schemas.py):
 *
 *   - used_llm                 global: True only when the Anthropic LLM path
 *                               ran and succeeded
 *   - data_completeness_notes  "<field>: <why that field is not grounded>"
 *   - important_files[].path   real paths the repository analyzer detected
 *
 * Deliberate limits
 * -----------------
 * 1. Never "AI-verified". Nothing in this pipeline verifies generated text
 *    against the source repository, so the strongest honest label is
 *    "AI-generated". Verified would be a lie.
 * 2. Never invent evidence. File names are only ever rendered from
 *    `important_files`; when that list is empty the panel says so instead.
 * 3. Per-section mode is only claimed where the data supports it. The mode is
 *    global (one `used_llm` for the whole response); per-section claims are
 *    derived from that flag plus the section's own completeness notes, and the
 *    architecture diagram is special-cased because ai/diagram.py generates it
 *    deterministically on both the LLM and the fallback path.
 */

import './AnalysisSource.css'

const MAX_EVIDENCE_FILES = 8;

/** Human label for the completeness-note prefix of each field. */
const FIELD_LABELS = {
  project_overview: 'Project overview',
  architecture: 'Architecture summary',
  architecture_diagram: 'Architecture diagram',
  dependencies: 'Dependencies',
  important_files: 'Important files',
  starter_tasks: 'Starter tasks',
  setup_guide: 'Setup guide',
  development_workflow: 'Development workflow',
  tech_stack: 'Tech stack',
};

function notesFor(analysis, field) {
  const notes = analysis?.data_completeness_notes;
  if (!Array.isArray(notes)) return [];
  return notes.filter((n) => typeof n === 'string' && n.startsWith(`${field}:`));
}

function detectedFiles(analysis) {
  const files = analysis?.important_files;
  if (!Array.isArray(files)) return [];
  return files
    .map((f) => (typeof f === 'string' ? f : f?.path))
    .filter((p) => typeof p === 'string' && p.length > 0);
}

/**
 * Badge for a section, derived only from real metadata.
 * Returns null when nothing truthful can be said.
 */
function badgeFor(analysis, field) {
  const notes = notesFor(analysis, field);

  // Nothing was detected, so there is no pattern to have matched. This is
  // checked before the diagram special case below, otherwise an "unknown"
  // diagram would still be labelled Pattern-matched.
  if (notes.length > 0) {
    return { icon: '⚠️', label: 'No data detected', tone: 'orange' };
  }

  // The diagram never comes from the LLM: ai/generator.py calls
  // generate_architecture_diagram() on both paths, so this holds regardless
  // of used_llm.
  if (field === 'architecture_diagram') {
    return { icon: '🔎', label: 'Pattern-matched', tone: 'blue' };
  }

  // These file paths come straight from the analyzer, independent of the LLM.
  if (field === 'important_files') {
    return { icon: '📋', label: 'Repository-derived', tone: 'green' };
  }

  if (analysis?.used_llm === true) {
    return { icon: '⚡', label: 'AI-generated', tone: 'accent' };
  }

  return { icon: '📋', label: 'Rule-based', tone: 'neutral' };
}

function reasonsFor(analysis, field) {
  const reasons = [];
  const label = FIELD_LABELS[field] || field;
  const notes = notesFor(analysis, field);
  const files = detectedFiles(analysis);

  if (field === 'architecture_diagram') {
    reasons.push(
      notes.length > 0
        ? 'The diagram is produced by the deterministic diagram generator, never by the LLM — but no structural signal was recognised for this repository.'
        : 'The diagram is generated deterministically from detected structure and dependencies — it is never written by the LLM.'
    );
  } else if (analysis?.used_llm === true) {
    reasons.push(
      `${label} was written by the Anthropic Claude model from the repository analyzer's output. It is AI-generated, not independently verified.`
    );
  } else {
    reasons.push(
      `${label} was assembled by the rule-based fallback from the repository analyzer's output. The LLM path was not used for this result.`
    );
  }

  for (const note of notes) {
    reasons.push(note.replace(/^[^:]+:\s*/, ''));
  }

  return { reasons, files };
}

export default function AnalysisSource({ analysis, field }) {
  if (!analysis) return null;

  const badge = badgeFor(analysis, field);
  if (!badge) return null;

  const { reasons, files } = reasonsFor(analysis, field);
  const shown = files.slice(0, MAX_EVIDENCE_FILES);
  const remaining = files.length - shown.length;

  return (
    <details className="trust">
      <summary className={`trust-badge badge badge-${badge.tone}`}>
        <span aria-hidden="true">{badge.icon}</span>
        <span>{badge.label}</span>
      </summary>

      <div className="trust-panel">
        <p className="trust-title">Why trust this?</p>
        <ul className="trust-reasons">
          {reasons.map((reason, i) => (
            <li key={i}>{reason}</li>
          ))}
        </ul>

        <p className="trust-title">Detected files this analysis is based on</p>
        {files.length > 0 ? (
          <ul className="trust-files">
            {shown.map((path) => (
              <li key={path}>
                <code>{path}</code>
              </li>
            ))}
            {remaining > 0 && <li className="trust-more">+{remaining} more</li>}
          </ul>
        ) : (
          <p className="trust-none">
            No files were flagged as important by the repository analyzer, so there
            is no file-level evidence to show for this section.
          </p>
        )}
      </div>
    </details>
  );
}
