export const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', roles: ['CITIZEN', 'REGISTRAR', 'ADMIN', 'VERIFICATION_OFFICER'] },
  { to: '/parcels', label: 'Land Records', roles: ['CITIZEN', 'REGISTRAR', 'ADMIN', 'VERIFICATION_OFFICER'] },
  { to: '/transfers', label: 'My Transfers', roles: ['CITIZEN'] },
  { to: '/registrar/transfers', label: 'Transfer Review', roles: ['REGISTRAR'] },
  { to: '/documents/integrity', label: 'Document Integrity', roles: ['CITIZEN', 'REGISTRAR', 'ADMIN', 'VERIFICATION_OFFICER'] },
  { to: '/documents/tamper', label: 'Tamper Detection', roles: ['CITIZEN', 'REGISTRAR', 'ADMIN', 'VERIFICATION_OFFICER'] },
  { to: '/evaluation', label: 'Evaluation', roles: ['CITIZEN', 'REGISTRAR', 'ADMIN', 'VERIFICATION_OFFICER'] },
  { to: '/admin/dashboard', label: 'Admin Dashboard', roles: ['ADMIN'] },
  { to: '/admin/users', label: 'Manage Users', roles: ['ADMIN'] },
]
