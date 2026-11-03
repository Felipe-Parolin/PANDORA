export function inspectionProgress(quote, type) {
  const equipmentIds = new Set(quote.items.map(item => item.equipment))
  const items = quote.inspections?.filter(item => item.inspection_type === type && equipmentIds.has(item.equipment)) || []
  return { done: items.filter(item => item.result !== 'PENDING').length, total: quote.items.length }
}
export const taskFor = (quote, leg) => quote.transport_tasks?.find(task => task.leg === leg)
export const itemStage = (quote, item) => item.stage || ({ ACTIVE: 'DELIVERED', RETURNED: 'RETURNED', COMPLETED: 'COMPLETED' }[quote.status] || 'PENDING')
export const operationCandidates = (quote, operation) => (quote.items || []).filter(item => ({ deliver: ['PENDING'], return: ['DELIVERED'], finalize: ['RETURNED'], extend: ['PENDING', 'DELIVERED'] }[operation] || []).includes(itemStage(quote, item)))
export const transportReady = (quote, leg, lines = quote.items) => !(leg === 'DELIVERY' ? quote.delivery_transport_required : quote.return_transport_required) || lines.length > 0 && lines.every(line => quote.transport_tasks?.some(task => task.leg === leg && task.status === 'COMPLETED' && (!Array.isArray(task.items) || task.items.some(item => item.equipment === line.equipment))))
export function operationProblem(quote, operation, line) {
  if (operation === 'deliver') {
    const inspection = quote.inspections?.find(item => item.equipment === line.equipment && item.inspection_type === 'PRE_RENTAL')
    if (!inspection || !['APPROVED', 'APPROVED_WITH_NOTES'].includes(inspection.result) || inspection.critical_impediment) return 'Aguarde a liberação da inspeção de saída.'
    if (!transportReady(quote, 'DELIVERY', [line])) return 'Conclua a viagem de entrega deste item.'
  }
  if (operation === 'return' && !transportReady(quote, 'RETURN', [line])) return 'Conclua a viagem de coleta deste item.'
  if (operation === 'finalize' && !quote.inspections?.some(item => item.equipment === line.equipment && item.inspection_type === 'RETURN' && item.result !== 'PENDING')) return 'Conclua a inspeção final deste item.'
  return ''
}
export const inspectionsReleased = quote => quote.items.length > 0 && inspectionProgress(quote, 'PRE_RENTAL').done === quote.items.length && !(quote.inspections || []).some(item => item.inspection_type === 'PRE_RENTAL' && quote.items.some(line => line.equipment === item.equipment) && item.result === 'BLOCKED')

export function rentalActionGroups(quote, can, busy = false) {
  const proposal = ['DRAFT', 'SENT'].includes(quote.status)
  const ongoing = ['APPROVED', 'ACTIVE'].includes(quote.status)
  const reserved = ['APPROVED', 'ACTIVE', 'RETURNED', 'COMPLETED'].includes(quote.status)
  const returned = quote.items.some(item => ['RETURNED', 'COMPLETED'].includes(itemStage(quote, item)))
  const eligible = operation => operationCandidates(quote, operation).some(item => !operationProblem(quote, operation, item))
  const stage = allowed => allowed ? '' : 'Indisponível na etapa atual da locação.'
  const action = (id, label, icon, permission, reason = '', tone = '') => ({
    id, label, icon, tone,
    reason: !can(permission) ? 'Seu perfil não possui permissão para esta ação.' : busy ? 'Aguarde a operação em andamento.' : reason,
  })
  return [
    { label: 'Acompanhamento', actions: [
      action('flow', 'Fluxo e documentos', 'Route', 'rentals.view'),
      action('preInspection', 'Inspeção de saída', 'ClipboardCheck', 'maintenance.view', stage(reserved)),
      action('postInspection', 'Inspeção de retorno', 'ClipboardCheck', 'maintenance.view', stage(returned)),
      action('deliveryTransport', 'Transporte de entrega', 'Truck', 'logistics.view', !quote.delivery_transport_required ? 'Entrega sem transporte contratado.' : stage(reserved)),
      action('returnTransport', 'Transporte de coleta', 'Truck', 'logistics.view', !quote.return_transport_required ? 'Coleta sem transporte contratado.' : stage(['ACTIVE', 'RETURNED', 'COMPLETED'].includes(quote.status))),
    ] },
    { label: 'Operação', actions: [
      action('edit', 'Editar orçamento', 'Pencil', 'rentals.manage', stage(proposal)),
      action('reserve', 'Aprovar e reservar', 'PackageCheck', 'rentals.approve', stage(proposal) || (!quote.items.length ? 'Adicione equipamentos ao orçamento.' : '') || (!quote.conditions?.trim() ? 'Registre as condições comerciais.' : ''), 'success'),
      action('deliver', 'Registrar entrega', 'PackageCheck', 'rentals.dispatch', stage(ongoing && operationCandidates(quote, 'deliver').length) || (!eligible('deliver') ? 'Aguarde a liberação técnica e o transporte dos itens.' : ''), 'success'),
      action('extend', 'Prorrogar locação', 'CalendarRange', 'rentals.extend', stage(ongoing)),
      action('return', 'Registrar devolução', 'RotateCcw', 'rentals.return', stage(quote.status === 'ACTIVE' && operationCandidates(quote, 'return').length) || (!eligible('return') ? 'Conclua a viagem de coleta.' : '')),
      action('finalize', 'Concluir devolução', 'CheckCircle2', 'rentals.return', stage(['ACTIVE', 'RETURNED'].includes(quote.status) && operationCandidates(quote, 'finalize').length) || (!eligible('finalize') ? 'Conclua a inspeção final dos equipamentos.' : ''), 'success'),
    ] },
    { label: 'Contato com o cliente', actions: [
      action('whatsapp', 'Confirmar pelo WhatsApp', 'MessageCircle', 'rentals.manage', stage(ongoing)),
      action('whatsappExtension', 'Solicitar prorrogação', 'CalendarRange', 'rentals.manage', stage(ongoing)),
    ] },
    { label: 'Encerramento', actions: [
      action('cancel', 'Cancelar locação', 'XCircle', 'rentals.manage', stage(['DRAFT', 'SENT', 'APPROVED'].includes(quote.status)), 'danger'),
      action('delete', 'Excluir orçamento', 'Trash2', 'rentals.manage', stage(['DRAFT', 'SENT', 'CANCELLED', 'EXPIRED'].includes(quote.status)) || (quote.transport_tasks?.length ? 'Viagens vinculadas protegem o histórico desta locação.' : ''), 'danger'),
    ] },
  ]
}
