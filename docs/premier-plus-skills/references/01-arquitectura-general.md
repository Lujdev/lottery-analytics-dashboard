# Arquitectura General — PremierPluss Api Taquilla

## Stack Tecnológico

| Componente | Tecnología | Versión/Notas |
|---|---|---|
| **Framework** | CakePHP | 4.x |
| **Lenguaje** | PHP | 8.x con `declare(strict_types=1)` |
| **Base de datos** | PostgreSQL | Conexión via `ConnectionManager::get('default')` |
| **Cache** | Redis | Wrapper propio `App\Services\Cache` |
| **HTTP Client** | Cake\Http\Client | Para comunicación con providers y wallet |
| **Autenticación** | JWT | Plugin `Authentication` de CakePHP |
| **Contenedores** | Docker Compose | PHP-FPM + Nginx + Ofelia |
| **Almacenamiento** | Amazon S3 | Via controllers en `Files/` |
| **Logging** | Cake\Log\Log | Niveles: debug, info, warning, error |

---

## Estructura Completa del Proyecto

```
PremierPluss-Api-Taquilla/
├── data/                                # Aplicación CakePHP
│   ├── src/
│   │   ├── Application.php              # Bootstrap: middleware stack, routing
│   │   ├── Controller/
│   │   │   ├── AppController.php        # (125 líneas) Controller base
│   │   │   │   ├── initialize()         # Carga RequestHandler + Authentication
│   │   │   │   ├── responseJson($json, $code)     # Respuesta JSON estándar
│   │   │   │   ├── responseWithSuccess($data)      # Wrapper éxito
│   │   │   │   ├── responseWithErrors($entity)     # Wrapper error con validación
│   │   │   │   └── getServerTime()      # FrozenTime::now()
│   │   │   ├── TicketsController.php    # (2576 líneas) Legacy - NO modificar
│   │   │   │   ├── indexV3/V4()         # Crear ticket (legacy)
│   │   │   │   ├── anullV2/V3()         # Anular ticket (legacy)
│   │   │   │   ├── reversa()            # Reversar ticket
│   │   │   │   ├── pagarV2()            # Pagar ticket ganador
│   │   │   │   ├── ventaByTaquillaN()   # Reporte de cuadre
│   │   │   │   └── ~47 métodos más...
│   │   │   ├── Tickets/                 # Controllers refactorizados
│   │   │   │   ├── CreateController.php     # (1145 líneas) Creación con validaciones
│   │   │   │   ├── AnullController.php      # Anulación estándar
│   │   │   │   ├── AnullByAuditController.php
│   │   │   │   ├── AnullUnlimitedController.php  # Sin límite de tiempo
│   │   │   │   ├── AnullSucaController.php
│   │   │   │   ├── ReverseController.php
│   │   │   │   ├── PayController.php
│   │   │   │   ├── ListController.php
│   │   │   │   ├── FindByIDController.php
│   │   │   │   ├── GenerateQRController.php
│   │   │   │   └── SendInEmailController.php
│   │   │   ├── LoteriesController.php   # (707 líneas) Sorteos y resultados
│   │   │   ├── SalesController.php      # Cuadres de caja
│   │   │   ├── ExternalProvidersController.php  # CRUD providers (config encriptada)
│   │   │   ├── UsersController.php      # Login, contacto, cédula
│   │   │   ├── Users/ (7 controllers)
│   │   │   ├── Sales/ (2 controllers)
│   │   │   ├── Results/ (2 controllers)
│   │   │   ├── System/ (9 controllers)
│   │   │   ├── Files/ (5 controllers)
│   │   │   ├── Seniat/ (1 controller)
│   │   │   ├── Rates/ (1 controller)
│   │   │   └── Traits/
│   │   │       └── TicketsTrait.php
│   │   ├── Model/
│   │   │   ├── Entity/                  # 25 entidades
│   │   │   │   ├── Ticket.php
│   │   │   │   ├── Bet.php
│   │   │   │   ├── TicketProvider.php   # ticket_id, provider, provider_ticket, provider_extra_data
│   │   │   │   ├── Lotery.php
│   │   │   │   ├── ExternalProvider.php # code, base_url, config (encriptada), is_active
│   │   │   │   └── ...
│   │   │   └── Table/                   # 32 tablas ORM
│   │   │       ├── TicketsTable.php
│   │   │       ├── BetsTable.php
│   │   │       ├── LoteriesTable.php
│   │   │       ├── QuotasTable.php
│   │   │       ├── ExternalProvidersTable.php  # Columna config con encriptación
│   │   │       ├── MonedasTable.php     # Constantes MONEDAS[id → sigla]
│   │   │       └── ...
│   │   ├── Modules/
│   │   │   ├── ExternalLoteriesProviderService/
│   │   │   │   ├── BaseService.php      # (136 líneas) Orquestador
│   │   │   │   ├── TicketSkeleton.php   # (33 líneas) DTO
│   │   │   │   └── Providers/
│   │   │   │       ├── Factory.php      # (164 líneas) Strategy Pattern
│   │   │   │       ├── IjaposProvider.php       # (528 líneas) CazaLoton/UneLoton
│   │   │   │       ├── NewTachiraProvider.php    # (409 líneas)
│   │   │   │       ├── NewBanklotProvider.php
│   │   │   │       ├── VentaActivaProvider.php
│   │   │   │       ├── MaxPlayProvider.php
│   │   │   │       ├── BombProvider.php
│   │   │   │       ├── ChanceProvider.php
│   │   │   │       ├── NewChanceProvider.php
│   │   │   │       ├── SmolProvider.php
│   │   │   │       ├── BetM3Provider.php
│   │   │   │       ├── NewMaticlotProvider.php
│   │   │   │       ├── LoteriaAraguaProvider.php
│   │   │   │       ├── BanklotProvider.php      # Legacy
│   │   │   │       ├── TachiraProvider.php       # Legacy
│   │   │   │       ├── MaticlotProvider.php      # Legacy
│   │   │   │       ├── IntegratorProvider.php
│   │   │   │       ├── CMillonarioProvider.php
│   │   │   │       ├── Triple7Provider.php
│   │   │   │       ├── LottoSoftProvider.php
│   │   │   │       └── DefaultProvider.php      # No-op
│   │   │   └── Currency/
│   │   ├── Services/
│   │   │   ├── Cache.php                # get(key): ?string, put(key, value, ttlSeconds): void
│   │   │   ├── Wallet/Service.php       # (290 líneas) API Wallet externa
│   │   │   ├── Providers/               # Servicios de sorteos nativos
│   │   │   │   ├── ChanceService.php
│   │   │   │   ├── InmejorableService.php
│   │   │   │   ├── MMSGOService.php
│   │   │   │   └── TachiraService.php
│   │   │   └── RatesCurrency/           # Tasas de cambio
│   │   ├── DTO/                         # 12 Data Transfer Objects
│   │   │   ├── TransactionParams.php    # userID, reference, currency, amount, amountType
│   │   │   ├── BalanceResponse.php      # transactionID, cash, bonus, errors[]
│   │   │   ├── CurrencyBalance.php      # VES, USD
│   │   │   ├── TransactionList.php      # Detalle de una transacción
│   │   │   ├── TransactionListParams.php # Filtros de listado
│   │   │   ├── TransactionResponse.php  # Wrapper
│   │   │   ├── ContactInfoParams.php
│   │   │   ├── SeniatInfoParams.php
│   │   │   ├── FilesParams.php
│   │   │   ├── BankAccountByUser.php
│   │   │   ├── ClienteFinal.php
│   │   │   └── WithdrawalAndDepositIntentions.php
│   │   ├── Repositories/               # 20 repositorios
│   │   │   ├── HorarioDeAperturaRepository.php  # getConfiguration()
│   │   │   ├── BloqueoAleatorioRepository.php   # getConfiguration() (umbral, porcentaje)
│   │   │   └── ...
│   │   ├── Middleware/
│   │   │   ├── RequestMiddleware.php              # Logging/validación
│   │   │   ├── PersistenceOrmFailedMiddleware.php # Captura errores ORM
│   │   │   └── UnauthenticatedHandler.php         # Respuesta 401
│   │   ├── Exception/
│   │   └── Log/
│   ├── config/
│   │   ├── routes.php             # (527 líneas) 2 scopes: / y /api-v1
│   │   └── app_local.php          # Wallet.url, DB, cache, encryption keys
│   ├── plugins/
│   ├── tests/
│   └── vendor/
├── docs/                          # Documentación
│   ├── premier-plus-skills/       # 👈 Estás aquí
│   ├── ApiIjapos.md               # Documentación técnica API Ijapos (307 líneas)
│   ├── ExternalProviders-Mejoras-Encriptacion.md
│   └── Changelog.md
├── nginx/                         # Configuración del proxy reverso
├── ofelia/                        # Cron jobs en Docker
├── etc/
└── compose.yaml                   # Docker Compose: app, nginx, ofelia
```

---

## Patrones Arquitectónicos

### 1. Strategy Pattern — External Providers

```
TicketSkeleton (DTO)
    ↓
BaseService (orquestador)
    ├── groupBy(bets, 'lotery_id')
    ├── getLotery(loteryID) → product_new
    ├── getIntegratorByProductID(productID) → provider name
    └── Factory::loadProvider(name, bets, skeleton)→sendBets()
        ↓
Provider específico (IjaposProvider, NewTachiraProvider, etc.)
```

### 2. DTO Pattern

```php
// TransactionParams — parámetros para Wallet
class TransactionParams {
    public int|null $userID;
    public string|null $reference;     // "{user_id}-{YmdHis.u}"
    public int|null $currency;         // 1=Bs, 2=USD
    public float|null $amount;
    public int|null $amountType;       // 0=cash
    public function getCurrencyISO()   // MonedasTable::MONEDAS[currency]['sigla']
}

// BalanceResponse — respuesta del Wallet
class BalanceResponse {
    public CurrencyBalance|null $cash;  // VES, USD
    public CurrencyBalance|null $bonus; // VES, USD
    private $errors = [];
    public function hasError(): bool
    public function addError(string $message): void
}
```

### 3. Repository Pattern

```php
HorarioDeAperturaRepository::getConfiguration() → horario de apertura de la taquilla
BloqueoAleatorioRepository::getConfiguration()  → umbral y porcentaje para bloqueo
```

### 4. AppController Base

Todos los controllers heredan de `AppController.php` que provee:
```php
responseJson($json, $code = 200)        // JSON response estándar
responseWithSuccess($data, $additional)  // Wrapper éxito con data
responseWithErrors($entity, $message)    // Wrapper error con validación CakePHP
getServerTime()                          // FrozenTime::now()
```

---

## Middleware Stack

```
Request → BodyParserMiddleware (JSON parsing)
       → RequestMiddleware (logging y validación)
       → AuthenticationMiddleware (JWT verificación)
       → PersistenceOrmFailedMiddleware (captura errores ORM)
       → UnauthenticatedHandler (respuesta 401)
       → Controller
```

---

## Tablas de BD Importantes

| Tabla | Uso |
|---|---|
| `tickets` | Tickets creados (con partición diaria: `tickets_YYYYMMDD`) |
| `bets` | Jugadas individuales (con partición: `bets_YYYYMMDD`) |
| `tickets_provider` | Relación ticket↔provider (provider, provider_ticket, provider_extra_data) |
| `combined_bets` | Números individuales de tripletas/pollas |
| `loteries` | Sorteos disponibles (lotery_hour, dia_lun...dia_dom, enable) |
| `new_products` | Productos/loterías (config JSON, result_source) |
| `quotas` | Cupos por número/lotería/rol/entidad |
| `external_providers` | Configuración de providers (code, base_url, config encriptado, is_active) |
| `users` | Usuarios (center_id, group_id, agency_id, role_id, master_center_id) |
| `centers_currencies` / `groups_currencies` / `agencys_currencies` | Monedas habilitadas por jerarquía |
| `agency_sale_by_currencies` | Límite de venta diaria por agencia |
| `center_sale_by_currencies` / `group_sale_by_currencies` | Límites venta y tripletas por centro/grupo |
| `provider_agency_blocked` | Agencias bloqueadas por provider |
| `setups` | Configuración global: quota_min, quota_max por moneda |
| `contact_info` | Datos de contacto de clientes |

---

## Cache Redis

```php
// App\Services\Cache — Métodos estáticos
Cache::get(string $key): ?string
Cache::put(string $key, string $value, int $ttlSeconds): void
```

| Clave | TTL | Uso |
|---|---|---|
| `provider_config_{ProviderName}` | 1200s (20 min) | Config de cada provider |
| `newtachira-token:{usuario}` | 86400s (1 día) | Session token de NewTachira |
| `ticket:{user_id}:{audit}` | 180s (3 min) | Cache de ticket para reintentos con audit |
| `sorteos:{user_id}:{currency_id}` | Variable | Sorteos disponibles |

---

## Convenciones de Código

- **Respuestas de error con código:** Todos los errores retornan `['message' => '...', 'code' => 'ERR_XX']`
- **Código de error patterns:** `ERR_1`..`ERR_4` (validación), `LAT` (fuera de horario), `WALL_ERR_D1` (wallet débito), `WALL_ERR_ROLLBACK` (wallet rollback), `ERR_CU1` (moneda), `ERR_C1` (contacto), `ERR_PAB` (agencia bloqueada)
- **Monedas:** `1 = VES (Bolívares)`, `2 = USD (Dólares)` — mapeo en `MonedasTable::MONEDAS`
- **Roles:** `1 = Admin`, `3 = Center`, `4 = Group`, `5 = Agency`, `13 = Master Center`, `11 = Cliente Final`
- **Identity en request:** `$this->request->getAttribute('identity')` → `id, role_id, center_id, group_id, agency_id, master_center_id, contact_info_id`
- **Header especial:** `Provider-Agency` — ID de agencia del proveedor
