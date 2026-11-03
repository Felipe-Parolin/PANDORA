import assert from 'node:assert/strict'
import test from 'node:test'
import { matchesSearch, sortRecords } from '../src/services/listFilters.js'
import { mountView, flush } from './helpers/mountView.mjs'

test('ordenação: comparação natural em português, números, ausentes ao fim e lista preservada', () => {
  const records = [{ name: 'Item 10', amount: '10.50' }, { name: 'item 2', amount: '2.00' }, { name: null, amount: null }]
  assert.deepEqual(sortRecords(records, 'name', { name: item => item.name }).map(item => item.name), ['item 2', 'Item 10', null])
  assert.deepEqual(sortRecords(records, '-amount', { amount: item => item.amount == null ? null : Number(item.amount) }).map(item => item.amount), ['10.50', '2.00', null])
  assert.equal(records[0].name, 'Item 10')
  assert.equal(matchesSearch(' joao ', 'João'), true)
  assert.equal(matchesSearch('xyz', null, undefined), false)
})

test('pessoas: busca combinada com situação/tipo e ordenação antes de paginar', async t => {
  const { state } = mountView(t, 'PeopleView'); await flush()
  state.customers = Array.from({ length: 24 }, (_, i) => ({ id: i+1, name: `Cliente ${i+1}`, person_type: 'PF', is_active: true }))
  state.customers.push({ id: 30, name: 'Cliente inativo', person_type: 'PF', is_active: false })
  state.activity = 'active'; state.personType = 'PF'; state.ordering = '-id'
  await flush()
  assert.equal(state.customerRows.length, 10)
  assert.equal(state.customerRows[0].id, 24)
  state.customerPage = 3; state.search = 'Cliente 2'; await flush()
  assert.equal(state.customerPage, 1)
  assert.equal(state.filteredCustomers.some(item => item.id === 30), false)
  state.users = [{ id: 1, full_name: 'João', access_group: 2, is_active: true }, { id: 2, full_name: 'Maria', access_group: 3, is_active: true }]
  state.search = 'joao'; state.accessGroup = '2'
  assert.deepEqual(state.filteredUsers.map(item => item.id), [1])
  state.groups = [{ id: 1, name: 'Padrão', is_system: true, user_count: 10 }, { id: 2, name: 'Personalizado', is_system: false, user_count: 2 }]
  state.search = ''; state.groupKind = 'custom'; state.ordering = '-users'
  assert.deepEqual(state.filteredGroups.map(item => item.id), [2])
})

test('categorias e veículos: filtros de domínio usam IDs e situação real de viagem', async t => {
  const equipment = mountView(t, 'EquipmentView'); await flush()
  equipment.state.categories = [{ id: 1, name: 'Máquinas' }, { id: 2, name: 'Compactação', parent: 1, parent_name: 'Máquinas' }, { id: 3, name: 'Geradores' }]
  equipment.state.categorySearch = 'compactacao'; equipment.state.categoryParent = '1'; equipment.state.categoryKind = 'child'
  assert.deepEqual(equipment.state.filteredCategories.map(item => item.id), [2])
  const vehicles = mountView(t, 'VehiclesView'); await flush()
  vehicles.state.vehicles = [{ id: 1, plate: 'ABC1D23', status: 'AVAILABLE', in_transit: true, vehicle_type: 'TRUCK', capacity_kg: 1000 }, { id: 2, plate: 'XYZ1D23', status: 'AVAILABLE', in_transit: false, vehicle_type: 'TRUCK', capacity_kg: 500 }]
  vehicles.state.vehicleStatus = 'AVAILABLE'; vehicles.state.vehicleType = 'TRUCK'; vehicles.state.ordering = '-capacity'
  assert.deepEqual(vehicles.state.filtered.map(item => item.id), [2])
})

test('locações: valor numérico, transporte, cliente e sobreposição do período', async t => {
  const { state } = mountView(t, 'RentalsView'); await flush()
  state.quotes = [
    { id: 1, number: 'ORC-1', customer: 1, customer_name: 'João', start_date: '2026-11-01', end_date: '2026-11-10', total: '99.00', status: 'SENT', items: [], delivery_transport_required: true },
    { id: 2, number: 'ORC-2', customer: 1, customer_name: 'João', start_date: '2026-11-03', end_date: '2026-11-08', total: '1000.00', status: 'SENT', items: [], delivery_transport_required: true },
    { id: 3, number: 'ORC-3', customer: 2, customer_name: 'Maria', start_date: '2026-12-01', end_date: '2026-12-02', total: '50.00', status: 'SENT', items: [] },
  ]
  state.quoteSearch = 'joao'; state.quoteCustomer = '1'; state.quoteTransport = 'delivery'; state.quoteFrom = '2026-11-05'; state.quoteTo = '2026-11-06'; state.quoteOrdering = '-total'
  assert.deepEqual(state.filteredQuotes.map(item => item.id), [2, 1])
})

test('manutenção: prioridade, responsável e etapa mantêm o vínculo das ordens à locação', async t => {
  const { state } = mountView(t, 'MaintenanceView'); await flush()
  state.orders = Array.from({ length: 12 }, (_, i) => ({ id: i+1, number: `OS-${i+1}`, maintenance_type: 'PRE_RENTAL', status: 'OPEN', priority: 'ALTA', equipment: i+1, equipment_name: 'Máquina', rental_quote_id: i+1, rental_quote_number: `ORC-${i+1}`, rental_customer_name: 'Cliente', technician: 1 }))
  state.priorityFilter = 'ALTA'; state.technicianFilter = '1'; state.ordering = 'number'; await flush()
  assert.equal(state.rentalGroupRows.length, 10)
  assert.equal(state.rentalGroupRows[0].orders[0].number, 'OS-1')
  state.rentalGroupPage = 2; state.search = 'ORC-12'; await flush()
  assert.equal(state.rentalGroupPage, 1)
  assert.equal(state.rentalGroups.length, 1)
  state.technicianFilter = 'none'
  assert.equal(state.filteredOrders.length, 0)
  state.selectTab('workshop')
  assert.equal(state.priorityFilter, '')
  assert.equal(state.technicianFilter, '')
})

test('seleção: marca, diária e ordenação chegam às páginas da API; limpar filtros mantém os itens escolhidos', async t => {
  const calls = []
  const { state } = mountView(t, 'RentalsView', { api: { get: async (url, config) => {
    calls.push({ url, params: { ...config?.params } })
    return { data: url === '/rental-quotes/availability/' ? { available: [], blocked: [], count: 0, next_page: null } : { results: [] } }
  } } })
  await flush(); state.open(); await flush()
  state.form.items = [{ equipment_id: 1, name: 'Item escolhido', daily_rate: '100', quantity_days: 1 }]
  state.selectedCategory = { id: 3, name: 'Categoria' }
  state.equipmentSearch = 'Honda'; state.pickerBrand = 'Honda'; state.pickerMinRate = '50'; state.pickerMaxRate = '150'; state.pickerOrdering = '-daily_rate'
  state.availabilityNext = 2
  await state.loadAvailability(true)
  const params = calls.filter(item => item.url === '/rental-quotes/availability/').at(-1).params
  assert.equal(params.page, 2)
  assert.equal(params.ordering, '-daily_rate')
  assert.equal(params.brand, 'Honda')
  assert.equal(params.min_daily_rate, '50')
  assert.equal(params.max_daily_rate, '150')
  assert.equal(params.category, undefined)
  state.clearPickerFilters()
  assert.equal(state.showList, false)
  assert.equal(state.form.items.length, 1)
})

test('planos: tabela pagina dez registros e mantém a abertura para edição ou consulta conforme a permissão', async t => {
  const { state } = mountView(t, 'MaintenanceView'); await flush()
  state.plans = Array.from({ length: 13 }, (_, i) => ({ id: i+1, name: `Plano ${i+1}`, equipment: 1, maintenance_type: 'PREVENTIVE', interval_days: 90, active: true, checklist: [] }))
  state.plans.push({ id: 99, name: 'Plano pré-locação', equipment: 1, maintenance_type: 'PRE_RENTAL', checklist: [] })
  state.selectTab('workshop'); await flush()
  assert.equal(state.categoryPlans.length, 13)
  assert.equal(state.planRows.length, 10)
  state.planPage = 2
  assert.deepEqual(state.planRows.map(item => item.id), [11, 12, 13])
  state.openPlan(state.planRows[2])
  assert.equal(state.editing.id, 13)
  assert.equal(state.planForm.name, 'Plano 13')
  assert.equal(state.modal, 'plan')
  state.selectTab('rental'); await flush()
  assert.equal(state.planPage, 1)
  assert.deepEqual(state.planRows.map(item => item.id), [99])
  const readonly = mountView(t, 'MaintenanceView', { can: () => false }); await flush()
  readonly.state.openPlan(state.plans[0])
  assert.equal(readonly.state.modal, 'plan-detail')
})

test('comercial: filtros não desmarcam destinatários ocultos nem liberam contatos sem consentimento', async t => {
  const { state } = mountView(t, 'CommercialView'); await flush()
  state.customers = [{ id: 1, name: 'Ana', email: 'ana@example.invalid', person_type: 'PF', is_active: true, marketing_opt_in: true }, { id: 2, name: 'Empresa', email: 'empresa@example.invalid', person_type: 'PJ', is_active: true, marketing_opt_in: true }, { id: 3, name: 'Sem autorização', email: 'nao@example.invalid', person_type: 'PJ', is_active: true, marketing_opt_in: false }]
  state.selectedCustomers = [1, 2]; state.recipientType = 'PJ'; state.recipientOrdering = '-name'
  assert.deepEqual(state.filteredRecipients.map(item => item.id), [2])
  assert.deepEqual([...state.selectedCustomers], [1, 2])
  state.recommendations = [{id:1,category_name:'Corte',priority:'HIGH',status:'PENDING',suggested_quantity:2},{id:2,category_name:'Corte',priority:'HIGH',status:'PENDING',suggested_quantity:4},{id:3,category_name:'Concreto',priority:'MEDIUM',status:'APPROVED',suggested_quantity:1}]
  state.purchaseSearch='Corte';state.purchaseStatus='PENDING';state.purchasePriority='HIGH';state.purchaseOrdering='-quantity'
  assert.deepEqual(state.filteredRecommendations.map(item=>item.id),[2,1])
  assert.equal(state.tab,'billing')
  state.campaigns = [{ id: 1, title: 'Agendada', status: 'READY', scheduled_at: '2026-11-10T10:00:00Z' }, { id: 2, title: 'Rascunho', status: 'DRAFT' }]
  state.campaignStatus = 'READY'; state.campaignSchedule = 'scheduled'
  assert.deepEqual(state.filteredCampaigns.map(item => item.id), [1])
})

test('viagens e agenda: ordenação usa instantes, mantém sem data no fim e usa a lista completa', async t => {
  const { state } = mountView(t, 'LogisticsView', { fetchAll: async url => ({ data: { results: url === '/transport-tasks/' ? Array.from({ length: 43 }, (_, i) => ({ id: i+1, leg: 'DELIVERY', status: 'PLANNED' })) : [] } }) }); await flush()
  assert.equal(state.trips.length, 43)
  state.trips = [{ id: 1, leg: 'DELIVERY', status: 'PLANNED', vehicle: 1, customer_name: 'B', scheduled_at: null }, { id: 2, leg: 'DELIVERY', status: 'PLANNED', vehicle: 1, customer_name: 'A', scheduled_at: '2026-11-03T12:00:00Z' }, { id: 3, leg: 'RETURN', status: 'PLANNED', vehicle: 2, customer_name: 'C' }]
  state.tripLeg = 'DELIVERY'; state.tripVehicle = '1'; state.tripOrdering = '-scheduled'
  assert.deepEqual(state.visibleTrips.map(item => item.id), [2, 1])
  state.trips[0].driver = 9; state.trips[0].driver_name = 'Motorista do histórico'
  assert.deepEqual(state.driverOptions.map(item => item.id), ['9'])
  state.agendaRows = [...state.trips]; state.agendaOrdering = 'customer'
  assert.deepEqual(state.visibleAgendaRows.map(item => item.customer_name), ['A', 'B', 'C'])
  state.agendaStart = '2026-11-10'; state.agendaEnd = '2026-11-01'
  await state.loadAgenda()
  assert.match(state.error, /período válido/)
})
