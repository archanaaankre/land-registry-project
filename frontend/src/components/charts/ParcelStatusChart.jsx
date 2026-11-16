import {
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
} from 'recharts'

const PALETTE = [
  { status: 'ACTIVE', color: '#287a52' },
  { status: 'INACTIVE', color: '#536b82' },
  { status: 'DISPUTED', color: '#a96812' },
]

export default function ParcelStatusChart({ parcels = [], loading = false, error = '' }) {
  if (loading) {
    return (
      <section className="evaluation-panel" aria-labelledby="parcel-status-heading">
        <h2 id="parcel-status-heading">Parcel status distribution</h2>
        <p className="registry-state" role="status">Loading parcel statistics…</p>
      </section>
    )
  }

  if (error) {
    return (
      <section className="evaluation-panel error-state" aria-labelledby="parcel-status-heading" role="alert">
        <h2 id="parcel-status-heading">Parcel status distribution</h2>
        <p>{error}</p>
      </section>
    )
  }

  const counts = PALETTE.reduce((acc, { status }) => {
    acc[status] = parcels.filter((parcel) => parcel.status === status).length
    return acc
  }, {})

  const total = parcels.length
  const data = PALETTE.map(({ status, color }) => ({
    status,
    value: counts[status] ?? 0,
    color,
  }))

  return (
    <section className="evaluation-panel" aria-labelledby="parcel-status-heading">
      <div className="evaluation-panel-heading">
        <h2 id="parcel-status-heading">Parcel status distribution</h2>
        <p className="result-count">
          {total} registered parcel{total === 1 ? '' : 's'}
        </p>
      </div>

      {total === 0 ? (
        <p className="registry-state">No parcels are currently available.</p>
      ) : (
        <>
          <div className="chart-container" style={{ width: '100%', height: 260 }}>
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Tooltip />
                <Pie
                  data={data}
                  dataKey="value"
                  nameKey="status"
                  cx="50%"
                  cy="50%"
                  innerRadius={80}
                  outerRadius={110}
                  fill="#8884d8"
                  label
                >
                  {data.map((entry) => (
                    <Cell key={entry.status} fill={entry.color} />
                  ))}
                </Pie>
              </PieChart>
            </ResponsiveContainer>
          </div>

          <div className="chart-legend">
            {data.map((entry) => (
              <div key={entry.status} className="chart-legend-item">
                <span
                  className="chart-legend-color"
                  style={{ backgroundColor: entry.color }}
                />
                <span>{entry.status}</span>
                <span className="chart-legend-value">{entry.value}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </section>
  )
}
