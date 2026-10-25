import { getTamperDetectionSummary } from '../../services/evaluationService.js'

export default function TamperDetectionChart({ summary = getTamperDetectionSummary() }) {
  return (
    <section className="evaluation-panel" aria-labelledby="tamper-detection-heading">
      <div className="evaluation-panel-heading">
        <h2 id="tamper-detection-heading">Tamper detection</h2>
        <p className="result-count">
          Not yet measured — no controlled modified-record test results are available.
        </p>
      </div>

      <div className="unavailable-state" role="status">
        <strong>{summary.title}: unavailable</strong>
        <p>{summary.message}</p>
      </div>

      <div className="evaluation-definition">
        <h3>Results required for a detection rate</h3>
        <dl className="definition-list">
          <div>
            <dt>Modified records tested</dt>
            <dd>Not yet measured.</dd>
          </div>
          <div>
            <dt>Correctly detected</dt>
            <dd>Not yet measured.</dd>
          </div>
          <div>
            <dt>Not detected / unexpected outcomes</dt>
            <dd>Not yet measured.</dd>
          </div>
          <div>
            <dt>Detection rate formula</dt>
            <dd>Correctly detected modified records / total modified records tested × 100.</dd>
          </div>
          <div>
            <dt>Unmodified records tested</dt>
            <dd>Not yet measured; this count would be reported separately from modified-record detection.</dd>
          </div>
          <div>
            <dt>Denominator rule</dt>
            <dd>{summary.denominatorRule}</dd>
          </div>
        </dl>
      </div>
    </section>
  )
}