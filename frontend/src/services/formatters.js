import { displayMask } from './inputMasks.js'
import { formatDocument, normalizeDocument } from './documents.js'

const empty = value => value === null || value === undefined || String(value).trim() === ''

export function formatTaxId(value, personType) {
  if (empty(value)) return '—'
  const raw = normalizeDocument(value)
  const type = personType || (raw.length === 11 ? 'PF' : 'PJ')
  if (raw.length !== (type === 'PF' ? 11 : 14)) return String(value)
  return formatDocument(raw, type)
}

export const formatPhone = value => empty(value) ? '—' : displayMask(value, 'phone')
export const formatPlate = value => empty(value) ? '—' : displayMask(value, 'plate')
export const formatCep = value => empty(value) ? '—' : displayMask(value, 'cep')

export function formatNumber(value, options = {}) {
  if (empty(value) || !Number.isFinite(Number(value))) return '—'
  return Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 2, ...options })
}

export const formatPercent = value => empty(value) || !Number.isFinite(Number(value)) ? '—' : `${formatNumber(value)}%`

export function formatDate(value, options = {}) {
  if (empty(value)) return '—'
  // Uma data sem horário é um dia do calendário, não um instante à meia-noite UTC.
  const date = new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? `${value}T12:00:00` : value)
  if (!Number.isFinite(date.getTime())) return '—'
  return date.toLocaleDateString('pt-BR', options)
}

export const rentalStatusLabel = value => ({
  DRAFT: 'Rascunho', SENT: 'Enviado', APPROVED: 'Aprovado / reservado',
  ACTIVE: 'Em locação', RETURNED: 'Devolvido / em inspeção',
  COMPLETED: 'Concluído', CANCELLED: 'Cancelado', EXPIRED: 'Expirado',
})[value] || value || '—'

export const transportStatusLabel = value => ({
  PLANNED: 'Planejado', IN_TRANSIT: 'Em transporte', COMPLETED: 'Concluído', CANCELLED: 'Cancelado',
})[value] || value || '—'
