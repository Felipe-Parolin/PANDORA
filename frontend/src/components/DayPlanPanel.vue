<script setup>
import { formatPlate } from '../services/formatters'
// Roteiro do dia: tudo que deve ser entregue/retirado, por manhã e tarde, com peso disponível no veículo, mapa e PDF.
import { computed, onMounted, ref, watch } from 'vue'
import { ChevronLeft, ChevronRight, FileDown, MapPin, RefreshCw, Truck } from 'lucide-vue-next'
import RouteMap from './RouteMap.vue'
import StatusBadge from './StatusBadge.vue'
import { api, apiError } from '../services/api'

const vehicleLabel = vehicle => vehicle.plate ? String(vehicle.label || vehicle.plate).replace(vehicle.plate, formatPlate(vehicle.plate)) : vehicle.label
const COLORS = ['#c2410c', '#1d4ed8', '#047857', '#7e22ce', '#be123c', '#0f766e']
const localToday = () => new Date().toLocaleDateString('en-CA')

const day = ref(localToday())
const vehicleFilter = ref('')
const periodFilter = ref('ALL')
const plan = ref(null)
const loading = ref(false)
const error = ref('')
const focusId = ref(null)
const mapRef = ref(null)

const kg = value => value === null || value === undefined ? '—' : `${Number(value).toLocaleString('pt-BR', { maximumFractionDigits: 1 })} kg`
const longDate = computed(() => new Date(`${day.value}T12:00:00`).toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long', year: 'numeric' }))

let loadToken = 0
async function load(attempt = 0) {
  const token = ++loadToken
  loading.value = true; error.value = ''
  try {
    const { data } = await api.get('/transport-tasks/day-plan/', { params: { date: day.value, vehicle: vehicleFilter.value || undefined }, timeout: 120000 })
    if (token !== loadToken) return
    plan.value = data
    // Paradas ainda sem ponto no mapa: o servidor continua localizando os endereços; repete até completar (máx. 4 vezes).
    if (data.summary?.without_coordinates && attempt < 4) { await load(attempt + 1); return }
  } catch (e) { if (token === loadToken) error.value = apiError(e) }
  finally { if (token === loadToken) loading.value = false }
}

function shift(days) {
  const base = new Date(`${day.value}T12:00:00`)
  base.setDate(base.getDate() + days)
  day.value = base.toLocaleDateString('en-CA')
}

const downloading = ref(false)
async function downloadPdf() {
  if (downloading.value) return
  downloading.value = true
  error.value = ''
  try {
    const response = await api.get('/transport-tasks/day-plan-pdf/', { params: { date: day.value, vehicle: vehicleFilter.value || undefined }, responseType: 'blob' })
    const url = URL.createObjectURL(response.data)
    const anchor = document.createElement('a')
    anchor.href = url; anchor.download = `horario-entregas-${day.value}.pdf`
    document.body.appendChild(anchor); anchor.click(); anchor.remove(); URL.revokeObjectURL(url)
  } catch (e) { error.value = apiError(e) }
  finally { downloading.value = false }
}

const visiblePeriods = computed(() => (plan.value?.periods || []).filter(p => periodFilter.value === 'ALL' || p.key === periodFilter.value))

const PERIOD_NAMES = { MORNING: 'Manhã', AFTERNOON: 'Tarde' }
// Uma rota por veículo e período: o veículo sai do depósito, passa por todas as paradas do período e volta.
// A numeração é contínua no dia (parada 1, 2, 3…) e não muda ao filtrar por período.
const routes = computed(() => {
  if (!plan.value) return []
  const byId = new Map(plan.value.stops.map(s => [s.id, s]))
  const result = []
  let colorIndex = 0
  for (const vehicle of plan.value.vehicles) {
    const ordered = vehicle.stops.map(id => byId.get(id)).filter(Boolean)
    const numbered = ordered.map((s, i) => ({ id: s.id, n: i + 1, period: s.period, latitude: s.latitude, longitude: s.longitude, title: `${s.time} · ${s.action_label} · ${s.customer_name}`, subtitle: s.address }))
    for (const period of ['MORNING', 'AFTERNOON']) {
      if (periodFilter.value !== 'ALL' && periodFilter.value !== period) continue
      const stops = numbered.filter(s => s.period === period)
      if (!stops.length) continue
      result.push({ key: `${vehicle.vehicle || 'none'}-${period}`, label: `${vehicleLabel(vehicle)} · ${PERIOD_NAMES[period]}`, color: COLORS[colorIndex++ % COLORS.length], loop: true, stops })
    }
  }
  return result
})
const stopNumber = id => {
  for (const route of routes.value) { const hit = route.stops.find(s => s.id === id); if (hit) return hit.n }
  return null
}
const missingCoordinates = computed(() => (plan.value?.stops || []).filter(s => s.latitude === null))
const barPercent = profile => profile?.capacity_kg ? Math.min(100, (profile.peak_load_kg / profile.capacity_kg) * 100) : 0
const barClass = profile => profile?.overloaded ? 'over' : barPercent(profile) >= 80 ? 'warn' : ''

watch([day, vehicleFilter], () => load())
onMounted(() => load())
</script>

<template>
  <section class="panel dayplan">
    <div class="dayplan-toolbar">
      <button class="icon-btn" title="Dia anterior" @click="shift(-1)"><ChevronLeft :size="18" /></button>
      <label>Data<AppDateTime v-model="day" type="date" /></label>
      <button class="icon-btn" title="Próximo dia" @click="shift(1)"><ChevronRight :size="18" /></button>
      <div class="dayplan-filter-fields">
      <label>Veículo<AppSelect searchable v-model="vehicleFilter"><option value="">Todos</option><option v-for="v in (plan?.vehicles || []).filter(v => v.vehicle)" :key="v.vehicle" :value="v.vehicle">{{ formatPlate(v.plate) }}</option></AppSelect></label>
      <label>Período<AppSelect v-model="periodFilter"><option value="ALL">Manhã e tarde</option><option value="MORNING">Manhã</option><option value="AFTERNOON">Tarde</option></AppSelect></label>
      </div>
      <button class="btn secondary" :disabled="loading" @click="() => load()"><RefreshCw :size="16" />Atualizar</button>
      
    </div>

    <GeneralError v-if="error" :message="error" @close="error = ''" />
    <strong style="text-transform: capitalize">{{ longDate }}</strong><div class="report-download"><span class="download-file-mark"><FileDown :size="26" /></span><div><strong>Roteiro de entregas e coletas</strong><small>PDF · {{ longDate }} · {{ plan?.stops.length || 0 }} parada(s)</small></div><button class="btn primary download-btn" :disabled="loading || downloading || !plan?.stops.length" @click="downloadPdf"><FileDown :size="18" />{{ downloading ? 'Gerando PDF...' : 'Baixar roteiro em PDF' }}</button></div>

    <template v-if="plan">
      <div class="dayplan-chips">
        <span>{{ plan.summary.total }} operação(ões)</span><span>{{ plan.summary.deliveries }} entrega(s)</span><span>{{ plan.summary.pickups }} retirada(s)</span>
        <span>Manhã: {{ plan.summary.morning }}</span><span>Tarde: {{ plan.summary.afternoon }}</span>
      </div>

      <div v-if="plan.vehicles.length" class="dayplan-weights">
        <article v-for="vehicle in plan.vehicles" :key="vehicle.vehicle || 'none'" class="weight-card">
          <header><strong><Truck :size="14" /> {{ vehicleLabel(vehicle) }}</strong><span>Capacidade: {{ vehicle.capacity_kg ? kg(vehicle.capacity_kg) : 'não cadastrada' }}</span></header>
          <template v-for="(label, key) in { MORNING: 'Manhã', AFTERNOON: 'Tarde' }" :key="key">
            <div v-if="vehicle.periods[key]">
              <div class="period-line"><b>{{ label }}</b> · sai com {{ kg(vehicle.periods[key].initial_load_kg) }} · retira {{ kg(vehicle.periods[key].pickup_kg) }}</div>
              <div class="weight-bar" :title="`Maior carga a bordo: ${kg(vehicle.periods[key].peak_load_kg)}`"><i :class="barClass(vehicle.periods[key])" :style="{ width: barPercent(vehicle.periods[key]) + '%' }" /></div>
              <div class="period-line">Maior carga a bordo {{ kg(vehicle.periods[key].peak_load_kg) }} ·
                <b v-if="vehicle.capacity_kg" :style="{ color: vehicle.periods[key].overloaded ? '#c53030' : '' }">{{ vehicle.periods[key].overloaded ? 'excede a capacidade em ' + kg(-vehicle.periods[key].remaining_kg) : 'peso ainda disponível: ' + kg(vehicle.periods[key].remaining_kg) }}</b>
                <b v-else>cadastre a capacidade do veículo</b>
                <template v-if="vehicle.periods[key].items_without_weight"> · {{ vehicle.periods[key].items_without_weight }} item(ns) sem peso cadastrado</template></div>
            </div>
          </template>
        </article>
      </div>

      <div class="dayplan-layout">
        <div>
          <div v-for="period in visiblePeriods" :key="period.key" class="dayplan-period">
            <h3>{{ period.label }} <small>{{ period.stops.length }} operação(ões) · por horário</small></h3>
            <p v-if="!period.stops.length" class="dayplan-empty">Nada agendado para {{ period.label.toLowerCase() }}.</p>
            <button v-for="stop in period.stops" :key="stop.id" type="button" class="dayplan-stop" @click="focusId = stop.id">
              <time>{{ stop.time }}</time>
              <div>
                <span class="stop-tag" :class="stop.leg === 'DELIVERY' ? 'delivery' : 'return'">{{ stop.action_label }}</span>
                <strong>{{ stop.customer_name }} · {{ stop.quote_number }}</strong>
                <small><MapPin :size="11" /> {{ stop.address }}<template v-if="stop.complement"> · {{ stop.complement }}</template></small>
                <small>{{ stop.items.map(i => i.code + ' ' + i.name).join(' · ') || 'Sem itens' }}</small>
                <small>{{ stop.vehicle_plate ? formatPlate(stop.vehicle_plate) : 'Sem veículo' }} · {{ stop.driver_name || 'Sem motorista' }} · {{ kg(stop.weight_kg) }}<template v-if="stop.items_without_weight"> (+ item sem peso)</template></small>
              </div>
              <div class="dayplan-stop-status">
                <b v-if="stopNumber(stop.id)" class="stop-tag">Parada {{ stopNumber(stop.id) }}</b>
                <StatusBadge :value="stop.status" :label="stop.status_label" />
              </div>
            </button>
          </div>
          <p v-if="!plan.stops.length" class="dayplan-empty">Nenhuma entrega ou retirada agendada para este dia.</p>
        </div>

        <div>
          <RouteMap ref="mapRef" :origin="plan.origin" :routes="routes" :focus="focusId" height="460px" />
          <div class="route-legend"><button type="button" class="btn secondary" style="padding:3px 10px;font-size:11px" @click="mapRef?.fit()">Ver todos os pontos</button><span><i style="background:#1f2937;border-radius:3px" />Saída e retorno: {{ plan.origin.label }}</span><span v-for="r in routes" :key="r.key"><i :style="{ background: r.color }" />{{ r.label }}</span></div>
          <p v-if="loading && missingCoordinates.length" class="dayplan-empty" style="margin-top:10px">Localizando {{ missingCoordinates.length }} endereço(s) no mapa…</p>
          <p v-else-if="missingCoordinates.length" class="dayplan-warning" style="margin-top:10px">{{ missingCoordinates.length }} parada(s) sem localização no mapa ({{ missingCoordinates.map(s => s.customer_name).join(', ') }}). Confira o endereço ou o CEP da locação.</p>
        </div>
      </div>
    </template>
    <p v-else-if="loading" class="dayplan-empty">Montando o roteiro…</p>
  </section>
</template>
