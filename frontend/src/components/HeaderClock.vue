<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const now = ref(new Date())
const format = options => new Intl.DateTimeFormat('pt-BR', { timeZone: 'America/Sao_Paulo', ...options })
const timeFormat = format({ hour: '2-digit', minute: '2-digit', second: '2-digit' })
const dateFormat = format({ day: '2-digit', month: 'long', year: 'numeric' })
const weekdayFormat = format({ weekday: 'long' })
const shortDateFormat = format({ day: '2-digit', month: '2-digit', year: 'numeric' })
const timeParts = computed(() => Object.fromEntries(timeFormat.formatToParts(now.value).map(part => [part.type, part.value])))
const date = computed(() => dateFormat.format(now.value))
const weekday = computed(() => weekdayFormat.format(now.value))
const shortDate = computed(() => shortDateFormat.format(now.value))
let timer
onMounted(() => { timer = window.setInterval(() => { now.value = new Date() }, 1000) })
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <div class="header-clock" aria-label="Horário de Brasília">
    <time :datetime="now.toISOString()"><strong>{{ timeParts.hour }}:{{ timeParts.minute }}<span class="clock-seconds">:{{ timeParts.second }}</span></strong><span><b>{{ weekday }}</b><span class="clock-date">{{ date }}</span><span class="clock-date-short">{{ shortDate }}</span></span></time>
  </div>
</template>

<style scoped>
.header-clock { display: flex; align-items: center; gap: 12px; min-width: 0; color: var(--burnt); }
time { display: flex; align-items: center; gap: 16px; }
time > strong { font-size: clamp(20px, 2vw, 27px); letter-spacing: .035em; font-variant-numeric: tabular-nums; color: var(--ink); }
.clock-seconds { opacity: .42; }
time > span { display: grid; gap: 2px; padding-left: 16px; border-left: 2px solid var(--amber); color: var(--muted); font-size: 12px; }
time b { color: var(--ink); font-size: 12px; text-transform: capitalize; }
.clock-date-short { display: none; }
@media (max-width: 600px) { .header-clock { gap: 6px; }.header-clock > svg { display: none; }time { align-items: flex-start; flex-direction: column; gap: 0; }time > span { display: flex; gap: 6px; padding: 0; border: 0; font-size: 10px; }time b { font-size: 10px; }.clock-date { display: none; }.clock-date-short { display: inline; } }
@media (max-width: 380px) { time > strong { font-size: 19px; }time > span, time b { font-size: 9px; } }
</style>
