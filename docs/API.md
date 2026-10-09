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
| `GET` | `dashboard/` | indicadores do painel |

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

Filtros úteis: `equipment/?status=AVAILABLE`, `equipment/?category=1`, `customers/?search=nome` e `media/?category=MANUAL`.

As respostas de login e `auth/me/` incluem `access_group`, `access_group_name` e `permissions`. O código `*` representa acesso administrativo total. A API retorna `403` quando a ACL não autoriza a ação e `409` quando uma exclusão é impedida por vínculos protegidos.

## Manutenção

| Método | Endpoint | Uso |
|---|---|---|
| CRUD | `maintenance-plans/` | plano por data, periodicidade e horas de uso |
| CRUD | `service-orders/` | ciclo da ordem de serviço |
| `GET` | `service-orders/checklist-template/?type=PREVENTIVE` | checklist/roteiro da fábrica |

Filtros de OS: `status`, `type`, `equipment`, `technician`, `search` e `queue=unassigned`.

O ciclo inclui `OPEN`, `SCHEDULED`, `IN_PROGRESS`, `WAITING_PARTS`, `ABANDONED`, `COMPLETED` e `CANCELLED`. Ao usar `ABANDONED`, `abandoned_reason` é obrigatório; a API registra automaticamente `abandoned_at`. O início da execução registra `started_at`.

Planos expõem `due_date`, `due_usage_hours`, `usage_remaining` e `alert_status`. Os alertas podem ser `OK`, `UPCOMING`, `OVERDUE` ou `CRITICAL`. Uma manutenção crítica vencida por data ou uso bloqueia reserva e entrega.

## Locação e orçamento

| Método | Endpoint | Uso |
|---|---|---|
| CRUD | `rental-quotes/` | orçamento e seus itens |
| `GET` | `rental-quotes/availability/?start=2026-09-20&end=2026-09-25` | equipamentos disponíveis e bloqueados, com motivo |
| `POST` | `rental-quotes/{id}/reserve/` | aprova e reserva, gerando inspeção e OS pré-locação para cada equipamento |
| `POST` | `rental-quotes/{id}/cancel/` | cancela com motivo e libera os equipamentos |
| `POST` | `rental-quotes/{id}/deliver/` | registra entrega após inspeções aprovadas |
| `POST` | `rental-quotes/{id}/extend/` | prorroga após nova validação de disponibilidade |
| `POST` | `rental-quotes/{id}/return/` | registra devolução e abre uma OS de inspeção final por equipamento na Manutenção |
| `POST` | `rental-quotes/{id}/finalize-return/` | conclui devolução após todas as inspeções finais |
| `GET/PATCH` | `rental-inspections/` | consulta e executa checklist por equipamento |

Ao editar um orçamento, `ignore_quote=<id>` desconsidera a própria reserva durante a nova verificação de disponibilidade.

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

Ao reservar, entregar ou prorrogar, a API verifica sobreposição, situação operacional, OS aberta e manutenção crítica vencida dentro de transação atômica. A OS pré-locação vinculada à própria reserva é exceção na disponibilidade, mas outras OS abertas continuam bloqueando. A equipe de Manutenção registra o checklist por `PATCH rental-inspections/{id}/`; aprovação conclui e libera a OS automaticamente, e impedimento mantém o equipamento bloqueado. Uma OS pré-locação de reserva ativa não pode ser concluída ou excluída manualmente. Se a reserva for cancelada após um impedimento, a OS permanece aberta para reparo e exige testes finais e liberação técnica. A entrega exige inspeção aprovada e OS liberada para todos os equipamentos. Na devolução, é criada uma OS pós-locação por equipamento na Manutenção, inclusive quando não há avaria; a inspeção final conclui a OS limpa ou a mantém aberta para reparo.

As evidências podem ser enviadas por `media/` usando `rental_inspection=<id>`, categoria `INSPECTION` e upload multipart.

## Transporte opcional

| Método | Endpoint | Uso |
|---|---|---|
| CRUD | `vehicles/` | veículos, placa, capacidade, disponibilidade e observações |
| `GET/PATCH` | `transport-tasks/` | consulta e planejamento de viagens de entrega/coleta |
| `POST` | `transport-tasks/{id}/start/` | saída com veículo e motorista atribuídos, após liberação técnica no caso de entrega |
| `POST` | `transport-tasks/{id}/complete/` | conclui viagem e libera próxima etapa da locação |

Somente reservas com `delivery_transport_required` geram viagem de entrega. A viagem de coleta é criada ao registrar a entrega quando `return_transport_required` está ativo. O orçamento expõe as viagens em `transport_tasks` e inclui `transport_fee` no `total`. A exclusão de veículos ou orçamentos com viagens vinculadas é impedida para preservar o histórico. As permissões são `logistics.view` e `logistics.manage`.

Sem transporte contratado, a entrega e devolução seguem diretamente o fluxo habitual. O status da viagem é `PLANNED`, `IN_TRANSIT`, `COMPLETED` ou `CANCELLED`.

## Notificações internas

| Método | Endpoint | Uso |
|---|---|---|
| `GET` | `notifications/` | até 30 notificações recentes do usuário autenticado e `unread_count` |
| `POST` | `notifications/{id}/read/` | marca uma notificação própria como lida |
| `POST` | `notifications/read-all/` | marca todas as notificações próprias como lidas |

Eventos de reserva, devolução, abertura/atribuição/conclusão de OS e viagens criam avisos vinculados aos registros. As notificações pertencem exclusivamente ao destinatário; a interface consulta a API a cada 30 segundos enquanto está aberta.
