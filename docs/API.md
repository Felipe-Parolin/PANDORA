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
| CRUD | `maintenance-plans/` | plano e periodicidade |
| CRUD | `service-orders/` | ciclo da ordem de serviço |
| `GET` | `service-orders/checklist-template/?type=PREVENTIVE` | checklist/roteiro da fábrica |

Filtros de OS: `status`, `type`, `equipment`, `technician`, `search` e `queue=unassigned`.

O ciclo inclui `OPEN`, `SCHEDULED`, `IN_PROGRESS`, `WAITING_PARTS`, `ABANDONED`, `COMPLETED` e `CANCELLED`. Ao usar `ABANDONED`, `abandoned_reason` é obrigatório; a API registra automaticamente `abandoned_at`. O início da execução registra `started_at`.

## Locação e orçamento

| Método | Endpoint | Uso |
|---|---|---|
| CRUD | `rental-quotes/` | orçamento e seus itens |
| `GET` | `rental-quotes/availability/?start=2026-09-20&end=2026-09-25` | equipamentos disponíveis e bloqueados, com motivo |

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

Ao alterar `status` para `APPROVED`, a API verifica sobreposição, situação operacional, OS aberta e manutenção crítica vencida dentro de transação atômica.
