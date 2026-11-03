import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { setImmediate } from 'node:timers/promises'
import test from 'node:test'
import { compileScript, parse } from '@vue/compiler-sfc'
import * as vue from 'vue'
import * as destinations from '../src/services/rentalDestinations.js'
import * as dates from '../src/services/formDates.js'
import * as pagination from '../src/services/pagination.js'
import * as listFilters from '../src/services/listFilters.js'
import * as actions from '../src/services/rentalActions.js'
import * as periods from '../src/services/rentalPeriods.js'

const equipment = { id: 1, name: 'Equipamento de teste', internal_code: 'EQ-TESTE', daily_rate: '100.00' }
const makeQuote = () => ({
  id: 1, number: 'ORC-TESTE', customer: 1, start_date: '2026-11-02', end_date: '2026-11-04', status: 'SENT',
  conditions: 'Condições de teste', subtotal: '300.00', discount: '0.00', discount_percent: '0.00', notes: '',
  delivery_transport_required: true, return_transport_required: false, delivery_address: 'Rua de teste, 120, Leme/SP', return_address: '',
  delivery_cep: '13614032', return_cep: '', transport_fee: '45.00', estimated_transport_fee: '45.00', transport_fee_adjustment_reason: '',
  requested_delivery_at: null, requested_return_at: null,
  items: [{ equipment: 1, equipment_name: equipment.name, internal_code: equipment.internal_code, daily_rate: '100.00', quantity_days: 3 }],
})
const flush = async () => { await setImmediate(); await vue.nextTick() }
const estimate = (fee = '30.00') => ({ data: { cep: '13614032', estimate: { fee, distance_km: '10.0', trip_count: 1 } } })

function mount(t, lookup = async () => estimate()) {
  const calls = [], writes = [], quote = makeQuote()
  const api = {
    async get(url, options) {
      if (url === '/rental-quotes/lookup-address/') { calls.push(options); return lookup(options) }
      if (url === '/rental-quotes/availability/') return { data: { available: [{ equipment }], blocked: [], next_page: null, count: 1 } }
      return { data: { results: [], next: null } }
    },
    async patch(url, payload) { writes.push({ url, payload }); return { data: {} } },
  }
  const services = {
    api, can: () => true, rows: data => data?.results || data || [], shortDate: value => value, money: value => String(value), apiError: () => 'Falha de consulta',
    fetchAll: async url => ({ data: { results: url === '/rental-quotes/' ? [quote] : url === '/customers/' ? [{ id: 1, name: 'Cliente fictício' }] : [] } }),
  }
  const route = vue.reactive({ query: {} })
  const dependencies = { destinations, vue, services, dates, pagination, actions, periods, listFilters, router: { useRoute: () => route, useRouter: () => ({}) }, icons: {} }
  const source = readFileSync(new URL('../src/views/RentalsView.vue', import.meta.url), 'utf8')
  let code = compileScript(parse(source).descriptor, { id: 'RentalsView' }).content
  code = code.replace(/import\s+\{([^}]+)\}\s+from\s+'([^']+)'/g, (_, names, path) => {
    const name = ({ vue: 'vue', 'vue-router': 'router', 'lucide-vue-next': 'icons' })[path]
      || (path.endsWith('/api') ? 'services' : path.endsWith('/formDates') ? 'dates' : path.endsWith('/pagination') ? 'pagination' : path.endsWith('/listFilters') ? 'listFilters' : path.endsWith('/rentalDestinations') ? 'destinations' : path.endsWith('/rentalPeriods') ? 'periods' : 'actions')
    return `const {${names}} = dependencies.${name}`
  }).replace(/import (\w+) from '[^']+'/g, 'const $1 = {}')
  const component = new Function('dependencies', code.replace('export default', 'return'))(dependencies)
  component.render = () => null
  const renderer = vue.createRenderer({ createComment: () => ({}), insert() {}, remove() {}, parentNode() {}, nextSibling() {} })
  const app = renderer.createApp(component)
  app.mount({})
  t.after(() => app.unmount())
  return { state: app._instance.setupState, quote, calls, writes }
}

test('frete: abrir edição mantém o valor contratado e os horários ao alternar transporte', async t => {
  const { state, quote } = mount(t)
  await flush(); state.open(quote); await flush()
  assert.equal(state.form.transport_fee, '45.00')
  assert.equal(state.freightNeedsCalculation, false)
  state.form.requested_delivery_at = '2026-11-02T09:30'
  state.form.requested_return_at = '2026-11-04T16:00'
  state.scheduleDelivery = true; state.scheduleReturn = true
  state.form.return_transport_required = true
  state.form.delivery_transport_required = false
  assert.equal(state.form.requested_delivery_at, '2026-11-02T09:30')
  assert.equal(state.form.requested_return_at, '2026-11-04T16:00')
})

test('frete: copiar endereço não copia o preço; coleta consulta a direção inversa e soma os trechos', async t => {
  const { state, quote, calls } = mount(t, async options => estimate(options.params.leg === 'RETURN' ? '36.00' : '30.37'))
  await flush(); state.open(quote); await flush()
  await state.calculateFreight('delivery')
  assert.equal(state.form.transport_fee, 30.37)
  state.form.return_transport_required = true
  state.useDeliveryAddressForReturn()
  assert.equal(state.form.return_address, state.form.delivery_address)
  assert.equal(state.addressLookup.return.result, null)
  assert.equal(state.freightEstimatesReady, false)
  await state.calculateFreight('return')
  assert.deepEqual(calls.map(call => call.params.leg), ['DELIVERY', 'RETURN'])
  assert.equal(calls[1].params.address, state.form.return_address)
  assert.equal(calls[1].params.equipment_ids, '1')
  assert.equal(state.form.transport_fee, 66.37)
  assert.equal(state.form.estimated_transport_fee, 66.37)
})

test('frete: alteração de endereço descarta resposta atrasada e mantém o ajuste manual', async t => {
  let resolve
  const { state, quote } = mount(t, () => new Promise(done => { resolve = done }))
  await flush(); state.open(quote); await flush()
  state.form.transport_fee = 100; state.freightManuallyEdited = true
  const pending = state.calculateFreight('delivery')
  state.form.delivery_address = 'Rua de teste, 121, Leme/SP'
  state.invalidateFreight('delivery')
  resolve(estimate('30.00')); await pending
  assert.equal(state.addressLookup.delivery.result, null)
  assert.equal(state.addressLookup.delivery.loading, false)
  assert.equal(state.form.transport_fee, 100)
  assert.equal(state.form.estimated_transport_fee, 0)
})

test('frete: buscar CEP preenche endereço sem precificar nem apagar texto alterado durante a consulta', async t => {
  let resolve
  const { state, quote, calls } = mount(t, () => new Promise(done => { resolve = done }))
  await flush(); state.open(quote); await flush()
  const pending = state.searchAddress('delivery')
  assert.equal(calls[0].params.address, undefined)
  state.form.delivery_address = 'Endereço já corrigido pelo operador, 150, Leme/SP'
  state.invalidateFreight('delivery')
  resolve({ data: { cep: '13614032', street: 'Rua de teste', city: 'Leme', state: 'SP' } }); await pending
  assert.equal(state.form.delivery_address, 'Endereço já corrigido pelo operador, 150, Leme/SP')
  assert.equal(state.addressLookup.delivery.result, null)
})

test('frete: resposta de editor fechado não altera a próxima locação', async t => {
  let resolve
  const { state, quote } = mount(t, () => new Promise(done => { resolve = done }))
  await flush(); state.open(quote); await flush()
  const pending = state.calculateFreight('delivery')
  state.modal = false
  state.open({ ...quote, id: 2, transport_fee: '80.00', estimated_transport_fee: '80.00' })
  resolve(estimate()); await pending
  assert.equal(state.form.transport_fee, '80.00')
  assert.equal(state.addressLookup.delivery.result, null)
})

test('buscar CEP preserva o número digitado enquanto a consulta está em andamento', async t => {
  let resolve
  const {state,quote}=mount(t,()=>new Promise(done=>{resolve=done}))
  await flush();state.open(quote);await flush()
  const pending=state.searchAddress('delivery')
  assert.match(state.stepProblem(2),/consulta do CEP/)
  state.form.delivery_number='777'
  resolve({data:{cep:'13614032',street:'Rua consultada',neighborhood:'Centro',city:'Leme',state:'SP'}})
  await pending
  assert.equal(state.form.delivery_number,'777')
  assert.equal(state.form.delivery_address,'Rua consultada, Centro, Leme/SP, CEP 13614-032')
})

test('frete: ajuste manual continua após recálculo e é salvo com justificativa e horários', async t => {
  const { state, quote, writes } = mount(t)
  await flush(); state.open(quote); await flush()
  state.form.transport_fee = 100; state.freightManuallyEdited = true
  await state.calculateFreight('delivery')
  assert.equal(state.form.transport_fee, 100)
  assert.equal(state.form.estimated_transport_fee, 30)
  assert.match(state.stepProblem(3), /Justifique/)
  state.form.transport_fee_adjustment_reason = 'Condição comercial de teste'
  state.scheduleDelivery = true; state.scheduleReturn = true
  state.form.requested_delivery_at = '2026-11-02T09:30'
  state.form.requested_return_at = '2026-11-04T16:00'
  await state.calculateFreight('delivery')
  await state.save()
  assert.equal(writes.length, 1)
  assert.equal(writes[0].payload.transport_fee, 100)
  assert.equal(writes[0].payload.estimated_transport_fee, 30)
  assert.equal(writes[0].payload.transport_fee_adjustment_reason, 'Condição comercial de teste')
  assert.equal(writes[0].payload.requested_delivery_at, new Date('2026-11-02T09:30').toISOString())
  assert.equal(writes[0].payload.requested_return_at, new Date('2026-11-04T16:00').toISOString())
})

test('frete: falha de rota exige cálculo ou valor manual justificado e desmarcar transporte zera o total', async t => {
  const { state, quote } = mount(t, async () => ({ data: { estimate: { fee: null, reason: 'Sem rota' } } }))
  await flush(); state.open(quote); await flush()
  await state.calculateFreight('delivery')
  assert.equal(state.form.transport_fee, 0)
  assert.match(state.stepProblem(3), /Calcule o frete/)
  state.freightManuallyEdited = true
  assert.match(state.stepProblem(3), /Justifique/)
  state.form.transport_fee = 50; state.form.transport_fee_adjustment_reason = 'Frete acordado manualmente'
  assert.equal(state.stepProblem(3), '')
  state.form.delivery_transport_required = false
  assert.equal(state.form.transport_fee, 0)
  assert.equal(state.form.estimated_transport_fee, 0)
  assert.equal(state.stepProblem(3), '')
})
