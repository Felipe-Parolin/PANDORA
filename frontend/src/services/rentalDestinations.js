import { toDateTimeInput } from './formDates.js'

export function splitAddress(address = '', number = '') {
  const parts = String(address || '').split(',').map(value => value.trim())
  if (parts.length > 1 && /^(?:\d+[a-z]?(?:[-/]\d+)?|s\/?n)$/i.test(parts[1])) {
    return { address: [parts[0], ...parts.slice(2)].join(', '), number: number || parts[1] }
  }
  return { address: String(address || ''), number: number || '' }
}
export function fullAddress(address = '', number = '') {
  if (!number) return address || ''
  const base = splitAddress(address).address, comma = base.indexOf(',')
  return comma < 0 ? `${base}, ${number}` : `${base.slice(0,comma)}, ${number}${base.slice(comma)}`
}
export function effectiveLocation(item, form, leg, separate = true) {
  const custom = separate && item[`${leg}_location`]
  if (custom && Object.keys(custom).length) return { address:'', number:'', cep:'', complement:'', time:'', ...custom }
  return { ...splitAddress(form[`${leg}_address`], form[`${leg}_number`]), cep: form[`${leg}_cep`] || '', complement: form[`${leg}_complement`] || '', time: toDateTimeInput(form[`requested_${leg}_at`]).slice(11,16) }
}
export function destinationGroups(items, form, leg, separate = true) {
  const groups = new Map()
  for (const item of items) {
    const location = effectiveLocation(item,form,leg,separate)
    const key = JSON.stringify([location.address.toLocaleLowerCase().trim().replace(/\s+/g,' '), location.number.toLocaleLowerCase().trim(),location.cep,location.complement.trim()])
    if (!groups.has(key)) groups.set(key, {...location, key, items:[]})
    groups.get(key).items.push({...item,time:location.time})
  }
  return [...groups.values()]
}
