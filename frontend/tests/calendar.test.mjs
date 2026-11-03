import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { compileScript, parse } from '@vue/compiler-sfc'
import * as Vue from 'vue'
import * as calendar from '../src/services/calendar.js'

function controller(t, overrides = {}) {
  const events = [], props = Vue.reactive({ modelValue: '', type: 'date', required: false, disabled: false, readonly: false, ...overrides })
  const vue = { ...Vue, onMounted() {}, onBeforeUnmount() {}, useAttrs: () => ({}), useId: () => 'test' }
  let code = compileScript(parse(readFileSync(new URL('../src/components/AppDateTime.vue', import.meta.url), 'utf8')).descriptor, { id: 'AppDateTime' }).content
  code = code.replace(/import\s+\{([^}]+)\}\s+from\s+'([^']+)'/g, (_, names, path) => `const {${names}} = ${path === 'vue' ? 'vue' : path.includes('calendar') ? 'calendar' : '{}'}`)
  const scope = Vue.effectScope()
  const component = new Function('vue', 'calendar', code.replace('export default', 'return'))(vue, calendar)
  const state = Vue.proxyRefs(scope.run(() => component.setup(props, { expose() {}, emit: (...args) => events.push(args) })))
  state.native = { value: '' }; state.trigger = { focus() {} }
  t.after(() => scope.stop())
  return { state, props, events }
}

test('calendário: meses começam na segunda, atravessam o ano e validam anos bissextos', () => {
  assert.equal(calendar.calendarDays(2026, 10)[0].value, '2026-10-26')
  assert.equal(calendar.calendarDays(2026, 11).length, 42)
  assert.equal(calendar.calendarDays(2026, 11).at(-1).value, '2027-01-10')
  assert.ok(calendar.parseDate('2024-02-29')); assert.equal(calendar.parseDate('2023-02-29'), null)
  assert.equal(calendar.parseDate('2026-13-01'), null)
  assert.equal(calendar.parseDate('0000-01-01'), null)
  assert.ok(calendar.calendarDays(1, 0).some(day => day.value === '0001-01-01'))
  assert.equal(calendar.displayDate('2026-11-05T09:30', 'datetime-local'), '05/11/2026 às 09:30')
})

test('calendário real: dia fora do intervalo não altera o formulário; valor escolhido mantém ISO', t => {
  const { state, events } = controller(t, { min: '2026-11-05', max: '2026-11-09' })
  state.choose('2026-11-04'); assert.deepEqual(events, [])
  state.choose('2026-11-09')
  assert.deepEqual(events[0], ['update:modelValue', '2026-11-09'])
  assert.equal(events[1][1].target.value, '2026-11-09')
})

test('calendário real: horário requer aplicar e respeita os limites de data e hora', t => {
  const { state, events } = controller(t, { type: 'datetime-local', min: '2026-11-05T09:00', max: '2026-11-05T16:30' })
  state.choose('2026-11-05'); assert.deepEqual(events, [])
  state.hour = '17'; state.minute = '00'; state.apply()
  assert.deepEqual(events, []); assert.ok(state.error)
  state.hour = '15'; state.minute = '5'; state.apply()
  assert.deepEqual(events[0], ['update:modelValue', '2026-11-05T15:05'])
})

test('calendário real: minuto inválido e controle desabilitado não enviam mudanças', t => {
  const { state, props, events } = controller(t, { type: 'time' })
  state.hour = '09'; state.minute = '60'; state.apply(); assert.deepEqual(events, [])
  state.minute = '30'; props.disabled = true; state.apply(); assert.deepEqual(events, [])
})
