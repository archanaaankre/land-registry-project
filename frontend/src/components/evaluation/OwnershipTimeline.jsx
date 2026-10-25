function formatTimestamp(value) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Timestamp unavailable' : date.toLocaleString()
}

function recordTone(status) {
  const normalized = String(status ?? '').toLowerCase()
  if (normalized === 'active') {
    return 'status-active'
  }
  if (normalized === 'disputed') {
    return 'status-disputed'
  }
  return 'status-inactive'
}

export default function OwnershipTimeline({ data, loading, error, onRetry }) {
  if (loading) {
    return (
      <section className="evaluation-panel" aria-labelledby="ownership-timeline-heading">
        <h2 id="ownership-timeline-heading">Ownership traceability</h2>
        <p className="registry-state" role="status">Loading ownership records…</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="evaluation-panel error-state" aria-labelledby="ownership-timeline-heading" role="alert">
        <h2 id="ownership-timeline-heading">Ownership traceability</h2>
        <p>{error}</p>
        {onRetry ? (
          <button className="secondary-button" onClick={onRetry} type="button">
            Retry
          </button>
        ) : null}
      </section>
    )
  }

  const events = data?.events ?? []

  return (
    <section className="evaluation-panel" aria-labelledby="ownership-timeline-heading">
      <div className="evaluation-panel-heading">
        <h2 id="ownership-timeline-heading">Ownership traceability</h2>
        <p className="result-count">
          {events.length} ownership record{events.length === 1 ? '' : 's'} from the application’s parcel records.
        </p>
      </div>

      {events.length === 0 ? (
        <p className="registry-state">{data?.message ?? 'No ownership records are currently available.'}</p>
      ) : (
        <ol className="ownership-timeline">
          {events.map((event) => (
            <li className="ownership-timeline-item" key={event.id}>
              <article>
                <div className="timeline-heading">
                  <span className={`status-badge ${recordTone(event.recordStatus)}`}>
                    {event.recordStatus}
                  </span>
                  <p className="timeline-timestamp">{formatTimestamp(event.timestamp)}</p>
                </div>
                <dl className="timeline-details">
                  <div>
                    <dt>Parcel</dt>
                    <dd>{event.cadastralNumber} ({event.parcelId})</dd>
                  </div>
                  <div>
                    <dt>Record type</dt>
                    <dd>{event.eventType}</dd>
                  </div>
                  <div>
                    <dt>Ownership record ID</dt>
                    <dd>{event.ownershipRecordId}</dd>
                  </div>
                  <div>
                    <dt>Recorded owner</dt>
                    <dd>{event.ownerReference}</dd>
                  </div>
                  <div>
                    <dt>Share</dt>
                    <dd>{event.share}%</dd>
                  </div>
                </dl>
              </article>
            </li>
          ))}
        </ol>
      )}

      {data?.errors?.length ? (
        <div className="evaluation-note" role="status">
          <strong>Partial data</strong>
          <ul>
            {data.errors.map((message, index) => (
              <li key={index}>{message}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="evaluation-definition">
        <h3>Source and limits</h3>
        <p className="registry-state">
          Source: parcel ownership records. Entries are displayed by their recorded creation time. They are not
          inferred transfers; this API does not expose prior-owner transitions or blockchain confirmations here.
        </p>
      </div>
    </section>
  )
}