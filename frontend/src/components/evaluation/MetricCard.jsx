const STATE_LABELS = {
  measured: 'Measured',
  'not-measured': 'Not yet measured',
  unavailable: 'Unavailable',
}

export default function MetricCard({
  title,
  value,
  unit,
  detail,
  sampleCount,
  sampleLabel = 'tests measured',
  state = 'not-measured',
}) {
  const hasValue = value !== null && value !== undefined
  const effectiveState = state === 'measured' && !hasValue ? 'not-measured' : state

  return (
    <article className="metric-card" aria-labelledby={`${title.toLowerCase().replaceAll(' ', '-')}-title`}>
      <h2 className="metric-title" id={`${title.toLowerCase().replaceAll(' ', '-')}-title`}>{title}</h2>
      <p className="metric-value">
        {effectiveState === 'measured'
          ? value
          : effectiveState === 'unavailable'
            ? 'Unavailable'
            : 'Not yet measured'}
        {effectiveState === 'measured' && unit ? <span className="metric-unit"> {unit}</span> : null}
      </p>
      {detail ? <p className="metric-detail">{detail}</p> : null}
      {Number.isInteger(sampleCount) && sampleCount >= 0 ? (
        <p className="metric-sample-count">{sampleCount} {sampleLabel}</p>
      ) : null}
      <span className={`metric-status metric-status-${effectiveState}`}>{STATE_LABELS[effectiveState]}</span>
    </article>
  )
}