const collator = new Intl.Collator('pt-BR', { numeric: true, sensitivity: 'base' })

export const searchText = value => String(value ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLocaleLowerCase('pt-BR').trim()
export function matchesSearch(query, ...values) {
  const term = searchText(query), compact = value => value.replace(/[\s.()/+\-]/g, '')
  const identifier = compact(term)
  return !term || values.some(value => {
    const text = searchText(value)
    return text.includes(term) || Boolean(identifier && compact(text).includes(identifier))
  })
}

// A lista original permanece intacta. Valores ausentes ficam no fim, inclusive na ordem decrescente.
export function sortRecords(records, ordering, fields) {
  const descending = ordering.startsWith('-')
  const select = fields[descending ? ordering.slice(1) : ordering]
  if (!select) return [...records]
  const missing = value => value == null || value === '' || typeof value === 'number' && !Number.isFinite(value)
  return [...records].sort((a, b) => {
    const left = select(a), right = select(b)
    if (missing(left) || missing(right)) return Number(missing(left)) - Number(missing(right))
    const result = typeof left === 'number' && typeof right === 'number' ? left - right : collator.compare(String(left), String(right))
    return descending ? -result : result
  })
}

export const dateValue = value => value ? Date.parse(value) : null
