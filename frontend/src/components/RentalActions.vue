<script setup>
import { computed } from 'vue'
import { Route, ClipboardCheck, Truck, Pencil, PackageCheck, CalendarRange, RotateCcw, CheckCircle2, MessageCircle, XCircle, Trash2 } from 'lucide-vue-next'
import { can } from '../services/api'
import { rentalActionGroups } from '../services/rentalActions'

const props = defineProps({ quote: { type: Object, required: true }, busy: Boolean })
const emit = defineEmits(['action'])
const icons = { Route, ClipboardCheck, Truck, Pencil, PackageCheck, CalendarRange, RotateCcw, CheckCircle2, MessageCircle, XCircle, Trash2 }
const groups = computed(() => rentalActionGroups(props.quote, can, props.busy))
function run(action) { if (!action.reason) emit('action', action.id) }
</script>

<template>
  <div class="rental-action-groups">
    <section v-for="group in groups" :key="group.label"><h3>{{ group.label }}</h3><div><button v-for="action in group.actions" :key="action.id" type="button" class="rental-action" :class="action.tone" :disabled="Boolean(action.reason)" :title="action.reason || action.label" @click="run(action)"><component :is="icons[action.icon]" :size="16" /><span>{{ action.label }}</span></button></div></section>
  </div>
</template>

<style scoped>
.rental-action-groups { display: grid; grid-template-columns: 1.2fr 1.2fr 1fr 1fr; gap: 16px; width: 100%; text-align: left; }
section { min-width: 0; }h3 { margin: 0 0 9px; color: var(--muted); font-size: 10px; letter-spacing: .05em; text-transform: uppercase; }section > div { display: grid; gap: 5px; }
.rental-action { display: flex; align-items: center; gap: 7px; width: 100%; min-height: 34px; padding: 7px 9px; border: 1px solid var(--line); border-radius: 7px; background: white; color: var(--ink); text-align: left; font-size: 11px; cursor: pointer; }.rental-action svg { flex-shrink: 0; }.rental-action span { overflow-wrap: anywhere; }.rental-action:not(:disabled):hover { border-color: var(--amber); background: #fff9eb; }.rental-action.success:not(:disabled) { color: var(--green); }.rental-action.danger:not(:disabled) { color: var(--red); }.rental-action:disabled { color: #76787d; background: #f2f3f4; border-color: #e5e6e8; opacity: .65; cursor: not-allowed; }
@media (max-width: 1100px) { .rental-action-groups { grid-template-columns: 1fr 1fr; } }
@media (max-width: 460px) { .rental-action-groups { gap: 14px 9px; }.rental-action { font-size: 10px; padding: 8px 6px; min-height: 42px; }h3 { font-size: 9px; }.rental-action svg { width: 14px; } }
</style>
