# External Providers — Arquitectura del Sistema

## Resumen

El sistema integra ~20 providers de loterías externos. La arquitectura usa un **Strategy Pattern** donde `BaseService` orquesta el envío de jugadas a los providers correctos según el `product_id` de cada lotería.

---

## Componentes del Sistema

### 1. `TicketSkeleton` — DTO de entrada

```php
// data/src/Modules/ExternalLoteriesProviderService/TicketSkeleton.php (33 líneas)
class TicketSkeleton {
    public int $ticket_currency;     // 1=VES, 2=USD
    public int $center_id;
    public int $group_id;
    public int $agency_id;
    public int $user_id;
    public array $bets;              // Array de jugadas [{lotery_id, number, amount}, ...]
}
```

### 2. `BaseService` — Orquestador (136 líneas)

```php
// data/src/Modules/ExternalLoteriesProviderService/BaseService.php
class BaseService {
    public array $tickets;           // Resultado por provider: ['Ijapos' => [...], 'NewTachira' => [...]]

    public function __construct(TicketSkeleton $ticketSkeleton) {
        // Paso 1: Agrupar bets por lotery_id
        $groupByLoteries = collection($ticketSkeleton->bets)->groupBy('lotery_id');

        // Paso 2: Para cada lotería, obtener el product_new
        foreach ($groupByLoteries as $loteryID => $bets) {
            $productID = $connection->getLotery($loteryID)['product_new'];
            $groupByProducts[$productID][$loteryID] = $bets;
        }

        // Paso 3: Para cada producto, obtener el integrador
        foreach ($groupByProducts as $productID => $bets) {
            $integrator = $this->getIntegratorByProductID($productID);
            $this->groupedByProvider[$integrator][$productID] = $bets;
        }
    }

    public function processTickets(): array {
        foreach ($this->groupedByProvider as $integrator => $products) {
            $startTime = microtime(true);
            $this->tickets[$integrator] = ExternalProviderFactory::loadProvider(
                $integrator, $products, $this->ticketSkeleton
            )->sendBets();
            // Log tiempo de respuesta en ms
        }
        return $this->tickets;
    }

    public function getBets(): array {
        // Merge todas las bets de todos los providers, filtrar amount > 0
        $bets = array_column($this->tickets, 'bets');
        return collection(array_merge(...$bets))
            ->filter(fn($bet) => ($bet['amount'] ?? 0) > 0)->toArray();
    }

    public function rollbackRecentTickets(): void {
        foreach ($this->tickets as $integrator => $ticket) {
            ExternalProviderFactory::anullRecent($integrator, $ticket);
        }
    }
}
```

### 3. `Factory` — Strategy Pattern (164 líneas)

```php
// data/src/Modules/ExternalLoteriesProviderService/Providers/Factory.php
class Factory {
    public static function loadProvider(string $name, array $bets, TicketSkeleton $skeleton): ProviderInterface {
        return match($name) {
            'Betf4'         => new Betf4Provider($bets, $skeleton),
            'Ijapos'        => new IjaposProvider($bets, $skeleton),
            'NewTachira'    => new NewTachiraProvider($bets, $skeleton),
            'NewBanklot'    => new NewBanklotProvider($bets, $skeleton),
            'VentaActiva'   => new VentaActivaProvider($bets, $skeleton),
            'MaxPlay'       => new MaxPlayProvider($bets, $skeleton),
            'Bomb'          => new BombProvider($bets, $skeleton),
            'Chance'        => new ChanceProvider($bets, $skeleton),
            'NewChance'     => new NewChanceProvider($bets, $skeleton),
            'Smol'          => new SmolProvider($bets, $skeleton),
            'BetM3'         => new BetM3Provider($bets, $skeleton),
            'NewMaticlot'   => new NewMaticlotProvider($bets, $skeleton),
            'LoteriaAragua' => new LoteriaAraguaProvider($bets, $skeleton),
            default         => new DefaultProvider($bets, $skeleton),
        };
    }

    public static function anullRecent(string $name, array $ticket): void {
        // Llama al método reverse() del provider si ticket_number no es null
        if ($ticket['ticket_number'] !== null) {
            match($name) {
                'Ijapos'     => IjaposProvider::reverse($ticket),
                'NewTachira' => NewTachiraProvider::reverse($ticket),
                // ... más providers
            };
        }
    }

    public static function anull(string $name, int $ticketID, int $currencyID): array {
        // Llama al método anull() del provider para anulaciones del usuario
        return match($name) {
            'Ijapos'     => IjaposProvider::anull($ticketID, $currencyID),
            'NewTachira' => NewTachiraProvider::anull($ticketID, $currencyID),
            // ... más providers
        };
    }
}
```

---

## Mapeo Completo producto → provider

Definido en `BaseService::getIntegratorByProductID()` (líneas 84-134):

```php
$integrator = [
    // Betf4 (Zoológico Activo + Triple Pirámide de Oro)
    2 => 'Betf4',   // Animales
    17 => 'Betf4',  // Triples
    // VentaActiva
    5 => 'VentaActiva', 61 => 'VentaActiva', 62 => 'VentaActiva', 64 => 'VentaActiva',
    // NewBanklot (incluye Triple Caracas)
    7 => 'NewBanklot', 11 => 'NewBanklot', 12 => 'NewBanklot', 13 => 'NewBanklot', 15 => 'NewBanklot',
    // NewTachira (reemplazó legacy Tachira)
    14 => 'NewTachira',
    // Bomb
    21 => 'Bomb',
    // Ijapos (CazaLoton + UneLoton)
    26 => 'Ijapos', 34 => 'Ijapos', 35 => 'Ijapos',
    // Chance
    27 => 'Chance', 28 => 'Chance',
    // NewChance
    90 => 'NewChance', 91 => 'NewChance', 92 => 'NewChance',
    // NewMaticlot
    38 => 'NewMaticlot', 93 => 'NewMaticlot', 94 => 'NewMaticlot', 95 => 'NewMaticlot',
    // BetM3
    39 => 'BetM3', 40 => 'BetM3',
    // LoteriaAragua
    63 => 'LoteriaAragua',
    // Smol
    74 => 'Smol', 85 => 'Smol', 88 => 'Smol', 89 => 'Smol',
    // MaxPlay (reemplazó NewMaticlot para estos IDs)
    20 => 'MaxPlay', 24 => 'MaxPlay', 73 => 'MaxPlay',
];
// Default: 'DefaultProvider' (no-op, retorna bets sin modificar)
```

---

## Flujo Visual

```
CreateController::index()
    ↓
TicketSkeleton(currency, center, group, agency, user, bets[])
    ↓
BaseService(ticketSkeleton)
    ├── bets.groupBy('lotery_id')
    │   ├── loteryID=123 → product_new=34 → 'Ijapos'
    │   ├── loteryID=456 → product_new=14 → 'NewTachira'
    │   └── loteryID=789 → product_new=5  → 'VentaActiva'
    ↓
processTickets()
    ├── Factory::loadProvider('Ijapos', bets, skeleton)→sendBets()
    │   → {ticket_number: 'ABC123', bets: [...], extra_data: '{...}'}
    ├── Factory::loadProvider('NewTachira', bets, skeleton)→sendBets()
    │   → {ticket_number: 'XYZ789', bets: [...], extra_data: '{...}'}
    └── Factory::loadProvider('VentaActiva', bets, skeleton)→sendBets()
        → {ticket_number: 'DEF456', bets: [...], extra_data: '{...}'}
    ↓
getBets()  // Merge + filter(amount > 0)
    ↓
CreateController guarda en tickets + bets + tickets_provider
```

---

## Contrato del Provider

Cada provider debe implementar:

| Método | Tipo | Descripción |
|---|---|---|
| `sendBets()` | Instancia | Enviar jugadas a la API. Retorna `{ticket_number, bets[], extra_data}` |
| `formatBets($bets)` | Instancia | Convertir bets internas al formato del provider |
| `formatOriginalBets($bets)` | Instancia | Flatten bets sin modificar |
| `agotarBets($bets)` | Instancia | Marcar todas las bets como `amount=0` |
| `formatToOrigin($providerBets)` | Instancia | Convertir respuesta del provider de vuelta al formato interno |
| `reverse($ticket)` | Estática | Reversar un ticket recién creado (rollback inmediato) |
| `anull($ticketID, $currencyID)` | Estática | Anular un ticket guardado en BD (anulación del usuario) |
| `makeVoid($serial, $currencyID)` | Estática | Ejecutar la llamada HTTP de anulación al provider |

### Respuesta estándar de `sendBets()`
```php
// Éxito
['ticket_number' => 'ABC123', 'bets' => [...], 'extra_data' => '{"id":"...", "serial":"...", ...}']

// Fallo total
['ticket_number' => null, 'bets' => $this->agotarBets($this->bets), 'extra_data' => null]
```

---

## Configuración de Providers

Almacenadas en tabla `external_providers`, columna `config` **encriptada** con clave dedicada.

```php
// Lectura con cache de 20 minutos
$cacheKey = "provider_config_{ProviderName}";
$cached = Cache::get($cacheKey);
if ($cached) return json_decode($cached, true);

$config = ExternalProvidersTable->find()->where(['code' => $providerName])->first();
Cache::put($cacheKey, json_encode($config), 1200);  // 20 min TTL
```

Estructura típica de `config`:
```json
{
    "base_url": "https://api.provider.com",
    "providercod": "ABC",
    "poscod": "POS001",
    "user": "username",
    "password": "password",
    "token": "auth-token"
}
```

---

## Performance Monitoring

```php
// BaseService::processTickets() registra tiempo por provider
$startTime = microtime(true);
$this->tickets[$integrator] = Factory::loadProvider($integrator, ...)->sendBets();
$executionTimeMs = (microtime(true) - $startTime) * 1000;
Log::write('debug', "{$integrator},response_time_ms:{$executionTimeMs}");
```
