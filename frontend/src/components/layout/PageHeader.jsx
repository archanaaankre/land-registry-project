export default function PageHeader({ eyebrow, title, intro, actions }) {
  return (
    <header className="page-header">
      <div className="page-header-heading">
        {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
        <h1 className="page-header-title">{title}</h1>
        {intro ? <p className="page-header-intro">{intro}</p> : null}
      </div>
      {actions ? (
        <div className="page-header-actions">
          {actions}
        </div>
      ) : null}
    </header>
  )
}
