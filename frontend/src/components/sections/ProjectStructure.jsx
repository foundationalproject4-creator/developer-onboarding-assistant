import './sections.css'

function TreeNode({ node, depth = 0 }) {
  const isDir = node.type === 'directory'

  return (
    <div>
      <div
        className="tree-node-row"
        style={{ paddingLeft: depth * 20 + 4 }}
      >
        {/* Indent guide lines */}
        {depth > 0 && (
          <span
            aria-hidden="true"
            style={{
              position: 'absolute',
              left: (depth - 1) * 20 + 12,
              top: 0,
              bottom: 0,
              width: '1px',
              background: 'var(--border)',
            }}
          />
        )}
        <span className="tree-node-icon" aria-hidden="true">
          {isDir ? (
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h2.764c.958 0 1.76.56 2.311 1.317l.139.183H13.5A1.5 1.5 0 0 1 15 5v7.5A1.5 1.5 0 0 1 13.5 14h-11A1.5 1.5 0 0 1 1 12.5v-9Z" fill="var(--accent-bg)" stroke="var(--accent-border)" strokeWidth="1.25"/>
            </svg>
          ) : (
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M2 1.75C2 .784 2.784 0 3.75 0h6.586c.464 0 .909.184 1.237.513l2.914 2.914c.329.328.513.773.513 1.237v9.586A1.75 1.75 0 0 1 13.25 16H3.75A1.75 1.75 0 0 1 2 14.25V1.75Z" fill="var(--surface-2)" stroke="var(--border)" strokeWidth="1.25"/>
            </svg>
          )}
        </span>
        <span style={{
          fontWeight: isDir ? 600 : 400,
          color: isDir ? 'var(--text-h)' : 'var(--text)',
        }}>
          {node.name}
        </span>
      </div>
      {node.children?.map(child => (
        <TreeNode key={child.name} node={child} depth={depth + 1} />
      ))}
    </div>
  )
}

export default function ProjectStructure({ data }) {
  return (
    <div className="section-root">
      <div className="section-header">
        <h2>Project Structure</h2>
        <p>Directory and file layout of the repository.</p>
      </div>

      <div className="card" style={{ overflowX: 'auto', position: 'relative' }}>
        <TreeNode node={data} depth={0} />
      </div>
    </div>
  )
}
