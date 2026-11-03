<script setup>
import { formatPlate, formatDate } from '../services/formatters'
import { matchesSearch, sortRecords, dateValue } from '../services/listFilters'
import { usePagination } from '../services/pagination'
import { toDateTimeInput, toDateTimePayload } from '../services/formDates'
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { CalendarClock, CheckCircle2, ClipboardList, MapPin, Pencil, PlayCircle, Plus, Search, Trash2, Truck, FileDown } from 'lucide-vue-next'
import ConfirmDialog from '../components/ConfirmDialog.vue'
import DayPlanPanel from '../components/DayPlanPanel.vue'
import ModalDialog from '../components/ModalDialog.vue'
import StatusBadge from '../components/StatusBadge.vue'
import { api, apiError, can, rows, shortDate, fetchAll } from '../services/api'

const route = useRoute(), router = useRouter()
const tab = ref('trips')
const queue = ref('ALL')
const search = ref('')
const tripVehicle = ref(''), tripDriver = ref(''), tripLeg = ref(''), tripOrdering = ref('scheduled')
const agendaOrdering = ref('scheduled'), agendaMore = ref(false), agendaLoading = ref(false)
const tripSortOptions = [['scheduled', 'Agenda próxima'], ['-scheduled', 'Agenda distante'], ['customer', 'Cliente A–Z'], ['number', 'Nº da locação'], ['-created', 'Mais recentes']]
const tripSortFields = { scheduled: item => dateValue(item.scheduled_at), created: item => dateValue(item.created_at), customer: item => item.customer_name, number: item => item.quote_number }
const trips = ref([])
const agendaRows = ref([])
const agendaStart = ref(new Date().toLocaleDateString('en-CA'))
const agendaEnd = ref(new Date(Date.now() + 6 * 86400000).toLocaleDateString('en-CA'))
const agendaCity = ref('')
const agendaLeg = ref('')
const agendaStatus = ref('')
const agendaVehicle = ref('')
const agendaDriver = ref('')
const agendaCustomer = ref('')
const agendaTimeStart = ref('')
const agendaTimeEnd = ref('')
const agendaMode = ref('list')
const vehicles = ref([])
const employees = ref([])
const driverOptions = computed(() => [...new Map([
  ...employees.value.map(item => [String(item.id), item.full_name]),
  ...[...trips.value, ...agendaRows.value].filter(item => item.driver).map(item => [String(item.driver), item.driver_name]),
]).entries()].map(([id, name]) => ({ id, name })).sort((a, b) => String(a.name).localeCompare(String(b.name), 'pt-BR')))
const editingTrip = ref(null)
const modal = ref(null)
const busy = ref(false)
const error = ref('')
const notice = ref('')

const tripForm = reactive({ rental_item_ids: [], vehicle: '', driver: '', address: '', address_cep: '', complement: '', scheduled_at: '', scheduled_end_at: '', trip_reference: '', load_sequence: 1, load_manifest_text: '', notes: '' })
watch(() => tripForm.rental_item_ids.join(','), () => {
  const removed = new Set((editingTrip.value?.items || []).filter(item => !tripForm.rental_item_ids.includes(item.id)).map(item => item.internal_code.toUpperCase()))
  tripForm.load_manifest_text = tripForm.load_manifest_text.split('\n').filter(code => !removed.has(code.trim().toUpperCase())).join('\n')
}, { flush: 'sync' })
const queues = computed(() => [
  { key: 'ALL', label: 'Todas' }, { key: 'PLANNED', label: 'A planejar' },
  { key: 'IN_TRANSIT', label: 'Em transporte' }, { key: 'COMPLETED', label: 'Concluídas' },
  { key: 'CANCELLED', label: 'Canceladas' },
].map(item => ({ ...item, count: trips.value.filter(trip => item.key === 'ALL' || trip.status === item.key).length })))
const visibleTrips = computed(() => sortRecords(trips.value.filter(trip => (!route.query.trip || String(trip.id) === String(route.query.trip)) && (queue.value === 'ALL' || trip.status === queue.value) && (!tripVehicle.value || String(trip.vehicle) === tripVehicle.value) && (!tripDriver.value || String(trip.driver) === tripDriver.value) && (!tripLeg.value || trip.leg === tripLeg.value) && matchesSearch(search.value, trip.quote_number, trip.customer_name, trip.vehicle_plate, trip.driver_name, trip.trip_reference, trip.address)), tripOrdering.value, tripSortFields))
function clearTripFilters() { search.value = ''; queue.value = 'ALL'; tripVehicle.value = ''; tripDriver.value = ''; tripLeg.value = ''; tripOrdering.value = 'scheduled' }
const visibleAgendaRows = computed(() => sortRecords(agendaRows.value, agendaOrdering.value, tripSortFields))
const availableVehicles = computed(() => vehicles.value.filter(vehicle => vehicle.status === 'AVAILABLE' && !vehicle.in_transit))
const agendaDays = computed(() => { const groups = new Map(); for (const task of visibleAgendaRows.value) { const key = task.scheduled_at ? new Date(task.scheduled_at).toLocaleDateString('en-CA') : 'sem-data'; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(task) } return [...groups.entries()].sort(([a], [b]) => agendaOrdering.value === '-scheduled' ? b.localeCompare(a) : a.localeCompare(b)) })

function setAgendaMode(mode) {
  agendaMode.value = mode
  const base = new Date(`${agendaStart.value}T12:00:00`)
  if (mode === 'day') agendaEnd.value = agendaStart.value
  else if (mode === 'week') { const end = new Date(base); end.setDate(end.getDate() + 6); agendaEnd.value = end.toLocaleDateString('en-CA') }
  else if (mode === 'month') { const first = new Date(base.getFullYear(), base.getMonth(), 1); const last = new Date(base.getFullYear(), base.getMonth() + 1, 0); agendaStart.value = first.toLocaleDateString('en-CA'); agendaEnd.value = last.toLocaleDateString('en-CA') }
  loadAgenda()
}

let agendaRequest = 0
async function loadAgenda() {
  if (!agendaStart.value || !agendaEnd.value || agendaEnd.value < agendaStart.value) { error.value = 'Informe um período válido para a agenda.'; return }
  const request = ++agendaRequest
  agendaLoading.value = true; error.value = ''
  try {
    const { data } = await api.get('/transport-tasks/agenda/', { params: { start: agendaStart.value, end: agendaEnd.value, city: agendaCity.value || undefined, leg: agendaLeg.value || undefined, status: agendaStatus.value || undefined, vehicle: agendaVehicle.value || undefined, driver: agendaDriver.value || undefined, customer: agendaCustomer.value || undefined, start_time: agendaTimeStart.value || undefined, end_time: agendaTimeEnd.value || undefined } })
    if (request === agendaRequest) { agendaRows.value = data.results || []; agendaPage.value = 1 }
  } catch (event) { if (request === agendaRequest) error.value = apiError(event) }
  finally { if (request === agendaRequest) agendaLoading.value = false }
}
function clearAgendaFilters() { agendaCity.value = ''; agendaLeg.value = ''; agendaStatus.value = ''; agendaVehicle.value = ''; agendaDriver.value = ''; agendaCustomer.value = ''; agendaTimeStart.value = ''; agendaTimeEnd.value = ''; agendaOrdering.value = 'scheduled'; loadAgenda() }

async function load() {
  const [tripResponse, vehicleResponse, userResponse] = await Promise.all([
    fetchAll('/transport-tasks/'), fetchAll('/vehicles/'),
    can('accounts.users.view') ? fetchAll('/users/') : Promise.resolve({ data: [] }),
  ])
  trips.value = rows(tripResponse.data)
  vehicles.value = rows(vehicleResponse.data)
  employees.value = rows(userResponse.data).filter(user => user.is_active)
}

function openTrip(trip) {
  editingTrip.value = trip
  error.value = ''
  modal.value = 'trip'
  Object.assign(tripForm, {
    rental_item_ids: (trip.items || []).map(item => item.id),
    vehicle: trip.vehicle || '', driver: trip.driver || '', address: trip.address, address_cep: trip.address_cep || '', complement: trip.complement || '',
    scheduled_at: toDateTimeInput(trip.scheduled_at), scheduled_end_at: toDateTimeInput(trip.scheduled_end_at), trip_reference: trip.trip_reference || '', load_sequence: trip.load_sequence || 1, load_manifest_text: (trip.load_manifest || []).join('\n'), notes: trip.notes || '',
  })
}

async function saveTrip() {
  if (editingTrip.value.items?.length && !tripForm.rental_item_ids.length) { error.value = 'Selecione pelo menos um equipamento para esta viagem.'; return }
  busy.value = true
  error.value = ''
  try {
    await api.patch(`/transport-tasks/${editingTrip.value.id}/`, {
      ...(editingTrip.value.items?.length ? { rental_item_ids: tripForm.rental_item_ids } : {}),
      vehicle: tripForm.vehicle || null, driver: tripForm.driver || null,
      address: tripForm.address.trim(), address_cep: tripForm.address_cep || '', complement: tripForm.complement.trim(), scheduled_at: toDateTimePayload(tripForm.scheduled_at), scheduled_end_at: toDateTimePayload(tripForm.scheduled_end_at), trip_reference: tripForm.trip_reference, load_sequence: Number(tripForm.load_sequence || 1), load_manifest: tripForm.load_manifest_text.split('\n').map(code => code.trim().toUpperCase()).filter(Boolean), notes: tripForm.notes,
    })
    modal.value = null
    notice.value = 'Viagem planejada.'
    await load()
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}


async function downloadOrder(trip) {
  try {
    const response = await api.get(`/transport-tasks/${trip.id}/loading-order/`, { responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = `ordem-carregamento-${trip.id}.pdf`
    document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url)
  } catch (event) { error.value = apiError(event) }
}

async function transition(trip, action) {
  busy.value = true
  error.value = ''
  notice.value = ''
  try {
    await api.post(`/transport-tasks/${trip.id}/${action}/`)
    notice.value = action === 'start' ? 'Viagem iniciada.' : 'Viagem concluída. A locação pode avançar para a próxima etapa.'
    await load()
  } catch (event) { error.value = apiError(event) }
  finally { busy.value = false }
}

onMounted(async () => {
  try {
    if (route.query.tab === 'vehicles') { await router.replace('/veiculos'); return }
    if (route.query.tab === 'dayplan') tab.value = 'dayplan'
    if (route.query.leg && ['DELIVERY', 'RETURN'].includes(String(route.query.leg))) {
      tab.value = 'agenda'
      agendaLeg.value = String(route.query.leg)
    }
    await load()
    if (route.query.quote) search.value = String(route.query.quote)
    if (tab.value === 'agenda') await loadAgenda()
  } catch (event) { error.value = apiError(event) }
})

const { page: tripPage, items: tripRows } = usePagination(visibleTrips, [search, queue, tripVehicle, tripDriver, tripLeg, tripOrdering])
const { page: agendaPage, items: agendaPageRows } = usePagination(visibleAgendaRows, [agendaOrdering])
</script>

<template>
  <div class="page logistics-page">
    <header class="page-heading compact"><div><span class="eyebrow">MOVIMENTAÇÃO DE EQUIPAMENTOS</span><h1>Transporte</h1><p>Planeje entregas e coletas apenas quando a locação precisar de veículo.</p></div></header>
    <router-link v-if="route.query.trip" to="/transporte" class="trip-context-link">Exibir todas as viagens</router-link><SuccessNotice v-if="notice" :message="notice" @close="notice = ''" />
    <GeneralError v-if="error && !modal" :message="error" @close="error = ''" />

    <div class="tabs section-tabs" role="tablist" aria-label="Áreas de transporte"><button role="tab" :aria-selected="tab === 'trips'" :class="{ active: tab === 'trips' }" @click="tab = 'trips'"><MapPin :size="17" />Viagens</button><button role="tab" :aria-selected="tab === 'dayplan'" :class="{ active: tab === 'dayplan' }" @click="tab = 'dayplan'"><ClipboardList :size="17" />Roteiro do dia</button><button role="tab" :aria-selected="tab === 'agenda'" :class="{ active: tab === 'agenda' }" @click="tab = 'agenda'; loadAgenda()"><CalendarClock :size="17" />Agenda</button></div>

    <template v-if="tab === 'trips'">
      <div class="workflow-tabs" role="tablist" aria-label="Filtrar viagens"><button v-for="item in queues" :key="item.key" :class="{ active: queue === item.key }" @click="queue = item.key"><span>{{ item.label }}</span><b>{{ item.count }}</b></button></div>
      <section class="panel list-panel">
        <ListToolbar><template #search><label class="list-control list-search"><span>Pesquisar</span><span class="search-box"><Search :size="17" /><input v-model="search" type="search" placeholder="Reserva, cliente, endereço ou placa" aria-label="Buscar viagens" /></span></label></template><template #filters><label class="list-control"><span>Operação</span><AppSelect v-model="tripLeg"><option value="">Todas</option><option value="DELIVERY">Entrega</option><option value="RETURN">Coleta</option></AppSelect></label><label class="list-control"><span>Veículo</span><AppSelect searchable v-model="tripVehicle"><option value="">Todos</option><option v-for="item in vehicles" :key="item.id" :value="String(item.id)">{{ formatPlate(item.plate) }}</option></AppSelect></label><label class="list-control"><span>Motorista</span><AppSelect searchable v-model="tripDriver"><option value="">Todos</option><option v-for="item in driverOptions" :key="item.id" :value="item.id">{{ item.name }}</option></AppSelect></label><ListOrdering v-model="tripOrdering" :options="tripSortOptions" /></template><template #meta><div class="filter-meta"><span class="result-count">{{ visibleTrips.length }} viagem(ns)</span><button class="btn secondary" type="button" @click="clearTripFilters">Limpar filtros</button></div></template></ListToolbar>
        <div class="table-wrap desktop-list"><table><thead><tr><th>Locação</th><th>Trajeto</th><th>Agendamento</th><th>Veículo / motorista</th><th>Status</th><th class="right">Ações</th></tr></thead><tbody>
          <tr v-for="trip in tripRows" :key="trip.id"><td><strong>{{ trip.quote_number }}</strong><small>{{ trip.customer_name }}</small><small v-if="trip.trip_reference">Viagem {{ trip.trip_reference }} · parada {{ trip.load_sequence }}</small></td><td><strong>{{ trip.leg_label }}</strong><small>{{ trip.address }}<template v-if="trip.complement"> · {{ trip.complement }}</template></small></td><td>{{ trip.scheduled_at ? formatDate(trip.scheduled_at) : 'A definir' }}</td><td><strong>{{ trip.vehicle_plate ? formatPlate(trip.vehicle_plate) : 'Sem veículo' }}</strong><small>{{ trip.driver_name || 'Sem motorista' }}</small></td><td><StatusBadge :value="trip.status" :label="trip.status_label" /></td><td class="right"><div class="row-actions"><button class="btn secondary download-action" title="Baixar ordem de carregamento em PDF" @click="downloadOrder(trip)"><FileDown :size="17" />PDF</button><button v-if="can('logistics.manage') && trip.status === 'PLANNED'" class="icon-btn table-action" title="Planejar viagem" @click="openTrip(trip)"><Pencil :size="17" /></button><button v-if="can('logistics.manage') && trip.status === 'PLANNED'" class="icon-btn success-action" title="Iniciar transporte" :disabled="busy" @click="transition(trip, 'start')"><PlayCircle :size="17" /></button><button v-if="can('logistics.manage') && trip.status === 'IN_TRANSIT'" class="icon-btn success-action" title="Concluir transporte" :disabled="busy" @click="transition(trip, 'complete')"><CheckCircle2 :size="17" /></button></div></td></tr>
          <tr v-if="!visibleTrips.length"><td colspan="6" class="empty-cell"><Truck :size="20" />Nenhuma viagem nesta fila.</td></tr>
        </tbody></table></div>
        <div class="mobile-card-list"><article v-for="trip in tripRows" :key="trip.id" class="mobile-record-card"><header><div><span class="eyebrow">{{ trip.quote_number }} · {{ trip.leg_label }}</span><strong>{{ trip.customer_name }}</strong><small v-if="trip.trip_reference">Viagem {{ trip.trip_reference }} · parada {{ trip.load_sequence }}</small></div><StatusBadge :value="trip.status" :label="trip.status_label" /></header><p class="trip-address"><MapPin :size="15" />{{ trip.address }}<template v-if="trip.complement"> · {{ trip.complement }}</template></p><dl><div><dt>Agendamento</dt><dd>{{ trip.scheduled_at ? formatDate(trip.scheduled_at) : 'A definir' }}</dd></div><div><dt>Veículo</dt><dd>{{ trip.vehicle_plate ? formatPlate(trip.vehicle_plate) : 'Não atribuído' }}</dd></div><div><dt>Motorista</dt><dd>{{ trip.driver_name || 'Não atribuído' }}</dd></div></dl><footer><button class="btn secondary" @click="downloadOrder(trip)"><FileDown :size="17" />Baixar PDF</button><button v-if="can('logistics.manage') && trip.status === 'PLANNED'" class="btn secondary" @click="openTrip(trip)"><CalendarClock :size="16" />Planejar</button><button v-if="can('logistics.manage') && trip.status === 'PLANNED'" class="btn primary" :disabled="busy" @click="transition(trip, 'start')"><PlayCircle :size="16" />Iniciar</button><button v-if="can('logistics.manage') && trip.status === 'IN_TRANSIT'" class="btn primary" :disabled="busy" @click="transition(trip, 'complete')"><CheckCircle2 :size="16" />Concluir</button></footer></article><div v-if="!visibleTrips.length" class="empty-state compact"><Truck :size="26" /><h2>Nenhuma viagem nesta fila</h2></div></div>
      <PaginationBar v-model="tripPage" :total="(visibleTrips).length" /></section>
    </template>

    <DayPlanPanel v-else-if="tab === 'dayplan'" />

    <template v-else-if="tab === 'agenda'">
      <section class="panel list-panel logistics-agenda-panel"><header class="list-toolbar"><div class="agenda-mode-tabs"><button :class="{ active: agendaMode === 'list' }" @click="agendaMode = 'list'">Lista</button><button :class="{ active: agendaMode === 'timeline' }" @click="agendaMode = 'timeline'">Linha do tempo</button><button :class="{ active: agendaMode === 'day' }" @click="setAgendaMode('day')">Dia</button><button :class="{ active: agendaMode === 'week' }" @click="setAgendaMode('week')">Semana</button><button :class="{ active: agendaMode === 'month' }" @click="setAgendaMode('month')">Mês</button></div></header><ListToolbar class="agenda-list-toolbar">
          <template #search><div class="agenda-search-fields"><label class="list-control"><span>Cidade / endereço</span><input v-model="agendaCity" type="search" placeholder="Filtrar endereço" /></label><label class="list-control"><span>Cliente</span><input v-model="agendaCustomer" type="search" placeholder="Nome ou ID" /></label></div></template>
          <template #filters><label class="list-control"><span>De</span><AppDateTime v-model="agendaStart" type="date" /></label><label class="list-control"><span>Até</span><AppDateTime v-model="agendaEnd" type="date" :min="agendaStart" /></label><label class="list-control"><span>Operação</span><AppSelect v-model="agendaLeg"><option value="">Todas</option><option value="DELIVERY">Entrega</option><option value="RETURN">Coleta</option></AppSelect></label><label class="list-control"><span>Situação</span><AppSelect v-model="agendaStatus"><option value="">Todas</option><option value="PLANNED">Planejada</option><option value="IN_TRANSIT">Em transporte</option><option value="COMPLETED">Concluída</option></AppSelect></label><ListOrdering v-model="agendaOrdering" :options="tripSortOptions" /><button type="button" class="btn primary" :disabled="agendaLoading" @click="loadAgenda">{{ agendaLoading ? 'Consultando...' : 'Consultar agenda' }}</button></template>
          <template #meta><div class="filter-meta"><span class="result-count">{{ visibleAgendaRows.length }} operação(ões)</span><div class="agenda-filter-actions"><button class="btn secondary" type="button" :aria-expanded="agendaMore" @click="agendaMore = !agendaMore">{{ agendaMore ? 'Menos filtros' : 'Mais filtros' }}<span v-if="agendaTimeStart || agendaTimeEnd || agendaVehicle || agendaDriver" class="filter-badge">Ativos</span></button><button class="btn secondary" type="button" @click="clearAgendaFilters">Limpar filtros</button></div></div></template>
          <template v-if="agendaMore" #more><div class="list-controls list-more-filters agenda-advanced"><label class="list-control"><span>Horário inicial</span><AppDateTime v-model="agendaTimeStart" type="time" /></label><label class="list-control"><span>Horário final</span><AppDateTime v-model="agendaTimeEnd" type="time" /></label><label class="list-control"><span>Veículo</span><AppSelect searchable v-model="agendaVehicle"><option value="">Todos</option><option v-for="v in vehicles" :key="v.id" :value="v.id">{{ formatPlate(v.plate) }}</option></AppSelect></label><label class="list-control"><span>Motorista</span><AppSelect searchable v-model="agendaDriver"><option value="">Todos</option><option v-for="item in driverOptions" :key="item.id" :value="item.id">{{ item.name }}</option></AppSelect></label></div></template>
        </ListToolbar>
        <div v-if="agendaMode === 'timeline' || agendaMode === 'day' || agendaMode === 'week' || agendaMode === 'month'" class="agenda-timeline"><section v-for="[day, tasks] in agendaDays" :key="day" class="agenda-day"><header><strong>{{ day === 'sem-data' ? 'Sem horário definido' : new Date(`${day}T12:00:00`).toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' }) }}</strong><span>{{ tasks.length }} operação(ões)</span></header><article v-for="task in tasks" :key="task.id" class="agenda-timeline-task"><time>{{ task.scheduled_at ? new Date(task.scheduled_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '—' }}</time><div><strong>{{ task.customer_name }} · {{ task.quote_number }}</strong><small>{{ task.address }}</small></div><span class="agenda-operation-tag" :class="task.leg.toLowerCase()">{{ task.leg_label }}</span><StatusBadge :value="task.status" :label="task.status_label"/></article></section><p v-if="!agendaRows.length" class="empty-cell">Nenhuma atividade agendada no período.</p></div>
        <div v-else class="table-wrap"><table><thead><tr><th>Data e hora</th><th>Operação</th><th>Cliente</th><th>Endereço</th><th>Veículo / motorista</th><th>Status</th></tr></thead><tbody><tr v-for="task in agendaPageRows" :key="task.id"><td>{{ task.scheduled_at ? new Date(task.scheduled_at).toLocaleString('pt-BR') : 'A definir' }}</td><td>{{ task.leg_label }}</td><td>{{ task.customer_name }}</td><td>{{ task.address }}</td><td>{{ task.vehicle_plate ? formatPlate(task.vehicle_plate) : 'Sem veículo' }} · {{ task.driver_name || 'Sem motorista' }}</td><td><StatusBadge :value="task.status" :label="task.status_label"/></td></tr><tr v-if="!agendaRows.length"><td colspan="6" class="empty-cell">Nenhuma atividade agendada no período.</td></tr></tbody></table><PaginationBar v-model="agendaPage" :total="visibleAgendaRows.length" /></div></section>
    </template>

    <ModalDialog v-if="modal === 'trip'" :title="`Planejar ${editingTrip.leg_label.toLowerCase()} · ${editingTrip.quote_number}`" wide @close="modal = null; error = ''"><form @submit.prevent="saveTrip"><div class="operation-context"><span class="eyebrow">{{ editingTrip.customer_name }}</span><strong>{{ editingTrip.leg_label }}</strong><small>{{ editingTrip.address }}<template v-if="editingTrip.complement"> · {{ editingTrip.complement }}</template></small></div><div class="form-grid transport-form"><fieldset v-if="editingTrip.items?.length" class="operation-item-selection span-2"><legend>Equipamentos desta viagem <span class="required-mark" aria-hidden="true">*</span></legend><label v-for="item in editingTrip.items" :key="item.id"><input v-model="tripForm.rental_item_ids" type="checkbox" :value="item.id" /><span><strong>{{ item.internal_code }} · {{ item.equipment_name }}</strong><small>{{ shortDate(item.start_date) }} a {{ shortDate(item.end_date) }}</small></span></label><small>Os itens desmarcados ficam em outra viagem a planejar, sem perder a reserva.</small></fieldset>
      <div class="form-field"><label>Veículo<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect searchable v-model="tripForm.vehicle" required><option value="">Selecione</option><option v-for="vehicle in vehicles.filter(item => availableVehicles.some(available => available.id === item.id) || item.id === editingTrip.vehicle)" :key="vehicle.id" :value="vehicle.id">{{ formatPlate(vehicle.plate) }} · {{ vehicle.brand }} {{ vehicle.model }}</option></AppSelect></div>
      <div class="form-field"><label>Motorista<span class="required-mark" aria-hidden="true"> *</span></label><AppSelect searchable v-model="tripForm.driver" required><option value="">Selecione</option><option v-for="user in employees" :key="user.id" :value="user.id">{{ user.full_name }}</option></AppSelect></div>
      <div class="form-field"><label>Início previsto<span class="required-mark" aria-hidden="true"> *</span></label><AppDateTime v-model="tripForm.scheduled_at" type="datetime-local" required /></div>
      <div class="form-field"><label>Término previsto</label><AppDateTime v-model="tripForm.scheduled_end_at" type="datetime-local" /></div>
      <div class="form-field"><label>Referência da viagem</label><input v-model="tripForm.trip_reference" maxlength="40" placeholder="Ex.: ROTA-01" /></div>
      <div class="form-field"><label>Sequência da parada</label><input v-model.number="tripForm.load_sequence" type="number" min="1" placeholder="Ex.: 1" /></div><div class="form-field span-2"><label>Ordem dos equipamentos no carregamento</label><textarea v-model="tripForm.load_manifest_text" rows="3" placeholder="Um código interno por linha, na ordem desejada. Ex.: EQ-001\nEQ-002" /></div>
      <div class="form-field span-2"><label>Endereço da entrega / coleta<span class="required-mark" aria-hidden="true"> *</span></label><input v-model="tripForm.address" required placeholder="Rua, número, bairro e cidade/UF" /></div>
      <div class="form-field"><label>CEP do destino</label><AppInput mask="cep" v-model="tripForm.address_cep" placeholder="00000-000" /></div><div class="form-field span-2"><label>Complemento (opcional)</label><input v-model="tripForm.complement" maxlength="120" placeholder="Bloco, apartamento, portão ou ponto de referência" /></div>
      <div class="form-field span-2"><label>Instruções de transporte</label><textarea v-model="tripForm.notes" rows="3" placeholder="Contato no local, acesso, carga ou cuidados com o equipamento." /></div>
    </div><div v-if="error" class="error-message">{{ error }}</div><div class="modal-actions"><button type="button" class="btn secondary" @click="modal = null; error = ''">Fechar</button><span class="spacer" /><button class="btn primary" :disabled="busy">{{ busy ? 'Salvando...' : 'Salvar viagem' }}</button></div></form></ModalDialog>

  </div>
</template>
