import { computed, ref, watch } from 'vue'

export const TABLE_PAGE_SIZE = 10
export function usePagination(source, resetSources = []) {
  const page = ref(1)
  const total = computed(() => source.value?.length || 0)
  const pages = computed(() => Math.max(1, Math.ceil(total.value / TABLE_PAGE_SIZE)))
  const items = computed(() => (source.value || []).slice((page.value - 1) * TABLE_PAGE_SIZE, page.value * TABLE_PAGE_SIZE))
  watch(pages, count => { page.value = Math.min(page.value, count) }, { flush: 'sync' })
  if (resetSources.length) watch(resetSources, () => { page.value = 1 })
  return { page, total, pages, items }
}
