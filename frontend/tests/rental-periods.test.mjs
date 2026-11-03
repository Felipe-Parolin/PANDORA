import assert from 'node:assert/strict'
import test from 'node:test'
import { periodDays, periodEnvelope, periodGroups } from '../src/services/rentalPeriods.js'
import { operationCandidates, operationProblem, rentalActionGroups } from '../src/services/rentalActions.js'
import { mountView, flush } from './helpers/mountView.mjs'

test('períodos usam diárias inclusivas e o intervalo geral cobre todos os itens', () => {
  assert.equal(periodDays('2026-11-02','2026-11-02'),1)
  assert.equal(periodDays('2026-11-02','2026-11-04'),3)
  assert.equal(periodDays('2026-11-04','2026-11-02'),0)
  const items=[{equipment_id:1,start_date:'2026-11-02',end_date:'2026-11-04'}, {equipment_id:2,start_date:'2026-11-05',end_date:'2026-11-06'}]
  assert.deepEqual(periodEnvelope(items,{}),{start_date:'2026-11-02',end_date:'2026-11-06'})
  assert.equal(periodGroups([...items,{...items[0],equipment_id:3}])[0].items.length,2)
})

test('edição calcula o preço de cada período e não perde as datas customizadas', async t => {
  const assets=[{id:1},{id:2}]
  const {state,calls}=mountView(t,'RentalsView',{ api:{ get:async(url,config)=>{
    calls.push({url,config})
    return {data:url.includes('availability/')?{available:assets.map(equipment=>({equipment})),blocked:[],next_page:null}: {results:[]}}
  } } })
  await flush()
  state.open({id:10,customer:1,start_date:'2026-11-02',end_date:'2026-11-06',status:'DRAFT',subtotal:'500',transport_fee:'0',estimated_transport_fee:'0',conditions:'Teste',items:[
    {equipment:1,daily_rate:'100',start_date:'2026-11-02',end_date:'2026-11-03'},
    {equipment:2,daily_rate:'150',start_date:'2026-11-05',end_date:'2026-11-06'},
  ]})
  await flush()
  assert.equal(state.subtotal,500)
  const checked=calls.filter(call=>call.url.includes('availability/') && call.config.params.equipment_ids)
  assert.ok(checked.some(call=>call.config.params.start==='2026-11-02' && call.config.params.end==='2026-11-03'))
  assert.ok(checked.some(call=>call.config.params.start==='2026-11-05' && call.config.params.end==='2026-11-06'))
  state.form.start_date='2026-11-01'; await flush()
  assert.equal(state.form.items[0].start_date,'2026-11-02')
  assert.equal(state.form.items[1].start_date,'2026-11-05')
  state.form.items[0].uses_default_period=true; state.useDefaultPeriod(state.form.items[0])
  assert.equal(state.form.items[0].start_date,'2026-11-01')
})

test('retirada parcial não exige inspeções nem transporte de outros equipamentos', () => {
  const quote={status:'ACTIVE',items:[{equipment:1,stage:'PENDING'},{equipment:2,stage:'DELIVERED'},{equipment:3,stage:'RETURNED'}],
    delivery_transport_required:true,return_transport_required:true,conditions:'Teste',inspections:[
      {equipment:1,inspection_type:'PRE_RENTAL',result:'APPROVED'}, {equipment:3,inspection_type:'RETURN',result:'APPROVED'},
    ],transport_tasks:[{leg:'DELIVERY',status:'COMPLETED',items:[{equipment:1}]}]}
  assert.deepEqual(operationCandidates(quote,'deliver').map(item=>item.equipment),[1])
  assert.equal(operationProblem(quote,'deliver',quote.items[0]),'')
  assert.match(operationProblem(quote,'return',quote.items[1]),/coleta/)
  const actions=rentalActionGroups(quote,()=>true).flatMap(group=>group.actions)
  assert.equal(actions.find(action=>action.id==='deliver').reason,'')
  assert.equal(actions.find(action=>action.id==='finalize').reason,'')
  assert.equal(actions.find(action=>action.id==='postInspection').reason,'')
})

test('a operação envia somente os equipamentos selecionados e horários ficam nas datas dos itens', async t => {
  const writes=[]
  const {state}=mountView(t,'RentalsView',{api:{get:async()=>({data:{}}),post:async(url,payload)=>{writes.push({url,payload});return {data:{}}}}})
  await flush()
  const quote={id:10,status:'ACTIVE',end_date:'2026-11-06',items:[{equipment:1,stage:'DELIVERED'},{equipment:2,stage:'DELIVERED'}],return_transport_required:false}
  state.openOperation('return',quote)
  assert.deepEqual(state.operationForm.equipment_ids,[1,2])
  state.operationForm.equipment_ids=[2]; await state.submitOperation()
  assert.deepEqual(writes[0].payload.equipment_ids,[2])
  state.form.items=[{equipment_id:1,start_date:'2026-11-02',end_date:'2026-11-03'},{equipment_id:2,start_date:'2026-11-05',end_date:'2026-11-06'}]
  state.deliveryClock='08:30';state.returnClock='17:00'
  assert.equal(state.form.requested_delivery_at,'2026-11-02T08:30')
  assert.equal(state.form.requested_return_at,'2026-11-06T17:00')
})

test('dividir viagem envia sua composição e preserva códigos de outras paradas no carregamento', async t => {
  const writes=[]
  const {state}=mountView(t,'LogisticsView',{api:{patch:async(url,payload)=>{writes.push({url,payload});return {data:{}}}}})
  await flush()
  state.openTrip({id:10,address:'Rua de teste, 10',load_manifest:['EQ-1','EQ-OUTRA-PARADA','EQ-2'],items:[
    {id:101,internal_code:'EQ-1'}, {id:102,internal_code:'EQ-2'},
  ]})
  state.tripForm.rental_item_ids=[102]
  assert.equal(state.tripForm.load_manifest_text,'EQ-OUTRA-PARADA\nEQ-2')
  await state.saveTrip()
  assert.equal(writes[0].url,'/transport-tasks/10/')
  assert.deepEqual(writes[0].payload.rental_item_ids,[102])
  assert.deepEqual(writes[0].payload.load_manifest,['EQ-OUTRA-PARADA','EQ-2'])
})
