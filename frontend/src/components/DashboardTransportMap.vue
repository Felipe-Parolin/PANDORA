<script setup>
import { computed, onMounted, ref } from 'vue'
import { MapPin, RefreshCw } from 'lucide-vue-next'
import { api } from '../services/api'
import RouteMap from './RouteMap.vue'
const plan = ref(null), loading = ref(false), error = ref('')
const date = ref(new Date().toLocaleDateString('en-CA'))
const routes = computed(() => {
  const stops = plan.value?.stops || []
  return (plan.value?.vehicles || []).map((vehicle, index) => ({
    key: vehicle.vehicle || `vehicle-${index}`, label: vehicle.label, color: ['#1d4ed8', '#047857', '#c2410c', '#6d28d9'][index % 4], loop: true,
    stops: (vehicle.stops || []).map((id, number) => {
      const stop = stops.find(item => item.id === id)
      return stop && { ...stop, n: number + 1, title: `${stop.time || ''} · ${stop.customer_name}`, subtitle: stop.address }
    }).filter(Boolean),
  }))
})
async function load() {
  loading.value = true; error.value = ''
  try { plan.value = (await api.get('/transport-tasks/day-plan/', { params: { date: date.value }, timeout: 20000 })).data }
  catch { error.value = 'Não foi possível carregar as paradas. Você pode consultar o roteiro na Logística.' }
  finally { loading.value = false }
}
onMounted(load)
</script>
<template>
  <section class="panel dashboard-transport-map"><header><div><span class="eyebrow">TRANSPORTE</span><h2><MapPin :size="19" />Entregas e coletas no mapa</h2></div><div class="dashboard-map-controls"><AppDateTime v-model="date" type="date" aria-label="Data do mapa" @change="load" /><button type="button" class="icon-btn" aria-label="Atualizar mapa" :disabled="loading" @click="load"><RefreshCw :size="18" :class="{ spinning: loading }" /></button></div></header><GeneralError v-if="error" :message="error" @close="error = ''" /><p v-if="loading" class="map-status" role="status">Carregando roteiro...</p><RouteMap v-if="plan" :origin="plan.origin" :routes="routes" height="320px" /><footer><span>{{ plan?.stops?.length || 0 }} parada(s) na data selecionada</span><router-link :to="{ name: 'logistics', query: { tab: 'dayplan' } }" class="text-link">Abrir roteiro completo</router-link></footer></section>
</template>
