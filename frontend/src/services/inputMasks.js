export const digits = value => String(value ?? '').replace(/\D/g, '')
export function canonicalMask(value, mask) {
  if (mask === 'cep') return digits(value)
  if (mask === 'plate') return String(value ?? '').replace(/[\s-]/g, '').toUpperCase()
  if (mask === 'phone') {
    const raw = String(value ?? '')
    return (raw.trim().startsWith('+') ? '+' : '') + digits(raw)
  }
  let raw = String(value ?? '').replace(/R\$|%|\s/g, '')
  if (raw.includes(',')) raw = raw.replace(/\./g, '').replace(',', '.')
  else if (/^-?\d{1,3}(\.\d{3})+$/.test(raw)) raw = raw.replace(/\./g, '')
  return raw
}
export function displayMask(value, mask, precision = 2) {
  const raw = String(value ?? '')
  if (!raw) return ''
  if (mask === 'cep') { const text = digits(raw); return text.length > 5 ? `${text.slice(0,5)}-${text.slice(5)}` : text }
  if (mask === 'plate') { const text = canonicalMask(raw, mask); return text.length > 3 ? `${text.slice(0,3)}-${text.slice(3)}` : text }
  if (mask === 'phone') {
    let text = digits(raw), prefix = ''
    if (text.startsWith('55') && text.length > 11) { prefix = '+55 '; text = text.slice(2) }
    else if (raw.startsWith('+')) return '+'+text
    if (text.length <= 2) return prefix + (text ? `(${text}` : '')
    const local = text.slice(2), split = local.length > 8 ? 5 : 4
    return `${prefix}(${text.slice(0,2)}) ${local.slice(0,split)}${local.length > split ? '-'+local.slice(split) : ''}`
  }
  if (!/^-?\d+(?:\.\d*)?$/.test(raw)) return raw
  const [integer, fraction = ''] = raw.split('.')
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, '.')
  const decimal = mask === 'money' ? fraction.padEnd(precision, '0') : fraction
  return `${mask === 'money' ? 'R$ ' : ''}${grouped}${decimal ? ','+decimal : ''}${mask === 'percent' ? '%' : ''}`
}
export function maskError(raw, mask, { min, max, step, precision = 2 } = {}) {
  if (raw === '') return ''
  if (mask === 'cep') return /^\d{8}$/.test(raw) ? '' : 'Informe um CEP com oito dígitos.'
  if (mask === 'plate') return /^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$/.test(raw) ? '' : 'Informe uma placa como ABC1234 ou ABC1D23.'
  if (mask === 'phone') return /^(?:\+?55)?\d{10,11}$/.test(raw) || /^\+\d{8,15}$/.test(raw) ? '' : 'Informe o telefone com DDD.'
  if (!/^-?\d+(?:\.\d*)?$/.test(raw) || !Number.isFinite(Number(raw))) return 'Informe um número válido.'
  if ((raw.split('.')[1] || '').length > precision) return `Use no máximo ${precision} casas decimais.`
  const value = Number(raw)
  if (min !== undefined && min !== '' && value < Number(min)) return `O valor mínimo é ${min}.`
  if (max !== undefined && max !== '' && value > Number(max)) return `O valor máximo é ${max}.`
  if (step && step !== 'any') {
    const count = (value-Number(min || 0))/Number(step)
    if (Math.abs(count-Math.round(count)) > 1e-7) return `Use intervalos de ${step}.`
  }
  return ''
}
