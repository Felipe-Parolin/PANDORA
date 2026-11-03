import { createApp } from 'vue'
import App from './App.vue'
import AppSelect from './components/AppSelect.vue'
import AppInput from './components/AppInput.vue'
import AppDateTime from './components/AppDateTime.vue'
import GeneralError from './components/GeneralError.vue'
import SuccessNotice from './components/SuccessNotice.vue'
import PaginationBar from './components/PaginationBar.vue'
import ListOrdering from './components/ListOrdering.vue'
import ListToolbar from './components/ListToolbar.vue'
import router from './router'
import './styles.css'

createApp(App).component('SuccessNotice', SuccessNotice).component('AppInput', AppInput).component('AppSelect', AppSelect).component('AppDateTime', AppDateTime).component('GeneralError', GeneralError).component('PaginationBar', PaginationBar).component('ListOrdering', ListOrdering).component('ListToolbar', ListToolbar).use(router).mount('#app')

// Tabelas viram cartões no celular: cada <td> recebe o título da sua coluna.
function labelTables(root = document) {
  root.querySelectorAll('.table-wrap:not(.desktop-list) table').forEach((table) => {
    const heads = [...table.querySelectorAll(':scope > thead > tr > th')].map((th) => th.textContent.trim())
    if (!heads.length) return
    table.classList.add('stack-table')
    table.querySelectorAll(':scope > tbody > tr').forEach((tr) => {
      [...tr.children].forEach((td, i) => { if (td.tagName === 'TD' && td.colSpan === 1 && heads[i] && td.dataset.label !== heads[i]) td.dataset.label = heads[i] })
    })
  })
}
let labelTimer
new MutationObserver(() => { clearTimeout(labelTimer); labelTimer = setTimeout(() => labelTables(), 50) }).observe(document.body, { childList: true, subtree: true })
