import { getDocumentIntegritySummary } from '../../services/evaluationService.js'

export default function DocumentIntegrityChart({ summary = getDocumentIntegritySummary() }) {
  return (
    <section className="evaluation-panel" aria-labelledby="document-integrity-heading">
      <div className="evaluation-panel-heading">
        <h2 id="document-integrity-heading">Document integrity</h2>
        <p className="result-count">
          Cryptographic hash verification summary from actual backend results only.
        </p>
      </div>

      <div className="unavailable-state" role="status">
        <strong>{summary.title}: not implemented</strong>
        <p>{summary.message}</p>
      </div>

      <div className="evaluation-definition">
        <h3>Interpretation boundary</h3>
        <p className="registry-state">{summary.disclaimer}</p>
        <dl className="definition-list">
          <div>
            <dt>Matching hashes</dt>
            <dd>0 reported; no verification results are available.</dd>
          </div>
          <div>
            <dt>Mismatched hashes</dt>
            <dd>Not available.</dd>
          </div>
          <div>
            <dt>Verification errors</dt>
            <dd>Not available.</dd>
          </div>
          <div>
            <dt>Success-rate denominator</dt>
            <dd>Matching hashes / total applicable verification attempts, only when results exist.</dd>
          </div>
        </dl>
      </div>
    </section>
  )
}