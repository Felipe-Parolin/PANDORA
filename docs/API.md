# Contrato inicial da API

Base local: `http://127.0.0.1:8000/api/`

Exceto `health` e `auth/login`, os endpoints exigem `Authorization: Bearer <access_token>`.

## Autenticação e painel

| Método | Endpoint | Uso |
|---|---|---|
| `GET` | `health/` | saúde do serviço |
| `POST` | `auth/login/` | login por e-mail e senha |
| `POST` | `auth/refresh/` | renovar token de acesso |
| `GET` | `auth/me/` | usuário autenticado |
| `GET` | `dashboard/` | indicadores e `purchase_suggestion` explicável, baseado em locações recentes (não é IA generativa) |

Exemplo de login:

```json
{
  "email": "admin@pandora.local",
  "password": "Pandora@123"
}
```

## Cadastros

| Recurso | Endpoint | Operações |
|---|---|---|
| Usuários | `users/` | CRUD conforme ACL |
| Grupos ACL | `access-groups/` | grupos personalizados e permissões |
| Catálogo ACL | `access-groups/catalog/` | permissões disponíveis por módulo |
| Clientes | `customers/` | CRUD conforme ACL |
| Categorias | `categories/` | CRUD conforme ACL |
| Equipamentos | `equipment/` | CRUD e `/{id}/history/` |
| QR Code | `equipment/{id}/qr-code/` | imagem PNG do QR |
| Resolver QR | `equipment/resolve-qr/?token=<uuid>` | localiza o equipamento |
| Mídias | `media/` | CRUD multipart, limite de 10 MB |
| Prévia/download de mídia | `GET media/{id}/content/` | fluxo autenticado de imagens/PDFs; `?download=1` força download, formatos Office são anexos |

Filtros úteis: `equipment/?status=AVAILABLE`, `equipment/?category=1`, `customers/?search=nome` e `media/?category=MANUAL`.

O conteúdo exige `media.view`, usa o arquivo vinculado ao registro e retorna 404 quando o armazenamento não o contém. A interface carrega imagens/PDFs como blobs locais para a prévia; não envia arquivos a visualizadores externos. DOC/DOCX continuam disponíveis para download.

As respostas de login e `auth/me/` incluem `access_group`, `access_group_name` e `permissions`. O código `*` representa acesso administrativo total. A API retorna `403` quando a ACL não autoriza a ação e `409` quando uma exclusão é impedida por vínculos protegidos.

## Manutenção

| Método | Endpoint | Uso |
|---|---|---|
| CRUD | `maintenance-plans/` | plano por data, periodicidade e horas de uso |
| CRUD | `service-orders/` | ciclo da ordem de serviço |
| `GET` | `service-orders/checklist-template/?type=PREVENTIVE` | checklist/roteiro da fábrica |

Filtros de OS: `status`, `type`, `equipment`, `technician`, `search` e `queue=unassigned`.

A tela de manutenção apresenta somente “Em aberto” (todos os estados operacionais não encerrados) e “Concluído” (`COMPLETED`), por padrão em aberto. As etapas anteriores da API permanecem compatíveis e são agrupadas na apresentação; OS canceladas não entram nessas duas listas e continuam preservadas no histórico, sem serem rotuladas como concluídas.

O ciclo inclui `OPEN`, `SCHEDULED`, `IN_PROGRESS`, `WAITING_PARTS`, `ABANDONED`, `COMPLETED` e `CANCELLED`. Ao usar `ABANDONED`, `abandoned_reason` é obrigatório; a API registra automaticamente `abandoned_at`. O início da execução registra `started_at`.

Planos expõem `due_date`, `due_usage_hours`, `usage_remaining` e `alert_status`. Os alertas podem ser `OK`, `UPCOMING`, `OVERDUE` ou `CRITICAL`. Uma manutenção crítica vencida por data ou uso bloqueia reserva e entrega.

OS da oficina aceitam `equipment_condition` (`PENDING`, `OPERATING`, `BROKEN`) e expõem `operational_status`. Uma condição `BROKEN` exige `diagnosis`, impede conclusão/cancelamento/liberação e protege a OS contra exclusão. Para concluir uma avaliação explícita, envie condição `OPERATING`, `released: true`, técnico e testes finais; a liberação exige `maintenance.release`. OS vinculadas a inspeções de locação continuam recebendo a decisão pelo endpoint de inspeção, sem alteração direta dessa condição. Os campos financeiros históricos não são removidos, mas não aparecem no formulário simplificado da oficina.

## Locação e orçamento

| Método | Endpoint | Uso |
|---|---|---|
| CRUD | `rental-quotes/` | orçamento e seus itens |
| `GET` | `rental-quotes/availability/?start=2026-09-20&end=2026-09-25` | equipamentos disponíveis e bloqueados, com motivo |
| `POST` | `rental-quotes/unmet-demand/` | registra procura não atendida explicitamente para cliente, equipamento e período indisponível |
| `GET/POST` | `rental-quotes/{id}/documents/` | lista versões ou gera nova versão de orçamento/comprovante (`kind`: `QUOTE`, `DELIVERY`, `RETURN`) |
| `GET` | `rental-quotes/{id}/documents/{document_id}/pdf/` | baixa o PDF não fiscal de uma versão registrada |
| `POST` | `rental-quotes/{id}/reserve/` | aprova e reserva, gerando inspeção e OS pré-locação para cada equipamento |
| `POST` | `rental-quotes/{id}/cancel/` | cancela com motivo e libera os equipamentos |
| `POST` | `rental-quotes/{id}/deliver/` | registra entrega após inspeções aprovadas |
| `POST` | `rental-quotes/{id}/extend/` | prorroga após nova validação de disponibilidade |
| `POST` | `rental-quotes/{id}/return/` | registra devolução e abre uma OS de inspeção final por equipamento na Manutenção |
| `POST` | `rental-quotes/{id}/finalize-return/` | conclui devolução após todas as inspeções finais |
| `GET/PATCH` | `rental-inspections/` | consulta e registra a condição operante/inoperante por equipamento |

Ao editar um orçamento, `ignore_quote=<id>` desconsidera a própria reserva durante a nova verificação de disponibilidade.

Cada equipamento pode definir `turnaround_days` (0 a 30 dias) para limpeza, transporte ou preparo entre locações. A API aplica esse intervalo tanto na consulta quanto na aprovação/prorrogação. `acquisition_cost` no equipamento e `labor_cost`/`parts_cost` na OS alimentam a sugestão de compra do dashboard; são valores informados pela equipe, não cotação automática.

`unmet-demand/` recebe `equipment`, `customer`, `start_date` e `end_date`; exige indisponibilidade real, evita duplicação do mesmo cliente/equipamento/período e requer `rentals.manage`. O dashboard considera apenas registros explícitos dos últimos 180 dias. A sugestão é heurística: mostra evidências, confiança e recomendação de compra ou substituição, sem executar compras.

Documentos exigem `rentals.view` para leitura e `rentals.manage` para gerar. O POST cria nova versão somente quando o snapshot mudou; repetição idêntica retorna a versão existente. Comprovantes exigem entrega/devolução já registrada. O histórico vinculado impede a exclusão do orçamento. São PDFs comerciais/operacionais não fiscais e não assinados.

Exemplo de criação:

```json
{
  "customer": 1,
  "start_date": "2026-09-20",
  "end_date": "2026-09-22",
  "status": "DRAFT",
  "discount": "0.00",
  "delivery_transport_required": true,
  "return_transport_required": false,
  "delivery_address": "Rua Exemplo, 10, Leme/SP",
  "transport_fee": "60.00",
  "conditions": "Retirada e devolução no balcão.",
  "items": [
    {
      "equipment_id": 1,
      "daily_rate": "190.00",
      "quantity_days": 3
    }
  ]
}
```

O fluxo usa os estados `DRAFT`, `SENT`, `APPROVED`, `ACTIVE`, `RETURNED`, `COMPLETED`, `CANCELLED` e `EXPIRED`. Mudanças posteriores à reserva são feitas pelas ações específicas, mantendo responsáveis, datas e trilha de auditoria.

Ao reservar, entregar ou prorrogar, a API verifica sobreposição, situação operacional, OS aberta e manutenção crítica vencida dentro de transação atômica. A OS pré-locação vinculada à própria reserva é exceção na disponibilidade, mas outras OS abertas continuam bloqueando. A equipe de Manutenção envia `PATCH rental-inspections/{id}/` com `equipment_decision: "OPERATING"` ou `"BROKEN"` e `observations`; a resposta inclui `operational_status`. Operante conclui e libera a OS; inoperante mantém a OS aberta e impede a entrega. O rótulo da interface mudou, mas o código `BROKEN` permanece estável. O adaptador preserva a leitura de campos e checklists históricos, que não são mais exigidos nem editáveis. Uma OS pré-locação de reserva ativa não pode ser concluída ou excluída manualmente. Se a reserva for cancelada após um impedimento, a OS permanece aberta para reparo e exige testes finais e liberação técnica. Na devolução, é criada uma OS pós-locação por equipamento na Manutenção, inclusive quando não há avaria; a avaliação final conclui a OS operante ou a mantém aberta para reparo.

As evidências podem ser enviadas por `media/` usando `rental_inspection=<id>`, categoria `INSPECTION` e upload multipart.

## Transporte opcional

O editor permite compartilhar CEP, endereço e complemento entre entrega e coleta (`return_same_as_delivery: true`, com ambos os serviços selecionados). Envie `calculate_transport: true` para obter os custos na API, sem confiar no valor calculado no navegador. A resposta inclui `transport_estimate.delivery`, `transport_estimate.return` e `transport_estimate.total`; os trajetos desmarcados não são cobrados. `transport_fee` recebe a soma antes do desconto percentual. A consulta depende de CEP com coordenadas e das configurações `FREIGHT_*`; se não for possível estimar um trajeto, o orçamento não é salvo com frete zero por engano. A estimativa não é rota viária nem tarifa oficial e a origem padrão continua provisória até configurar o depósito.

Orçamentos históricos sem composição por trajeto preservam seu frete até recálculo explícito. As condições comerciais são opcionais na API e não bloqueiam mais a reserva; os campos históricos não são apagados. Rascunhos não devem criar reservas, inspeções, OS ou viagens.

| Método | Endpoint | Uso |
|---|---|---|
| CRUD | `vehicles/` | veículos, placa, capacidade, disponibilidade e observações |
| `GET/PATCH` | `transport-tasks/` | consulta e planejamento de viagens de entrega/coleta |
| `GET` | `transport-tasks/drivers/` | opções mínimas de motorista (ID, nome e situação em viagem), com `logistics.manage`, sem expor o cadastro de contas |
| `POST` | `transport-tasks/{id}/start/` | saída com veículo e motorista atribuídos, após liberação técnica no caso de entrega |
| `POST` | `transport-tasks/{id}/complete/` | conclui viagem; com `advance_rental: true`, também confirma entrega/devolução em uma transação |

Somente reservas com `delivery_transport_required` geram viagem de entrega. A viagem de coleta é criada ao registrar a entrega quando `return_transport_required` está ativo. O orçamento expõe as viagens em `transport_tasks` e inclui `transport_fee` no `total`. A exclusão de veículos ou orçamentos com viagens vinculadas é impedida para preservar o histórico. As permissões são `logistics.view` e `logistics.manage`.

A resposta de viagem inclui equipamentos, período da locação, custo do trajeto quando disponível e `workflow` (situação, orientação e `can_start`). A fila distingue programação, liberação técnica, viagem em andamento e confirmação pendente, sem liberar saídas inválidas. Um motorista não pode iniciar duas viagens simultâneas. `advance_rental` também exige `rentals.dispatch` para entrega ou `rentals.return` para retorno; falhas desfazem a conclusão da viagem. Sem essa opção, mantém-se a confirmação separada compatível com clientes antigos, exibida como pendência. O retorno abre inspeção e OS final na Manutenção, sem liberar o equipamento automaticamente.

## Preparação fiscal

| Método | Endpoint | Uso |
|---|---|---|
| `GET/PATCH` | `fiscal/company/` | consulta/configura o emitente desta instalação; inicia vazio |
| `GET/PATCH` | `fiscal/customers/{id}/` | endereço fiscal, situação de ICMS e IE complementares do cliente |
| `GET/PATCH` | `fiscal/equipment/{id}/` | NCM e valor do bem, separados da diária |
| `GET` | `fiscal/rentals/` | lista paginada de locações, exceto canceladas/expiradas |
| `GET` | `fiscal/rentals/{id}/readiness/` | pendências cadastrais e dados atuais para preparar integração |
| `GET` | `fiscal/rentals/{id}/export/` | exporta prévia JSON, sem emissão ou cálculo de tributos |

Leitura exige `fiscal.view`; alteração de dados complementares exige `fiscal.manage`; configuração do emitente exige `fiscal.configure`. As alterações são auditadas. Nenhum endpoint habilita produção, recebe certificados ou transmite a um autorizador. `data_ready` indica somente preenchimento básico; `can_issue`, `fiscal_document` e `taxes_calculated` permanecem falsos. Campos desconhecidos ficam vazios ou `UNKNOWN`; não há regime ou classificação tributária presumidos. O cadastro de clientes também aceita o formato alfanumérico do CNPJ.

Sem transporte contratado, a entrega e devolução seguem diretamente o fluxo habitual. O status da viagem é `PLANNED`, `IN_TRANSIT`, `COMPLETED` ou `CANCELLED`.

## Notificações internas

| Método | Endpoint | Uso |
|---|---|---|
| `GET` | `notifications/` | até 30 notificações recentes do usuário autenticado e `unread_count` |
| `POST` | `notifications/{id}/read/` | marca uma notificação própria como lida |
| `POST` | `notifications/read-all/` | marca todas as notificações próprias como lidas |

Eventos de reserva, devolução, abertura/atribuição/conclusão de OS e viagens criam avisos vinculados aos registros. As notificações pertencem exclusivamente ao destinatário; a interface consulta a API a cada 30 segundos enquanto está aberta.
