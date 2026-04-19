---
name: PremierPluss Api Taquilla
description: API REST de taquilla para sistema de loterías. CakePHP 4.x, PostgreSQL, Redis, Docker.
---

# PremierPluss Api Taquilla — Skill Principal

API REST para gestión de taquillas de loterías: venta de tickets, integración con 20 providers de loterías externos, wallet, resultados y reportes.

---

## Stack

| Componente | Tecnología |
|---|---|
| Framework | CakePHP 4.x (PHP 8.x strict_types) |
| BD | PostgreSQL |
| Cache | Redis (`App\Services\Cache`) |
| Contenedores | Docker + Nginx + Ofelia (cron) |
| Almacenamiento | Amazon S3 |

---

## Estructura Clave

```
data/src/
├── Controller/                # ~68 archivos
│   ├── AppController.php      # Base: responseJson(), Authentication, RequestHandler
│   ├── Tickets/               # 10 controllers (Create, Anull, Reverse, Pay, List, FindByID, QR, SendInEmail, AnullByAudit, AnullUnlimited)
│   ├── Users/                 # 7 controllers (FindByUsername, FindByCedula, UserContactInfo, GetUserCurrencies, etc.)
│   ├── Sales/                 # 2 controllers (ListByTaquilla, ListByAgency)
│   ├── Results/               # 2 controllers (GetResult, GetAllFromProductInString)
│   ├── System/                # 9 controllers (HealthCheck, Time, PreAwardHook, QuotasHook, States, Municipios, etc.)
│   ├── Files/                 # 5 controllers (Upload, Get, Update, DeleteById, DeleteByPrefix)
│   ├── TicketsController.php  # Legacy (2576 líneas)
│   ├── LoteriesController.php # Sorteos, resultados, cache (707 líneas)
│   ├── SalesController.php    # Cuadres de caja
│   └── ExternalProvidersController.php  # CRUD providers (config encriptada)
├── Modules/
│   └── ExternalLoteriesProviderService/
│       ├── BaseService.php          # Orquestador (136 líneas)
│       ├── TicketSkeleton.php       # DTO: currency, center, group, agency, user, bets
│       └── Providers/
│           ├── Factory.php          # Strategy Pattern (164 líneas)
│           └── [20 providers].php   # IjaposProvider, NewTachiraProvider, etc.
├── Services/
│   ├── Cache.php                    # Redis: get(), put($key, $value, $ttl)
│   └── Wallet/Service.php          # API externa: balance, debit, credit, rollback, transactionsList
├── DTO/                             # 12 DTOs
│   ├── TransactionParams.php        # userID, reference, currency, amount, amountType + getCurrencyISO()
│   ├── BalanceResponse.php          # transactionID, cash(CurrencyBalance), bonus(CurrencyBalance), errors[]
│   ├── CurrencyBalance.php          # VES, USD
│   ├── TransactionList.php          # Transactions individual
│   ├── TransactionListParams.php    # since, until, currency, PageNumber, PageSize
│   └── TransactionResponse.php     # Wrapper de transacciones
├── Repositories/                    # 20 repos (HorarioDeAperturaRepository, BloqueoAleatorioRepository, etc.)
├── Middleware/
│   ├── RequestMiddleware.php              # Logging/validación de requests
│   ├── PersistenceOrmFailedMiddleware.php # Error handling ORM
│   └── UnauthenticatedHandler.php         # 401 personalizado
└── Model/
    ├── Entity/ (25 entidades)
    └── Table/ (32 tablas: Tickets, Bets, Loteries, Quotas, ExternalProviders, etc.)
```

---

## Referencias Detalladas

| # | Archivo | Contenido |
|---|---|---|
| 01 | [01-arquitectura-general.md](./references/01-arquitectura-general.md) | Stack, estructura, patrones de diseño, flujo de request, Docker, middleware, DTOs |
| 02 | [02-tickets-ciclo-de-vida.md](./references/02-tickets-ciclo-de-vida.md) | Creación con validaciones detalladas, cupos jerárquicos, tripletas, wallet integration, bloqueo aleatorio, error codes |
| 03 | [03-external-providers.md](./references/03-external-providers.md) | BaseService orquestador, Factory pattern, TicketSkeleton DTO, mapeo producto→integrador, contrato de providers |
| 04 | [04-providers-individuales.md](./references/04-providers-individuales.md) | Cada provider con su API, endpoints, auth, formatos de datos, generación de tk, códigos de respuesta |
| 05 | [05-anulaciones-y-reversos.md](./references/05-anulaciones-y-reversos.md) | Flujos completos de anulación/reversa, extra_data por provider, rollback, makeVoid, códigos de error |
| 06 | [06-resultados-y-sorteos.md](./references/06-resultados-y-sorteos.md) | LoteriesController, consultas SQL de sorteos, filtros por jerarquía, cache, servicios nativos |
| 07 | [07-wallet-y-transacciones.md](./references/07-wallet-y-transacciones.md) | Wallet API completa, DTOs con código fuente, endpoints HTTP, manejo de errores, monedas |
| 08 | [08-usuarios-y-autenticacion.md](./references/08-usuarios-y-autenticacion.md) | JWT auth, AppController base, middleware stack, rutas exactas, jerarquía organizacional |
| 09 | [09-ventas-y-reportes.md](./references/09-ventas-y-reportes.md) | Cuadres de caja, control de ventas por agencia con SQL, límites, intenciones |
| 10 | [10-sistema-y-configuracion.md](./references/10-sistema-y-configuracion.md) | Health check, hooks, S3, cache Redis, Docker, logs, external providers CRUD |

---

## Mapeo Producto → Provider

Definido en `BaseService::getIntegratorByProductID()` (`data/src/Modules/ExternalLoteriesProviderService/BaseService.php:84-134`):

| Products | Provider | Estado |
|---|---|---|
| 2 | Betf4 | ✅ (Zoológico Activo) |
| 5, 61, 62, 64 | VentaActiva | ✅ |
| 7, 11, 12, 13, 15 | NewBanklot | ✅ (incluye Triple Caracas) |
| 14 | NewTachira | ✅ (reemplazó Tachira legacy) |
| 20, 24, 73 | MaxPlay | ✅ (reemplazó NewMaticlot para estos IDs) |
| 21 | Bomb | ✅ |
| 26, 34, 35 | Ijapos | ✅ (CazaLoton + UneLoton) |
| 27, 28 | Chance | ✅ |
| 38, 93, 94, 95 | NewMaticlot | ✅ |
| 39, 40 | BetM3 | ✅ |
| 63 | LoteriaAragua | ✅ |
| 74, 85, 88, 89 | Smol | ✅ |
| 90, 91, 92 | NewChance | ✅ |

Si un `product_id` no está mapeado → `DefaultProvider` (no-op).

---

## Rutas Completas de la API

Definidas en `data/config/routes.php` (527 líneas, 2 scopes):

### Scope `/` (sin auth)
```
POST /tickets/add-v3        → Tickets/CreateController  (duplicado legacy)
POST /tickets/add-v4        → Tickets/CreateController  (duplicado legacy)
POST /tickets/add_v4        → Tickets/CreateController  (duplicado legacy)
GET  /validate-email/{token} → ValidateEmail/SendEmail::validateEmail
```

### Scope `/api-v1` (con auth JWT)
**Tickets:** POST create, GET list, GET {id}, POST {id}/anull, POST {id}/unlimited-anull, POST {id}/reverse, POST audit/{audit}/anull, DELETE suca-anull/{id}/anull, POST {id}/pay, GET {id}/qr, POST {id}/send-email

**Sorteos/Resultados:** GET /loteries, GET /results, GET /results/{product_id}/string

**Usuarios:** GET /users, GET /users/me, PUT /users/me/update, GET /users/currencies, POST /users/token/{idHardware}, PATCH/POST seniat-info, GET /contact/{cedula}, GET /contact-info/{cedula}, GET /client/{nit}

**Ventas:** GET /sales/consolidado, GET /sales/detallado, GET /sales/tripleta, GET /sales/taq, GET /sales/agencies

**Sistema:** GET /system/live, GET /system/time, POST /system/hook/preaward/{lotery_id}, POST /system/hook/set-limits, GET /system/states, GET /system/municipios, GET /system/ciudades

**Wallet/Financiero:** POST /intentions, GET /user/WithdrawalAndDepositIntentions, GET /user/accounts, POST /user/add-account, PATCH /user/update-account, PATCH /user/delete-account

**Archivos:** POST /s3/upload-file, POST /user/upload-file, GET /user/files, PATCH /user/delete-file-id, PATCH /user/delete-file-prefix, PATCH /user/update-file

**Providers:** GET/POST /external-providers, GET/PUT/DELETE /external-providers/{id}

**Otros:** GET /products, GET /products/available/{currency_id}, PATCH /user/password-change, POST /user/fpc, GET /validate/send-email, GET /rates, GET /banks-venezuela, GET /messages, POST /messages/saw/{id}, GET /figures-info, POST /agency-data, GET /agencies, POST /taquilla-final/create-user, GET /taquilla-final/user-balance, GET /taquilla-final/listTransactions, POST /currency/update-rates

---

## Changelog

Ver [Changelog.md](./Changelog.md) para historial de cambios del proyecto.
