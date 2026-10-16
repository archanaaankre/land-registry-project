import { getTamperDetectionSummary } from '../../services/evaluationService.js'

export default function TamperDetectionChart({ summary = getTamperDetectionSummary() }) {
  return (
    <section className="evaluation-panel" aria-labelledby="tamper-detection-heading">
      <div className="evaluation-panel-heading">
        <h2 id="tamper-detection-heading">Tamper detection</h2>
        <p className="result-count">
          Controlled test summary; unavailable until a tamper-detection implementation and test results exist.
        </p>
      </div>

      <div className="unavailable-state" role="status">
        <strong>{summary.title}: no test results available</strong>
        <p>{summary.message}</p>
      </div>

      <div className="evaluation-definition">
        <h3>Methodology</h3>
        <dl className="definition-list">
          <div>
            <dt>Detection rate</dt>
            <dd>{summary.formula}</dd>
          </div>
          <div>
            <dt>Denominator rule</dt>
            <dd>{summary.denominatorRule}</dd>
          </div>
          <div>
            <dt>Currently counted attempts</dt>
            <dd>None; no tamper-detection tests were executed by this dashboard.</dd>
          </div>
        </dl>
      </div>
    </section>
  )
}