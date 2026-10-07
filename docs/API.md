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
| `POST` | `rental-quotes/{id}/return/` | registra devolução e bloqueia os itens para inspeção |
| `POST` | `rental-quotes/{id}/finalize-return/` | conclui devolução e encaminha avarias à manutenção |
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

Ao reservar, entregar ou prorrogar, a API verifica sobreposição, situação operacional, OS aberta e manutenção crítica vencida dentro de transação atômica. A OS pré-locação vinculada à própria reserva é exceção na disponibilidade, mas outras OS abertas continuam bloqueando. A equipe de Manutenção registra o checklist por `PATCH rental-inspections/{id}/`; aprovação conclui e libera a OS automaticamente, e impedimento mantém o equipamento bloqueado. Uma OS pré-locação de reserva ativa não pode ser concluída ou excluída manualmente. Se a reserva for cancelada após um impedimento, a OS permanece aberta para reparo e exige testes finais e liberação técnica. A entrega exige inspeção aprovada e OS liberada para todos os equipamentos. Na devolução, o equipamento permanece em `INSPECTION`; itens avariados ou críticos geram automaticamente uma OS pós-locação.

As evidências podem ser enviadas por `media/` usando `rental_inspection=<id>`, categoria `INSPECTION` e upload multipart.
