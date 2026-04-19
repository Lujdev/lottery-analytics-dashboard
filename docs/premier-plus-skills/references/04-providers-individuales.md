# Providers Individuales — Detalle Técnico

## Betf4Provider

**Productos:**
- `product_id = 2` → Animales (Zoológico Activo, lotery_id 13–22)
- `product_id = 17` → Triples (Triple Pirámide de Oro, lotery_id 180–183, 741, 743)

**Archivo:** `data/src/Modules/ExternalLoteriesProviderService/Providers/Betf4Provider.php`
**Protocolo:** JSON POST, una request por `raffle_id`, batch pre-cierre
**Auth:** Headers `api_key`, `integrator_id`, `structure_id` (header)

> ⚠️ **Betf4 usa un modelo de envío diferente al resto de providers**: `sendBets()` solo guarda localmente (genera `ticket_number` local sin llamar a la API). El envío real a Betf4 se hace via el endpoint `POST /api-v1/external-providers/betf4-batch-send` antes del cierre del sorteo, normalmente llamado por n8n.

### Configuración (`external_providers.config`)

```json
{
    "api_key": "...",
    "integrator_id": 7,
    "header_structure_id": 2671,
    "structure_id": 2672,
    "station": 2610
}
```

> ⚠️ **`header_structure_id` ≠ `structure_id`**: el primero va solo en el header HTTP; el segundo va en el body JSON de cada request.

### Endpoint de Venta (Betf4 API)

```
POST {base_url}/api/v1/sales_api/new_sales
```

**Headers:**
```
Content-Type: application/json
api_key: <config.api_key>
integrator_id: <config.integrator_id>
structure_id: <config.header_structure_id>   ← 2671
```

**Body (por cada raffle_id):**
```json
{
    "structure_id": 2672,
    "station": 2610,
    "raffle_id": 116,
    "bets": "<base64(zlib(json_bets))>",
    "currency_id": 15
}
```

> `currency_id` es el ID interno de Betf4, no el nuestro. Ver mapa de monedas abajo.

### Mapa de Monedas

| Nuestro `currency_id` | Betf4 `currency_id` |
|---|---|
| 1 (VES) | 15 |
| 2 (USD) | 2 |
| 3 (BRL) | 9 |
| 5 (COP) | 12 |

### Formato de jugadas (`bets`)

**Animales:** número 2 dígitos con padding — `"02"`, `"15"`, `"0"` (Delfin), `"00"` (Ballena)  
**Triples:** número 3 dígitos con padding — `"001"`, `"123"`, `"999"`

```php
// JSON → gzcompress() (ZLIB) → base64_encode()
$formattedBets = [["n" => "02", "m" => 50.00], ...];
$bets = base64_encode(gzcompress(json_encode($formattedBets)));
```

### Mapeo lotery_id → raffle_id

```php
// Animales (Zoológico Activo, product_id=2)
13 => 108,  14 => 109,  15 => 110,  16 => 111,
17 => 112,  18 => 113,  19 => 114,  20 => 115,
21 => 116,  22 => 117,

// Triples (Triple Pirámide de Oro, product_id=17)
181 => 75,  // TP-A 11:45 AM
180 => 79,  // TP-B 11:45 AM
182 => 76,  // TP-A 03:45 PM
183 => 80,  // TP-B 03:45 PM
743 => 77,  // TP-A 06:45 PM
741 => 81,  // TP-B 06:45 PM
```

Los raffle_id de triples son `[75, 76, 77, 79, 80, 81]`, detectados por `isTripleRaffle()` para aplicar padding de 3 dígitos.

### Endpoint de Batch Send (nuestro)

```
POST /api-v1/external-providers/betf4-batch-send
```

**Query params opcionales:**
- `?minutes=7` (default) — captura sorteos que cierran en los próximos N minutos
- `?force_lotery_id=22` — fuerza envío de un sorteo específico ignorando tiempo

**Flujo interno por sorteo/moneda:**
1. `getCurrenciesWithBets($loteryId)` — consulta solo monedas con jugadas reales del día (evita queries innecesarios)
2. `isAlreadySent($loteryId, $currencyId)` — dedup via `betf4_send_log` (si existe registro OK de hoy → agrega `SKIPPED` en details y hace `continue`)
3. `getAggregatedBetf4Bets($loteryId, $currencyId)` — agrega montos por número (`SUM(amount) GROUP BY number`)
4. `Betf4Provider::sendBatchToApi($bets, $loteryId, $currencyId)` — llama la API de Betf4
5. `insertSendLog($db, [...])` — registra resultado en `betf4_send_log`
6. `updateProviderExtraData($db, $loteryId, $currencyId, [...])` — guarda ticket/serial en `tickets_provider.provider_extra_data`

**Respuesta del endpoint:**
```json
{
    "success": true,
    "sent": 2,
    "failed": 0,
    "details": [
        {
            "product": "animales",
            "lotery_id": 22,
            "lotery": "ZOOLOGICO ACTIVO 06:00 PM",
            "currency": "VES",
            "currency_id": 1,
            "bets": 8,
            "total": 200.00,
            "status": "OK"
        },
        {
            "product": "triples",
            "lotery_id": 741,
            "lotery": "TRIPLE PIRAMIDE B 06:45 PM",
            "currency": "VES",
            "currency_id": 1,
            "bets": 5,
            "total": 350.00,
            "status": "OK"
        }
    ]
}
```

Posibles valores de `status` en `details`: `OK`, `FAILED` (con campo `error`), `SKIPPED` (con campo `message: "Ya enviado hoy"`).

HTTP 200 si `failed=0`, HTTP 207 si hay al menos un fallo.

### Tabla `betf4_send_log`

Registra cada envío batch. Usada también como mecanismo de deduplicación (reemplaza Redis).

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | SERIAL PK | Auto-incremental |
| `lotery_id` | INTEGER | Nuestro lotery_id |
| `lotery_name` | VARCHAR(100) | Nombre del sorteo |
| `product_type` | VARCHAR(20) | `'animales'` o `'triples'` |
| `currency_id` | INTEGER | Nuestro currency_id |
| `betf4_ticket` | INTEGER | ID de ticket de Betf4 (nullable) |
| `betf4_serial` | VARCHAR(50) | Serial de Betf4 (nullable) |
| `bets_count` | INTEGER | Cantidad de números enviados |
| `total_amount` | NUMERIC(12,2) | Monto total enviado |
| `status` | VARCHAR(20) | `'OK'`, `'FAILED'`, `'EMPTY'` |
| `error_message` | TEXT | Mensaje de error (nullable) |
| `sent_at` | TIMESTAMP | `DEFAULT NOW()` |

### `provider_extra_data` en `tickets_provider`

Después de un envío exitoso, el endpoint actualiza el campo `provider_extra_data` de todos los tickets del día/sorteo/moneda donde `provider = 'Betf4'`:

```json
{
    "betf4_ticket": 551950,
    "betf4_serial": "644329757",
    "sent_at": "2026-03-18 17:54:00"
}
```

### Respuesta exitosa de la API Betf4

```json
{"status": "OK", "ticket": 551942, "serial": "774258144"}
```

### Anulación / Reverso

Betf4 **no tiene endpoint de anulación por ticket**. Los métodos `reverse()`, `anull()` y `makeVoid()` retornan `null` con log de error, sin lanzar excepción para no bloquear rollbacks de otros providers.

---

## IjaposProvider (528 líneas)

**Productos:** 26, 34 (CazaLoton), 35 (UneLoton)
**Archivo:** `data/src/Modules/ExternalLoteriesProviderService/Providers/IjaposProvider.php`
**Protocolo:** HTTP POST con query string a `/webSale.jsp`
**Auth:** `providercod` + `poscod` (sin token)

### Endpoints

| Operación | URL | operation |
|---|---|---|
| Venta | `{base_url}/webSale.jsp?operation=0&...` | 0 |
| Anulación | `{base_url}/webSale.jsp?operation=1&...` | 1 |

### Formato de datos (trama)

```
CodigoSorteo|CodigoTipoNumero|Numero|Monto;
```

**Ejemplos:**
- CazaLoton (product 34): `"14|07|25|50.00;"` → Sorteo 14, tipo 07, número 25, monto 50.00
- UneLoton triple (product 35, 3 dígitos): `"14|01|123|20.00;"` → tipo 01
- UneLoton terminal (product 35, 1-2 dígitos): `"14|02|45|10.00;"` → tipo 02

**Múltiples jugadas se concatenan:** `"14|07|25|50.00;14|07|30|25.00;"`

### Tipos de número

| productID | Longitud | tipoNumero | Descripción |
|---|---|---|---|
| 34 | Cualquiera | `07` | CazaLoton |
| 35 | 3 dígitos | `01` | UneLoton triples |
| 35 | 1-2 dígitos | `02` | UneLoton terminales |

### Generación de `tk` (ticket number)

```php
// 10 caracteres exactos: 6 (HHiiss) + 4 (random)
$ticketNumber = date('His') . sprintf('%04d', mt_rand(0, 9999));
// Ejemplo: "1423570847" → 14:23:57 + 0847
```

> **IMPORTANTE:** El `tk` es provider-specific y no causa colisiones entre providers. El `tk` de Ijapos se almacena en `extra_data.serial` y se usa para anulaciones.

### Request de venta

```php
$queryParams = http_build_query([
    'operation' => 0,
    'providercod' => $dbConfig['config']['providercod'],
    'poscod' => $dbConfig['config']['poscod'],
    'tk' => $ticketNumber,
    'coincod' => $this->ticket_currency,  // 1=VES, 2=USD
    'data' => $dataTrama  // Todas las jugadas concatenadas
]);
$url = self::SEND_TICKET_API_URL() . '?' . $queryParams;
$response = $http->post($url);
```

### Respuesta de venta

**Éxito:** `"87654321;14|07|25|50.00;14|07|30|0.00;"` (primer campo = ID del provider, seguido de jugadas con montos ajustados, 0.00 = agotada)

**Error:** Código numérico (0-16):

| Código | Significado |
|---|---|
| 0 | Error de trama de datos |
| 1 | Error general |
| 2 | Lotería cerrada |
| 3 | Lotería no existe |
| 4 | POS desactivado |
| 5 | POS no existe |
| 6 | Punto de venta desactivado |
| 7 | Punto de venta no existe |
| 8 | Proveedor desactivado |
| 9 | Proveedor no existe |
| 10 | POS administrativo no asignado |
| 11 | Acceso restringido por IP |
| 12 | Tipo número cerrado |
| 13 | Error en el monto |
| 14 | Moneda no existe/inactiva |
| 15 | Tipo serie no activa para POS |
| 16 | Tipo serie no existe |

### extra_data almacenado

```json
{
    "id": "87654321",           // ID del provider
    "serial": "1423570847",     // Nuestro tk (usado para anulación)
    "currency": 1,              // Moneda
    "raw_response": "87654321;14|07|25|50.00;14|07|30|0.00;"
}
```

### Mapeo de loterías (lotery_id → código Ijapos)

```php
$this->loteries = [
    // Mapeo dinámico cargado desde la BD/config
    // Ejemplo: 123 => "14", 456 => "15", etc.
];
```

### Anulación

```php
// Búsqueda de ticket: tickets_provider WHERE ticket_id AND provider = 'Ijapos'
// Se usa el 'serial' del extra_data (nuestro tk), NO el 'id' del provider
$queryParams = http_build_query([
    'operation' => 1,
    'data' => $serialNumber,    // ← Nuestro tk
    'providercod' => $providercod,
    'poscod' => $poscod
]);
```

**Códigos de respuesta de anulación:**

| Código | Significado |
|---|---|
| 0 | Ticket anulado exitosamente |
| 1 | Error general |
| 2 | Tiempo agotado para anular |
| 3 | Ticket ya fue pagado |
| 4 | Ticket ya fue cancelado |
| 5 | Ticket no existe |
| 8 | Proveedor desactivado |
| 9 | Proveedor no existe |
| 10 | POS administrativo no asignado |
| 11 | Acceso restringido por IP |

### Formato de monto (FIX aplicado)

```php
// ⚠️ CORRECCIÓN CRÍTICA: La API requiere 2 decimales con punto
$amountFormatted = number_format($amount, 2, '.', '');
// Correcto: "50.00" — Incorrecto: "50" (causaba error de trama, código 0)
```

---

## NewTachiraProvider (409 líneas)

**Producto:** 14
**Archivo:** `data/src/Modules/ExternalLoteriesProviderService/Providers/NewTachiraProvider.php`
**Protocolo:** JSON POST a API 2.0
**Auth:** Token-based (legacy `/authope` endpoint para login, luego token para API 2.0)

### Auth Híbrida

```php
// Login via legacy endpoint
POST {base_url}/authope
Body: { "usuario": "...", "clave": "..." }
→ Response: { "token": "eyJ..." }

// Token cacheado en Redis
$cacheKey = "newtachira-token:{$usuario}";
Cache::put($cacheKey, $token, 86400);  // 1 día TTL
```

### Endpoints

| Operación | URL | Método |
|---|---|---|
| Login | `{base_url}/authope` | POST |
| Venta | `{base_url}/api/jugada` | POST (JSON + token header) |
| Anulación | `{base_url}/api/anular` | POST (JSON + token header) |

### Request de venta

```json
{
    "nroTicket": "PPS1423570847",
    "jugadas": [
        { "sorteo": 1, "numero": "123", "monto": 50.00 }
    ]
}
```

### Generación de ticket number

```php
$ticketNumber = 'PPS' . date('His') . sprintf('%04d', mt_rand(0, 9999));
// Prefijo "PPS" = PremierPluss, para evitar colisiones con otros clientes
```

---

## Otros Providers (Resumen)

### VentaActiva

**Productos:** 5, 61, 62, 64
**Protocolo:** HTTP POST (JSON)
**Particularidad:** Provider con más productos asociados. Envía jugadas individuales por sorteo.

### NewBanklot

**Productos:** 7, 11, 12, 13, 15 (Triple Caracas)
**Protocolo:** HTTP POST
**Nota:** Reemplazó el legacy BanklotProvider.

### MaxPlay

**Productos:** 20, 24, 73
**Protocolo:** JSON POST con token
**Nota:** Reemplazó NewMaticlot para estos product IDs.

### Bomb

**Producto:** 21
**Protocolo:** HTTP POST

### Chance / NewChance

**Productos Chance:** 27, 28
**Productos NewChance:** 90, 91, 92
**Protocolo:** HTTP POST
**Nota:** NewChance es versión actualizada de Chance.

### Smol

**Productos:** 74, 85, 88, 89
**Protocolo:** HTTP POST

### BetM3

**Productos:** 39, 40
**Protocolo:** HTTP POST

### NewMaticlot

**Productos:** 38, 93, 94, 95
**Protocolo:** HTTP POST
**Nota:** Mantiene los product IDs que MaxPlay no absorbió.

### LoteriaAragua

**Producto:** 63
**Protocolo:** HTTP POST

### DefaultProvider (No-op)

**Productos:** Cualquiera no mapeado
**Comportamiento:** Retorna bets sin modificar, no hace ninguna llamada API.

---

## Tabla Resumen de Providers

| Provider | Products | Auth | Formato | Endpoints |
|---|---|---|---|---|
| Betf4 | 2, 17 | api_key+integrator_id+structure_id (headers) | JSON + ZLIB+Base64 | /api/v1/sales_api/new_sales |
| Ijapos | 26, 34, 35 | providercod+poscod | Query string + trama | webSale.jsp |
| NewTachira | 14 | Token (legacy login) | JSON | /api/jugada, /api/anular |
| VentaActiva | 5, 61, 62, 64 | Varía | JSON | Varía |
| NewBanklot | 7, 11, 12, 13, 15 | Varía | POST | Varía |
| MaxPlay | 20, 24, 73 | Token | JSON | Varía |
| Bomb | 21 | Varía | POST | Varía |
| Chance | 27, 28 | Varía | POST | Varía |
| NewChance | 90, 91, 92 | Varía | POST | Varía |
| Smol | 74, 85, 88, 89 | Varía | POST | Varía |
| BetM3 | 39, 40 | Varía | POST | Varía |
| NewMaticlot | 38, 93, 94, 95 | Varía | POST | Varía |
| LoteriaAragua | 63 | Varía | POST | Varía |
| Default | * | N/A | N/A | N/A |
