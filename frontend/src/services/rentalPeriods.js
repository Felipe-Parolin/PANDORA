export function periodDays(start, end) {
  if (!start || !end || end < start) return 0
  const days = Math.round((Date.parse(`${end}T12:00:00Z`) - Date.parse(`${start}T12:00:00Z`)) / 86400000) + 1
  return Number.isFinite(days) ? days : 0
}
export function periodEnvelope(items, fallback) {
  const starts = items.map(item => item.start_date).filter(Boolean).sort()
  const ends = items.map(item => item.end_date).filter(Boolean).sort()
  return { start_date: starts[0] || fallback.start_date, end_date: ends.at(-1) || fallback.end_date }
}
export function periodGroups(items) {
  const groups = new Map()
  for (const item of items) {
    const key = `${item.start_date}/${item.end_date}`
    if (!groups.has(key)) groups.set(key, { start: item.start_date, end: item.end_date, items: [] })
    groups.get(key).items.push(item)
  }
  return [...groups.values()]
}
