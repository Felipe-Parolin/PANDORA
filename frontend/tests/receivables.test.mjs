import test from 'node:test'
import assert from 'node:assert/strict'
import { mountView, flush } from './helpers/mountView.mjs'

const customer={id:1,name:'Cliente de teste',billed:'200.00',open_total:'200.00',paid_total:'0.00'}
const titles=[1,2].map(id=>({id,number:`CR-${id}`,amount:'100.00',status:'OPEN',description:'Locação',due_date:'2026-11-02',issue_date:'2026-10-01',monthly_interest_rate:'1.00',grace_days:5}))
const preview={customer:1,payment_date:'2026-11-02',items:titles,principal:'200.00',interest:'0.00',total:'200.00',calculation_token:'a'.repeat(64)}
const payment={id:9,number:'REC-9',principal:'200.00',interest:'0.00',total:'200.00',snapshot:{customer:{name:customer.name},items:titles}}
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return{promise,resolve,reject}}
function mount(t, overrides={}){
  const api={get:async url=>({data:url.includes('/customers/')?{results:[customer],count:1}:{results:titles,count:2}}),post:async()=>({data:preview}),...overrides}
  return mountView(t,'ReceivablesPanel',{api},'components').state
}

test('contas: resposta atrasada de outro cliente não substitui a lista atual',async t=>{
  const first=deferred(),second=deferred()
  const state=mount(t,{get:async(url,config)=>url==='/receivables/'?(config.params.customer===1?first.promise:second.promise):{data:{results:[customer],count:1}}})
  await flush();state.openClient(customer);state.openClient({...customer,id:2,name:'Segundo cliente'})
  second.resolve({data:{results:[{...titles[1],id:20}],count:1}});await flush()
  first.resolve({data:{results:[titles[0]],count:1}});await flush()
  assert.equal(state.client.id,2);assert.equal(state.titles[0].id,20)
})

test('contas: seleção de página preserva seleções de outras páginas',async t=>{
  const state=mount(t);await flush();state.openClient(customer);await flush()
  state.selected=[25];state.selectVisible();assert.deepEqual([...state.selected],[25,1,2])
  state.selectVisible();assert.deepEqual([...state.selected],[25])
})

test('pagamento: duplo clique envia uma baixa e uma nova tentativa mantém a chave após falha de rede',async t=>{
  const calls=[],pending=deferred()
  let fail=true
  const state=mount(t,{post:async(url,data)=>{
    if(url.endsWith('settlement-preview/'))return{data:preview}
    calls.push(data)
    if(fail)return pending.promise
    return{data:payment}
  }})
  await flush();state.openClient(customer);await flush();state.selected=[1,2];state.openPayment();await flush()
  const first=state.settlePayment();await state.settlePayment();assert.equal(calls.length,1)
  pending.reject(new Error('Conexão perdida após processamento'));await first
  const key=calls[0].idempotency_key;assert.ok(key)
  fail=false;await state.settlePayment()
  assert.equal(calls.length,2);assert.equal(calls[1].idempotency_key,key)
  assert.equal(state.payment.number,'REC-9');assert.equal(state.titleStatus,'PAID');assert.deepEqual([...state.selected],[])
})

test('pagamento: fechar durante a baixa é bloqueado e fechar uma prévia pendente descarta a resposta',async t=>{
  const pending=deferred()
  const state=mount(t,{post:()=>pending.promise});await flush();state.openClient(customer);await flush();state.selected=[1];state.openPayment()
  state.paymentBusy=true;state.closePayment();assert.equal(state.paymentOpen,true)
  state.paymentBusy=false;state.closePayment();pending.resolve({data:preview});await flush()
  assert.equal(state.paymentOpen,false);assert.equal(state.preview,null)
})

test('contas: edição envia apenas vencimento e condições, sem reescrever o valor faturado',async t=>{
  const writes=[]
  const state=mount(t,{patch:async(url,data)=>{writes.push({url,data});return{data:{}}}})
  await flush();state.openClient(customer);await flush();state.openEditor(titles[0]);state.editor.due_date='2026-11-20';state.editor.monthly_interest_rate='0.50'
  await state.saveTitle()
  assert.deepEqual(writes[0].data,{description:'Locação',due_date:'2026-11-20',monthly_interest_rate:'0.50',grace_days:5})
  assert.equal(state.editor,null)
})

test('seleção: total usa o cálculo do servidor e inclui contas de outras páginas',async t=>{
  const requests=[]
  const state=mount(t,{post:async(url,data)=>{requests.push({url,data});return{data:{principal:'1000.00',interest:'0.33',total:'1000.33'}}}})
  await flush();state.openClient(customer);await flush();state.selected=[1,25]
  await state.loadSelectedTotal()
  assert.deepEqual([...requests[0].data.receivable_ids],[1,25])
  assert.equal(requests[0].data.customer,1)
  assert.deepEqual({...state.selectionTotals},{principal:'1000.00',interest:'0.33',total:'1000.33'})
  state.selected=[]
  assert.equal(state.selectionTotals,null);assert.equal(state.selectionBusy,false)
})

test('seleção: resposta antiga não altera o total de uma nova seleção nem de uma janela fechada',async t=>{
  const first=deferred(),second=deferred()
  const state=mount(t,{post:async(url,data)=>data.receivable_ids.includes(1)?first.promise:second.promise})
  await flush();state.openClient(customer);await flush()
  state.selected=[1];const request1=state.loadSelectedTotal()
  state.selected=[2];const request2=state.loadSelectedTotal()
  second.resolve({data:{principal:'200.00',interest:'0.00',total:'200.00'}});await request2
  first.resolve({data:{principal:'100.00',interest:'0.00',total:'100.00'}});await request1
  assert.equal(state.selectionTotals.total,'200.00')
  state.closeClient();assert.equal(state.selectionTotals,null)
})

test('seleção: falha do cálculo não apresenta um total válido e permite tentar novamente',async t=>{
  let fail=true
  const state=mount(t,{post:async()=>{if(fail)throw new Error('Falha');return{data:{principal:'100.00',interest:'1.00',total:'101.00'}}}})
  await flush();state.openClient(customer);await flush();state.selected=[1]
  await state.loadSelectedTotal()
  assert.equal(state.selectionTotals,null);assert.ok(state.selectionError);assert.equal(state.selectionBusy,false)
  fail=false;await state.loadSelectedTotal()
  assert.equal(state.selectionTotals.total,'101.00');assert.equal(state.selectionError,'')
})

test('seleção: alterar as condições de uma conta selecionada atualiza o somatório',async t=>{
  let interest='1.00'
  const state=mount(t,{post:async()=>({data:{principal:'100.00',interest,total:interest==='1.00'?'101.00':'102.00'}}),patch:async()=>{interest='2.00';return{data:{}}}})
  await flush();state.openClient(customer);await flush();state.selected=[1];await state.loadSelectedTotal()
  assert.equal(state.selectionTotals.total,'101.00')
  state.openEditor(titles[0]);await state.saveTitle()
  assert.equal(state.selectionTotals.total,'102.00')
})
