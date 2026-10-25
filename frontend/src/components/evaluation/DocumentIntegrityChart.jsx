import { getDocumentIntegritySummary } from '../../services/evaluationService.js'

export default function DocumentIntegrityChart({ summary = getDocumentIntegritySummary() }) {
  return (
    <section className="evaluation-panel" aria-labelledby="document-integrity-heading">
      <div className="evaluation-panel-heading">
        <h2 id="document-integrity-heading">Document integrity</h2>
        <p className="result-count">
          Unavailable — document-hash verification is not implemented in this build.
        </p>
      </div>

      <div className="unavailable-state" role="status">
        <strong>{summary.title}: results unavailable</strong>
        <p>{summary.message}</p>
      </div>

      <div className="evaluation-definition">
        <h3>Verification results</h3>
        <p className="registry-state">{summary.disclaimer}</p>
        <dl className="definition-list">
          <div>
            <dt>Matching document hashes</dt>
            <dd>Not yet measured.</dd>
          </div>
          <div>
            <dt>Modified documents with detected mismatches</dt>
            <dd>Not yet measured.</dd>
          </div>
          <div>
            <dt>Verification errors</dt>
            <dd>Not yet measured.</dd>
          </div>
          <div>
            <dt>Detection-rate rule</dt>
            <dd>
              Modified documents with a detected mismatch / modified documents tested × 100. Calculate only when
              both counts are available and the tested count is greater than zero.
            </dd>
          </div>
        </dl>
      </div>
    </section>
  )
}