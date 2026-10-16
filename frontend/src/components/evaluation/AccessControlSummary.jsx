import { getAccessControlSummary } from '../../services/evaluationService.js'

function resultLabel(allowedRoles, role) {
  return allowedRoles.includes(role) ? 'Allowed by policy' : 'Rejected by policy'
}

export default function AccessControlSummary({ summary = getAccessControlSummary() }) {
  const { policy, message } = summary

  return (
    <section className="evaluation-panel" aria-labelledby="access-control-heading">
      <div className="evaluation-panel-heading">
        <h2 id="access-control-heading">Role-based access control</h2>
        <p className="result-count">
          Policy source: {policy.source}
        </p>
      </div>

      <div className="evaluation-note" role="status">
        <strong>Measured test results are not available.</strong>
        <p>{message}</p>
      </div>

      <div className="permission-matrix-wrapper">
        <table className="permission-matrix">
          <caption className="sr-only">
            Configured backend authorization rules for citizen, registrar, and admin roles.
          </caption>
          <thead>
            <tr>
              <th scope="col">Action</th>
              {policy.roles.map((role) => (
                <th key={role} scope="col">
                  {role}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {policy.actions.map((action) => (
              <tr key={action.key}>
                <th scope="row">{action.label}</th>
                {policy.roles.map((role) => (
                  <td key={role}>{resultLabel(action.allowedRoles, role)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="access-control-notes">
        {policy.actions.map((action) => (
          <li key={action.key}>
            <strong>{action.label}:</strong> {action.notes}
          </li>
        ))}
        <li>
          <strong>Test outcomes:</strong> No executed RBAC test dataset is exposed by the API. Allowed, rejected,
          and unexpected-action counts are therefore not shown.
        </li>
      </ul>
    </section>
  )
}