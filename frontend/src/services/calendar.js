const pad = value => String(value).padStart(2, '0')
export const localDate = date => `${String(date.getFullYear()).padStart(4, '0')}-${pad(date.getMonth()+1)}-${pad(date.getDate())}`
export function parseDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value || '')
  if (!match) return null
  if (Number(match[1]) < 1) return null
  const date = new Date(2000, Number(match[2])-1, Number(match[3]), 12)
  date.setFullYear(Number(match[1]))
  return localDate(date) === match[0] ? date : null
}
export function calendarDays(year, month) {
  const first = new Date(2000, month, 1, 12)
  first.setFullYear(year)
  first.setDate(first.getDate() - (first.getDay()+6)%7)
  return Array.from({ length: 42 }, (_, index) => {
    const day = new Date(first); day.setDate(first.getDate()+index)
    return { value: localDate(day), day: day.getDate(), outside: day.getMonth() !== month }
  })
}
export function withinRange(value, min, max) { return Boolean(value) && (!min || value >= min) && (!max || value <= max) }
export function displayDate(value, type = 'date') {
  if (!value) return ''
  if (type === 'time') return value.slice(0, 5)
  const date = parseDate(value)
  if (!date) return ''
  const formatted = `${pad(date.getDate())}/${pad(date.getMonth()+1)}/${String(date.getFullYear()).padStart(4,'0')}`
  return type === 'datetime-local' ? `${formatted} às ${value.slice(11,16)}` : formatted
}
