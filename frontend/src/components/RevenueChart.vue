<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { formatDate } from '../services/formatters'
import { money } from '../services/api'

const props = defineProps({ points: { type: Array, default: () => [] }, groupBy: { type: String, default: 'month' } })
const chart = ref(null), visible = ref(false)
let observer
onMounted(() => {
  if (typeof IntersectionObserver === 'undefined') { visible.value = true; return }
  observer = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting && entry.intersectionRatio >= .15)) {
      visible.value = true
      observer.disconnect()
    }
  }, { threshold: .15 })
  observer.observe(chart.value)
})
onBeforeUnmount(() => observer?.disconnect())
const peak = computed(() => Math.max(0, ...props.points.map(point => Number(point.total) || 0)))
const ceiling = computed(() => {
  if (!peak.value) return 1
  const base = 10 ** Math.floor(Math.log10(peak.value))
  return [1, 2, 5, 10].find(step => step * base >= peak.value) * base
})
const ticks = computed(() => [0, 1, 2, 3, 4].map(index => ({ value: ceiling.value * index / 4, percent: index * 25 })))
const total = computed(() => props.points.reduce((sum, point) => sum + Number(point.total || 0), 0))
const compactMoney = value => new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', notation: 'compact', maximumFractionDigits: 1 }).format(value)
function periodLabel(value) {
  if (props.groupBy === 'year') return formatDate(value, { year: 'numeric' })
  if (props.groupBy === 'month') return formatDate(value, { month: 'short', year: '2-digit' }).replace('. de ', '/').replace(' de ', '/')
  return formatDate(value, { day: '2-digit', month: '2-digit' })
}
</script>

<template>
  <div ref="chart" class="revenue-visual" :class="{ 'is-visible': visible }" aria-label="Receita contratual por período">
    <div class="revenue-visual-summary"><span><i aria-hidden="true"/>Receita contratual</span><strong>{{ money(total) }}</strong></div>
    <div class="revenue-visual-frame">
      <div class="revenue-visual-axis" aria-hidden="true"><span v-for="tick in ticks" :key="tick.percent" :style="{ bottom: `${tick.percent}%` }">{{ compactMoney(tick.value) }}</span></div>
      <div class="revenue-visual-scroll" tabindex="0" aria-label="Períodos do gráfico; role horizontalmente para ver mais">
        <div class="revenue-visual-plot" :style="{ '--period-count': Math.max(points.length, 1) }">
          <div class="revenue-visual-grid" aria-hidden="true"><i v-for="tick in ticks" :key="tick.percent" :style="{ bottom: `${tick.percent}%` }"/></div>
          <div v-for="(point, index) in points" :key="point.period" class="revenue-visual-column">
            <div class="revenue-visual-space" role="img" :aria-label="`${formatDate(point.period)}: ${money(point.total)}`" :title="`${formatDate(point.period)} · ${money(point.total)}`" tabindex="0">
              <div class="revenue-visual-bar" :style="{ height: `${Math.max(0, Number(point.total)) / ceiling * 100}%` }"><span>{{ compactMoney(Number(point.total)) }}</span><i :style="{ '--grow-delay': `${Math.min(index, 8) * 80}ms` }"/></div>
            </div>
            <span class="revenue-visual-period">{{ periodLabel(point.period) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.revenue-visual{--revenue-plot-height:120px;padding:12px 20px 10px;min-width:0}.revenue-visual-summary{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px}.revenue-visual-summary>span{display:flex;align-items:center;gap:8px;font-size:12px;color:var(--muted)}.revenue-visual-summary>span i{width:8px;height:8px;background:var(--amber);border-radius:2px}.revenue-visual-summary strong{font-size:17px;font-variant-numeric:tabular-nums}.revenue-visual-frame{display:flex;gap:12px;min-width:0}.revenue-visual-axis{position:relative;flex:0 0 62px;height:var(--revenue-plot-height);margin-top:24px}.revenue-visual-axis span{position:absolute;right:0;transform:translateY(50%);white-space:nowrap;font-size:10px;color:var(--muted);font-variant-numeric:tabular-nums}.revenue-visual-scroll{flex:1;min-width:0;overflow-x:auto;padding-bottom:6px}.revenue-visual-scroll:focus-visible{outline:2px solid var(--amber);outline-offset:2px;border-radius:4px}.revenue-visual-plot{display:grid;grid-template-columns:repeat(var(--period-count),minmax(64px,1fr));position:relative;min-width:max(100%,calc(var(--period-count) * 64px));padding-top:24px}.revenue-visual-grid{position:absolute;inset:24px 0 auto;height:var(--revenue-plot-height);pointer-events:none}.revenue-visual-grid i{position:absolute;left:0;right:0;height:1px;background:#eceae5}.revenue-visual-column{min-width:0;position:relative}.revenue-visual-space{height:var(--revenue-plot-height);width:36px;position:relative;margin:0 auto;outline:none}.revenue-visual-bar{position:absolute;left:0;right:0;bottom:0}.revenue-visual-bar>i{position:absolute;inset:0;background:var(--amber);border-radius:4px 4px 0 0;transform-origin:bottom;animation:revenue-grow .7s ease both;animation-play-state:paused;animation-delay:var(--grow-delay)}.revenue-visual-bar>span{position:absolute;bottom:100%;left:50%;transform:translateX(-50%);padding-bottom:7px;font-size:10px;font-weight:600;color:#62646a;white-space:nowrap;font-variant-numeric:tabular-nums}.revenue-visual-space:hover .revenue-visual-bar>i,.revenue-visual-space:focus-visible .revenue-visual-bar>i{background:#c98c10}.revenue-visual-space:focus-visible{outline:2px solid var(--ink);outline-offset:5px;border-radius:4px}.revenue-visual-period{display:block;line-height:1.4;text-align:center;padding:11px 5px 0;color:var(--muted);font-size:10px;white-space:nowrap}
.revenue-visual.is-visible .revenue-visual-bar>i{animation-play-state:running}
@keyframes revenue-grow{from{transform:scaleY(0)}to{transform:scaleY(1)}}
@media(prefers-reduced-motion:reduce){.revenue-visual-bar>i{animation:none}}
@media(max-width:640px){.revenue-visual{padding:12px 14px 10px}.revenue-visual-axis{flex-basis:55px}.revenue-visual-frame{gap:8px}.revenue-visual-summary strong{font-size:15px}}
</style>
