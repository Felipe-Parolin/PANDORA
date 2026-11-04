import assert from 'node:assert/strict'
import test from 'node:test'
import { mountView, flush } from './helpers/mountView.mjs'

const order = (overrides = {}) => ({ id: 1, equipment: 1, maintenance_type: 'CORRECTIVE', priority: 'NORMAL', symptoms: 'Verificar motor', diagnosis: '', technician: null, status: 'OPEN', final_tests: '', released: false, labor_hours: 0, parts_used: '', activities: [], ...overrides })

test('cliente: notas e CEP sobrevivem à edição; cadastro novo não herda dados anteriores', async t => {
  const { state } = mountView(t, 'PeopleView'); await flush()
  state.openCustomer({ name: 'Cliente', notes: 'Entrar pelo portão lateral', address: 'Rua de teste, 120', address_cep: '13614032' })
  assert.equal(state.customerForm.notes, 'Entrar pelo portão lateral')
  assert.equal(state.customerForm.address_cep, '13614032')
  state.openCustomer()
  assert.equal(state.customerForm.notes, '')
  assert.equal(state.customerForm.address_cep, '')
})

test('locação: endereço do cadastro é inicial; alteração local e endereço antigo não são sobrescritos', async t => {
  const { state } = mountView(t, 'RentalsView'); await flush()
  state.customers = [{ id: 1, name: 'A', address: 'Rua Alfa, 120', address_cep: '13614032' }, { id: 2, name: 'B', address: 'Rua Beta, 50', address_cep: '13610000' }]
  state.open(); state.form.customer = 1
  assert.equal(state.form.delivery_address, 'Rua Alfa'); assert.equal(state.form.delivery_number,'120')
  assert.equal(state.form.return_cep, '13614032')
  state.addressSource.delivery = 'custom'; state.form.delivery_address = 'Obra, 300'
  state.form.customer = 2
  assert.equal(state.form.delivery_address, 'Obra, 300')
  assert.equal(state.form.return_address, 'Rua Beta'); assert.equal(state.form.return_number,'50')
  state.useCustomerAddress('delivery')
  assert.equal(state.form.delivery_address, 'Rua Beta'); assert.equal(state.form.delivery_number,'50')
  state.open({ customer: 1, items: [], delivery_address: 'Endereço antigo, 1', delivery_cep: '13614032', return_address: '', return_cep: '', subtotal: 0 })
  assert.equal(state.form.delivery_address, 'Endereço antigo'); assert.equal(state.form.delivery_number,'1')
  assert.equal(state.addressSource.delivery, 'custom')
})

test('OS de oficina: checklist do plano tem progresso persistente e bloqueia conclusão incompleta', async t => {
  const writes = []
  const { state } = mountView(t, 'MaintenanceView', {
    api: {
      post: async () => ({ data: {} }), get: async () => ({ data: {} }),
      patch: async (url, data) => {
        writes.push(structuredClone(data))
        return { data: { activities: data.activities.map((item, i) => ({ ...item, id: i+10 })) } }
      },
    },
  })
  await flush()
  state.plans = [{ id: 5, checklist: ['Limpar proteção', { label: 'Testar motor' }] }]
  state.orders = [order({ plan: 5 })]
  state.openOrder(state.orders[0]); await flush()
  assert.equal(state.modal, 'order')
  assert.deepEqual(state.orderActivities.map(item => item.description), ['Limpar proteção', 'Testar motor'])
  state.orderForm.diagnosis = 'Cabo reparado'; state.orderActivities[0].completed = true
  assert.equal(await state.saveOrderProgress(), true)
  assert.equal(writes[0].activities[0].completed, true)
  assert.equal(state.orderActivities[0].id, 10)
  assert.equal(state.orders[0].activities[0].completed, true)
  state.orderStep = 3; state.orderStep = 1
  assert.equal(state.orderForm.diagnosis, 'Cabo reparado')
  state.orderForm.status = 'COMPLETED'
  assert.equal(await state.saveOrderProgress(), false)
  assert.equal(state.orderStep, 2)
  assert.equal(writes.length, 1)
  state.orderActivities[1].completed = true
  assert.equal(await state.saveOrderProgress(), true)
})

test('OS de locação: inspeção encerra a OS sem reenviar status antigo nem perder diagnóstico', async t => {
  const initial = order({ rental_inspection: 7, rental_quote_id: 9, rental_quote_status: 'APPROVED', maintenance_type: 'PRE_RENTAL', inspection_result: 'PENDING' })
  let current = initial
  const writes = []
  const { state } = mountView(t, 'MaintenanceView', {
    fetchAll: async url => ({ data: url === '/service-orders/' ? [current] : [] }),
    api: { post: async () => ({ data: {} }), get: async () => ({ data: { id: 9, status: 'APPROVED' } }), patch: async (url, data) => { writes.push(data); current = { ...current, ...data }; return { data: current } } },
  }); await flush()
  state.openOrder(initial); await flush()
  assert.equal(state.inspectionContext.initialId, 7)
  state.orderForm.diagnosis = 'Conferido pelo técnico'
  assert.equal(await state.saveOrderProgress(), true)
  assert.equal('released' in writes[0], false)
  current = { ...current, status: 'COMPLETED', inspection_result: 'APPROVED', released: true, final_tests: 'Checklist aprovado.' }
  await state.inspectionChanged()
  assert.equal(state.orderForm.status, 'COMPLETED')
  assert.equal(state.orderEditable, false)
  assert.equal(state.orderForm.diagnosis, 'Conferido pelo técnico')
  await state.saveOrderProgress()
  assert.equal(writes.length, 1)
})

test('OS: resposta de checklist antigo não substitui o próximo atendimento e consulta não escreve', async t => {
  let resolve
  const { state } = mountView(t, 'MaintenanceView', { api: { post: async () => ({ data: {} }), get: () => new Promise(done => { resolve = done }) } }); await flush()
  state.openOrder(order({ rental_inspection: 7, rental_quote_id: 9, maintenance_type: 'PRE_RENTAL' }))
  state.openOrder(order({ id: 2, activities: [{ id: 10, description: 'Novo', completed: true }] }))
  resolve({ data: { id: 9 } }); await flush()
  assert.equal(state.inspectionContext, null)
  assert.equal(state.orderActivities[0].description, 'Novo')
  const readonly = mountView(t, 'MaintenanceView', { can: () => false }); await flush()
  readonly.state.openOrder(order({ activities: [{ description: 'Conferir', completed: false }] })); await flush()
  assert.equal(readonly.state.orderEditable, false)
  assert.equal(await readonly.state.saveOrderProgress(), true)
})

test('OS: continuar salva inspeção alterada e permanece no checklist quando ela falha', async t => {
  const { state } = mountView(t, 'MaintenanceView'); await flush()
  state.orderStep = 2
  let saves = 0
  state.inspectionEditor = { editable: true, hasChanges: true, save: async () => { saves++; return false } }
  await state.nextOrderStep()
  assert.equal(state.orderStep, 2)
  state.inspectionEditor.save = async () => { saves++; return true }
  await state.nextOrderStep()
  assert.equal(state.orderStep, 3)
  assert.equal(saves, 2)
})

test('orçamento: item com OS pendente não impede negociar com outro equipamento; aprovação continua bloqueada', async t => {
  const { state } = mountView(t, 'RentalsView'); await flush()
  state.form.start_date = '2026-11-02'; state.form.end_date = '2026-11-04'
  state.form.items = [{ equipment_id: 1, name: 'Item existente', daily_rate: '100' }, { equipment_id: 2, name: 'Item novo', daily_rate: '200' }]
  state.selectionConflicts = [{ equipment: { id: 1, name: 'Item existente' }, reason: 'Existe uma ordem de serviço aberta para o equipamento.' }]
  await flush(); state.selectionLoading = false; state.selectionChecked = true
  state.form.status = 'SENT'; assert.equal(state.stepProblem(1), '')
  state.form.status = 'DRAFT'; assert.equal(state.stepProblem(1), '')
  state.form.status = 'APPROVED'; assert.match(state.stepProblem(1), /indisponibilidade/)
  assert.deepEqual(state.form.items.map(item => item.equipment_id), [1, 2])
})

test('locações carregam orçamentos e clientes sem consultar funcionalidades removidas', async t => {
  const quote = { id: 12, number: 'ORC-012', items: [] }
  const customer = { id: 3, name: 'Cliente' }
  const requested = []
  const { state } = mountView(t, 'RentalsView', {
    fetchAll: async url => {
      requested.push(url)
      if (url === '/rental-quotes/') return { data: [quote] }
      if (url === '/customers/') return { data: [customer] }
      throw new Error(`Consulta inesperada: ${url}`)
    },
  })
  await flush()
  assert.deepEqual(requested, ['/rental-quotes/', '/customers/'])
  assert.deepEqual(state.quotes, [quote])
  assert.deepEqual(state.customers, [customer])
  assert.equal(state.customersLoading, false)
})
