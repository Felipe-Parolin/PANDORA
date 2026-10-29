// Preserve legacy workflow values while presenting the two current OS situations.
export const serviceOrderState = status => status === 'COMPLETED' ? 'COMPLETED' : status === 'CANCELLED' ? 'CANCELLED' : 'OPEN'
export const serviceOrderStateLabel = status => ({ OPEN: 'Em aberto', COMPLETED: 'Concluído', CANCELLED: 'Cancelado' })[serviceOrderState(status)]
export const isOpenServiceOrder = status => serviceOrderState(status) === 'OPEN'
