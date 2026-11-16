import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

const STATUS_ORDER = ['DRAFT', 'SUBMITTED', 'UNDER_REVIEW', 'APPROVED', 'BLOCKCHAIN_PENDING', 'COMPLETED', 'REJECTED', 'FAILED', 'CANCELLED']

const PALETTE = {
  DRAFT: '#68757c',
  SUBMITTED: '#536b82',
  UNDER_REVIEW: '#a96812',
  APPROVED: '#287a52',
  BLOCKCHAIN_PENDING: '#536b82',
  COMPLETED: '#287a52',
  REJECTED: '#b74343',
  FAILED: '#b74343',
  CANCELLED: '#68757c',
}

function statusLabel(status) {
  const labels = {
    DRAFT: 'Draft',
    SUBMITTED: 'Submitted',
    UNDER_REVIEW: 'Under review',
    APPROVED: 'Approved',
    BLOCKCHAIN_PENDING: 'Blockchain pending',
    COMPLETED: 'Completed',
    REJECTED: 'Rejected',
    FAILED: 'Failed',
    CANCELLED: 'Cancelled',
  }
  return labels[status] || status
}

export default function TransferStatusChart({ transfers = [], loading = false, error = '' }) {
  if (loading) {
    return (
      <section className="evaluation-panel" aria-labelledby="transfer-status-heading">
        <h2 id="transfer-status-heading">Transfer requests by status</h2>
        <p className="registry-state" role="status">Loading transfer statistics…</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="evaluation-panel error-state" aria-labelledby="transfer-status-heading" role="alert">
        <h2 id="transfer-status-heading">Transfer requests by status</h2>
        <p>{error}</p>
      </section>
    )
  }

  const counts = STATUS_ORDER.reduce((acc, status) => {
    acc[status] = transfers.filter((transfer) => transfer.status === status).length
    return acc
  }, {})

  const total = transfers.length
  const data = STATUS_ORDER.map((status) => ({
    status,
    label: statusLabel(status),
    value: counts[status] ?? 0,
    color: PALETTE[status] ?? '#68757c',
  }))

  return (
    <section className="evaluation-panel" aria-labelledby="transfer-status-heading">
      <div className="evaluation-panel-heading">
        <h2 id="transfer-status-heading">Transfer requests by status</h2>
        <p className="result-count">
          {total} transfer request{total === 1 ? '' : 's'}
        </p>
      </div>

      {total === 0 ? (
        <p className="registry-state">No transfer requests are currently available.</p>
      ) : (
        <>
          <div className="chart-container" style={{ width: '100%', height: 300 }}>
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={data} margin={{ top: 20, right: 30, bottom: 80, left: 20 }}>
                <Tooltip />
                <XAxis dataKey="label" tick={{ fontSize: 12 }} />
                <YAxis tick={{ fontSize: 12 }} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]} fill="#536b82">
                  {data.map((entry) => (
                    <Cell key={entry.status} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-legend">
            {data.filter((entry) => entry.value > 0).map((entry) => (
              <div key={entry.status} className="chart-legend-item">
                <span
                  className="chart-legend-color"
                  style={{ backgroundColor: entry.color }}
                />
                <span>{entry.label}</span>
                <span className="chart-legend-value">{entry.value}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
