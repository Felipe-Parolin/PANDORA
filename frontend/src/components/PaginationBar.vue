<script setup>
import { computed } from 'vue'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
const props = defineProps({ modelValue: { type: Number, default: 1 }, total: { type: Number, default: 0 }, pageSize: { type: Number, default: 10 }, loading: Boolean })
const emit = defineEmits(['update:modelValue'])
const pages = computed(() => Math.max(1, Math.ceil(props.total / props.pageSize)))
const first = computed(() => props.total ? (props.modelValue - 1) * props.pageSize + 1 : 0)
const last = computed(() => Math.min(props.modelValue * props.pageSize, props.total))
</script>
<template>
  <footer class="list-footer pagination-bar"><span>{{ first }}–{{ last }} de {{ total }} registros</span><nav aria-label="Paginação"><button type="button" class="icon-btn" aria-label="Página anterior" title="Página anterior" :disabled="loading || modelValue <= 1" @click="emit('update:modelValue', modelValue - 1)"><ChevronLeft :size="19" /></button><span>{{ modelValue }} / {{ pages }}</span><button type="button" class="icon-btn" aria-label="Próxima página" title="Próxima página" :disabled="loading || modelValue >= pages" @click="emit('update:modelValue', modelValue + 1)"><ChevronRight :size="19" /></button></nav></footer>
</template>
<style scoped>
.pagination-bar { gap: 12px; flex-wrap: wrap; }.pagination-bar nav { display: flex; align-items: center; gap: 10px; }.pagination-bar nav > span { font-size: 12px; font-variant-numeric: tabular-nums; }.pagination-bar button { border: 1px solid var(--line); background: white; }.pagination-bar button:disabled { opacity: .35; cursor: not-allowed; }
</style>
