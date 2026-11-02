export const NAV_ITEMS = [
  { to: '/dashboard', label: 'Dashboard', roles: ['CITIZEN', 'REGISTRAR', 'VERIFICATION_OFFICER', 'ADMIN'] },
  { to: '/parcels', label: 'Land Records', roles: ['CITIZEN', 'REGISTRAR', 'ADMIN'] },
  { to: '/transfers', label: 'My Transfers', roles: ['CITIZEN'] },
  { to: '/registrar/transfers', label: 'Transfer Review', roles: ['REGISTRAR'] },
  { to: '/evaluation', label: 'Evaluation', roles: ['CITIZEN', 'REGISTRAR', 'ADMIN'] },
  { to: '/admin/users', label: 'User Management', roles: ['ADMIN'] },
]
