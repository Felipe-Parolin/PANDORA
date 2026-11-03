<script setup>
// Mapa (OpenStreetMap + Leaflet): rota completa de cada saída — depósito → todas as paradas, na ordem do horário → volta ao depósito.
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'

const props = defineProps({
  origin: { type: Object, default: null },
  // [{ key, label, color, loop, stops: [{ id, n, latitude, longitude, title, subtitle }] }]  (loop: volta ao depósito; padrão true)
  routes: { type: Array, default: () => [] },
  focus: { type: [Number, String], default: null },
  height: { type: String, default: '420px' },
})

const el = ref(null)
let map = null
let layer = null
let drawToken = 0
let resizeObserver = null
let lastBounds = []
const markersById = new Map()

const text = (tag, value, style = '') => { const node = document.createElement(tag); node.textContent = value; if (style) node.style.cssText = style; return node }

function badge(content, color, square = false) {
  const wide = String(content).length > 2
  return L.divIcon({
    className: 'route-marker-wrap',
    html: `<span class="route-marker${square ? ' square' : ''}${wide ? ' wide' : ''}" style="background:${color}">${content}</span>`,
    iconSize: wide ? [44, 28] : [30, 30], iconAnchor: wide ? [22, 14] : [15, 15], popupAnchor: [0, -14],
  })
}

function popup(title, subtitle, extra) {
  const box = document.createElement('div')
  box.append(text('strong', title, 'display:block'))
  if (subtitle) box.append(text('span', subtitle, 'display:block;font-size:12px'))
  if (extra) box.append(text('small', extra, 'display:block;color:#666'))
  return box
}

function groupPopup(entries) {
  const box = document.createElement('div')
  box.append(text('span', entries[0].stop.subtitle || '', 'display:block;font-size:12px;margin-bottom:4px'))
  for (const { stop, route } of entries) {
    box.append(text('strong', `${stop.n}. ${stop.title}`, 'display:block;margin-top:4px'))
    box.append(text('small', route.label, 'display:block;color:#666'))
  }
  return box
}

async function roadGeometry(points, token) {
  // Rota viária pelo OSRM público; se falhar, mantém a linha reta tracejada.
  if (points.length < 2) return null
  const path = points.map(([lat, lng]) => `${lng},${lat}`).join(';')
  try {
    const response = await fetch(`https://router.project-osrm.org/route/v1/driving/${path}?overview=full&geometries=geojson`)
    if (!response.ok) return null
    const data = await response.json()
    if (token !== drawToken) return null
    const coords = data?.routes?.[0]?.geometry?.coordinates
    return coords?.length ? coords.map(([lng, lat]) => [lat, lng]) : null
  } catch { return null }
}

// Enquadra o mapa de forma que TODOS os pontos (depósito e paradas) fiquem visíveis de uma vez.
function fit() {
  if (!map) return
  map.invalidateSize()
  if (lastBounds.length > 1) map.fitBounds(lastBounds, { padding: [40, 40], maxZoom: 16, animate: false })
  else if (lastBounds.length === 1) map.setView(lastBounds[0], 14, { animate: false })
}
defineExpose({ fit })

async function draw() {
  if (!map) return
  const token = ++drawToken
  layer.clearLayers()
  markersById.clear()
  const bounds = []
  const origin = props.origin && Number.isFinite(props.origin.latitude) ? [props.origin.latitude, props.origin.longitude] : null
  if (origin) {
    L.marker(origin, { icon: badge('S', '#1f2937', true), zIndexOffset: 1000 }).addTo(layer)
      .bindPopup(popup('Depósito', props.origin.label, props.origin.provisional ? 'Saída e retorno de cada rota. Origem provisória — configure FREIGHT_ORIGIN_CEP.' : 'Saída e retorno de cada rota.'))
    bounds.push(origin)
  }

  // Paradas no mesmo endereço (ex.: entrega e retirada do mesmo cliente) viram um único marcador com todos os números.
  const groups = new Map()
  const geo = new Map()
  for (const route of props.routes) {
    const points = route.stops.filter(s => Number.isFinite(s.latitude) && Number.isFinite(s.longitude))
    geo.set(route, points)
    for (const stop of points) {
      const key = `${stop.latitude.toFixed(5)},${stop.longitude.toFixed(5)}`
      if (!groups.has(key)) groups.set(key, { position: [stop.latitude, stop.longitude], entries: [] })
      groups.get(key).entries.push({ stop, route })
    }
  }
  for (const { position, entries } of groups.values()) {
    bounds.push(position)
    const label = entries.map(e => e.stop.n).join('·')
    const marker = L.marker(position, { icon: badge(label, entries[0].route.color), zIndexOffset: entries.length * 10 }).addTo(layer)
    marker.bindPopup(entries.length === 1
      ? popup(`${entries[0].stop.n}. ${entries[0].stop.title}`, entries[0].stop.subtitle, entries[0].route.label)
      : groupPopup(entries))
    for (const { stop } of entries) markersById.set(String(stop.id), marker)
  }

  // Rota completa: depósito → todas as paradas (em ordem) → depósito.
  const jobs = []
  for (const route of props.routes) {
    const points = geo.get(route) || []
    if (!points.length) continue
    const line = []
    if (origin) line.push(origin)
    for (const stop of points) line.push([stop.latitude, stop.longitude])
    if (origin && route.loop !== false) line.push(origin)
    if (line.length < 2) continue
    const dashed = L.polyline(line, { color: route.color, weight: 4, opacity: .55, dashArray: '6 8' }).addTo(layer)
    jobs.push(roadGeometry(line, token).then(geometry => {
      if (geometry && token === drawToken) { layer.removeLayer(dashed); L.polyline(geometry, { color: route.color, weight: 5, opacity: .85 }).addTo(layer) }
    }))
  }
  lastBounds = bounds
  fit()
  await Promise.allSettled(jobs)
}

onMounted(async () => {
  map = L.map(el.value, { scrollWheelZoom: false }).setView([-22.1853, -47.3903], 13)
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; contribuidores do OpenStreetMap' }).addTo(map)
  layer = L.layerGroup().addTo(map)
  await nextTick()
  map.invalidateSize()
  draw()
  // Se o contêiner mudar de tamanho depois (layout, abas), reenquadra para não deixar pontos fora da área visível.
  if (typeof ResizeObserver !== 'undefined') { resizeObserver = new ResizeObserver(() => fit()); resizeObserver.observe(el.value) }
})
onBeforeUnmount(() => { drawToken++; resizeObserver?.disconnect(); map?.remove(); map = null })
watch(() => [props.origin, props.routes], () => { nextTick(() => { map?.invalidateSize(); draw() }) }, { deep: true })
watch(() => props.focus, id => {
  const marker = markersById.get(String(id))
  if (marker && map) { map.setView(marker.getLatLng(), Math.max(map.getZoom(), 15)); marker.openPopup() }
})
</script>

<template>
  <div class="route-map" :style="{ height }" ref="el" role="region" aria-label="Mapa do roteiro do dia" />
</template>
