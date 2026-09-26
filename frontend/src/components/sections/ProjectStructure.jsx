import './sections.css'

function TreeNode({ node, depth = 0 }) {
  const isDir = node.type === 'directory'
  const icon = isDir ? '📁' : '📄'

  return (
    <div>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          padding: '4px 0',
          paddingLeft: depth * 20,
          fontSize: 14,
          color: isDir ? 'var(--text-h)' : 'var(--text)',
          fontFamily: 'var(--mono)',
        }}
      >
        <span style={{ fontSize: 13 }} aria-hidden="true">{icon}</span>
        <span style={{ fontWeight: isDir ? 600 : 400 }}>{node.name}</span>
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

      <div className="card" style={{ overflowX: 'auto' }}>
        <TreeNode node={data} depth={0} />
      </div>
    </div>
  )
}
