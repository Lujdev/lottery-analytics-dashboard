# Changelog — PremierPluss Api Taquilla

Todos los cambios notables del proyecto serán documentados en este archivo.

---

## [2026-04-15] — Integración Tote (LotoAnimalito, LottoPantera, Triple Pantera, Terminal Pantera)

### Nuevo Proveedor
- Creado `ToteProvider.php` en `Providers/` siguiendo el patrón Strategy establecido.
- Integración en tiempo real vía webhook `POST /api/webhooks/premier` (Fase 2 de Tote).
- Autenticación por header `X-Webhook-Token`.
- Soporta 4 juegos con 48 `drawSlotId` (12 horarios × 4 productos).

### Registro en Factory
- `Factory::loadProvider()` — instanciación de `ToteProvider`.
- `Factory::anullRecent()` — reverso (no soportado, retorna `null`).
- `Factory::anull()` — anulación (no soportada, retorna `null`).

### Pendiente (TODO)
- Definir los `product_id` internos en `BaseService::getIntegratorByProductID()`.
- Llenar el mapeo `lotery_id → drawSlotId` en `ToteProvider::$loteries`.
- Registrar la configuración del proveedor en la tabla `external_providers` (code: `Tote`, base_url, token).

---

## [2026-03-26] — Betf4 Batch Endpoint + Triple Pirámide de Oro

### Nuevo Endpoint
- Creado `POST /api-v1/external-providers/betf4-batch-send` en `ExternalProvidersController::batchSend()`.
- Reemplaza el enfoque anterior de comando CLI (Ofelia). Invocado por n8n antes del cierre de cada sorteo.
- Query params: `?minutes=7` (default) y `?force_lotery_id=X`.

### Soporte de Triples
- `Betf4Provider` ahora soporta `product_id=17` (Triple Pirámide de Oro) además del `product_id=2` (Zoológico Activo).
- Mapeo de raffle_id para triples: 181→75, 180→79, 182→76, 183→80, 743→77, 741→81.
- Números triples usan padding de 3 dígitos, detectado via `isTripleRaffle()`.
- Mapa de monedas: nuestro `currency_id` → `betf4_currency_id` (VES=1→15, USD=2→2, BRL=3→9, COP=5→12).

### Nueva tabla `betf4_send_log`
- Registra cada envío con: `lotery_id`, `lotery_name`, `product_type`, `currency_id`, `betf4_ticket`, `betf4_serial`, `bets_count`, `total_amount`, `status` (OK/FAILED/EMPTY), `error_message`, `sent_at`.
- Reemplaza la deduplicación anterior basada en Redis. El check `isAlreadySent()` consulta esta tabla.

### Respuesta del Endpoint
- Array plano `details[]` donde cada item tiene campo `product` (`"animales"` o `"triples"`).
- Campos raíz: `success`, `sent`, `failed`, `details`.
- Status posibles por item: `OK`, `FAILED` (con `error`), `SKIPPED` (con `message: "Ya enviado hoy"`).
- HTTP 207 si hay al menos un fallo, HTTP 200 si todos OK.

### `provider_extra_data` en `tickets_provider`
- Después de envío exitoso, actualiza `tickets_provider.provider_extra_data` con `{betf4_ticket, betf4_serial, sent_at}` para todos los tickets del sorteo/moneda del día.

### Limpieza del Provider
- Eliminada propiedad `$productos` (código muerto).
- Comentarios simplificados: eliminadas referencias a `Betf4BatchSendCommand` y prefijos `BATCH:` en logs.

---

## [2026-02-27] — Integración Betf4 Provider (Zoológico Activo)

### Nuevo Provider
- Creado `Betf4Provider.php` para integrar el proveedor **Betf4** con el producto **Zoológico Activo** (`product_id=2` en `loteries.product_new`).
- Registrado en `Factory.php` (`loadProvider`, `anullRecent`, `anull`).
- Mapeado `product_id=2` → `'Betf4'` en `BaseService::getIntegratorByProductID()`.

### Especificaciones de la API Betf4
- **Endpoint de venta:** `POST /api/v1/sales_api/new_sales` — una request por `raffle_id`
- **Autenticación vía headers:** `api_key`, `integrator_id`, `structure_id` (header — valor diferente al del body)
- **Body:** `structure_id`, `station`, `raffle_id`, `currency_id`, `bets` (comprimido)
- **Compresión de jugadas:** JSON → `gzcompress()` (ZLIB) → `base64_encode()`
- **Formato de jugada:** `[{"n": "02", "m": 50.00}]` (n = número del animal con padding, m = monto)
- **Animales especiales:** `"0"` (Delfin), `"00"` (Ballena), resto `str_pad(n, 2, '0', STR_PAD_LEFT)`

### Configuración en `external_providers` (campos `config`)
```json
{
    "api_key": "...",
    "integrator_id": 7,
    "header_structure_id": 2671,
    "structure_id": 2672,
    "station": 2610
}
```
> ⚠️ `header_structure_id` y `structure_id` son **valores distintos**: el primero va en el header HTTP, el segundo en el body JSON.

### Mapeo lotery_id → raffle_id Betf4 (Zoológico Activo)
| lotery_id (nuestro) | raffle_id Betf4 | Hora |
|---|---|---|
| 13 | 108 | 09:00 AM |
| 14 | 109 | 10:00 AM |
| 15 | 110 | 11:00 AM |
| 16 | 111 | 12:00 PM |
| 17 | 112 | 01:00 PM |
| 18 | 113 | 02:00 PM |
| 19 | 114 | 03:00 PM |
| 20 | 115 | 04:00 PM |
| 21 | 116 | 05:00 PM |
| 22 | 117 | 06:00 PM |

### Anulación / Reverso
Betf4 **no dispone** de endpoint de anulación o reverso por ticket individual. Los métodos `reverse()`, `anull()` y `makeVoid()` retornan `null` con log de error, sin bloquear el rollback de otros providers simultáneos.

### Archivos modificados
- `data/src/Modules/ExternalLoteriesProviderService/Providers/Betf4Provider.php` *(nuevo)*
- `data/src/Modules/ExternalLoteriesProviderService/Providers/Factory.php`
- `data/src/Modules/ExternalLoteriesProviderService/BaseService.php`

---

## [2026-02-27] — Limpieza de migraciones de `external_providers`

### Cambiado
- `CreateExternalProviders` ahora crea la tabla `external_providers` solo si no existe.
- Se eliminó el `DROP TABLE IF EXISTS` para evitar reconstrucciones destructivas de la tabla.
- Se eliminaron las migraciones `PopulateExternalProvidersFromEnv` y `ReEncryptExternalProvidersConfig` para evitar población automática y re-encriptación desde migraciones.
- Los datos existentes en `external_providers` se mantienen sin cambios.

### Archivos modificados
- `data/config/Migrations/20250105000001_CreateExternalProviders.php`

### Archivos eliminados
- `data/config/Migrations/20250105000002_PopulateExternalProvidersFromEnv.php`
- `data/config/Migrations/data/config/Migrations/20260123200000_ReEncryptExternalProvidersConfig.php`

---

## [2026-02-24] — Trazabilidad por agencia en logs de jugadas y reversas (NewChance/Ijapos)

### Mejoras de observabilidad
- Se agregó `agency_id` al contexto de logs de **jugadas exitosas** (`sendBets`) en `NewChanceProvider` e `IjaposProvider`.
- Se agregó `agency_id` al contexto de logs de **anulación/reverso exitoso** (`anull`/`makeVoid`) en ambos providers.
- En anulaciones manuales, `agency_id` se resuelve por `ticket_id` con consulta puntual a `tickets` desde el mismo provider.

### Compatibilidad
- No se modificó el contrato de `extra_data` para persistencia de provider.
- Se mantiene el flujo actual de moneda (`currency_id` 1/2/5 según provider) y reverso/anulación.
- No se pasan nuevos parámetros desde `AnullController`/`ReverseController` hacia `Factory::anull`.

### Archivos modificados
- `data/src/Modules/ExternalLoteriesProviderService/Providers/NewChanceProvider.php`
- `data/src/Modules/ExternalLoteriesProviderService/Providers/IjaposProvider.php`

---

## [2026-02-24] — Refactor NewChanceProvider: config ISO, trazabilidad de errores y logs en español

### Corregido
- **Nuevo formato de configuración por moneda ISO:** `NewChanceProvider` ahora usa `config` plano con claves `VES`, `USD`, `COP` (en lugar de `currencies_tokens` con IDs numéricos).  
  Mapeo aplicado: `1 => VES`, `2 => USD`, `5 => COP`.

- **Validación estricta de configuración/token por moneda:** si falta la clave de moneda requerida o la configuración es inválida, el envío/reverso falla de forma controlada y registra el motivo exacto.

- **Compatibilidad de reverso con `extra_data`:** en ventas exitosas de NewChance ahora se agrega `currency_id` al `extra_data` del provider para que `reverse()` pueda resolver correctamente el token de reverso por moneda.

### Mejoras de observabilidad
- **Logs con contexto consistente del provider:** se centralizó logging para que todas las entradas salgan con prefijo de NewChance y contexto estructurado.
- **Mensajes de error claros y en español:** se unificaron errores de configuración, token, ticket, comunicación HTTP y respuesta inválida del proveedor.
- **Sin exposición de token en logs:** se eliminó el registro del token en trazas de envío/reverso.

### Mantenibilidad
- Refactor interno de `sendBets`, `makeVoid`, `reverse` y `anull` para reducir duplicación y hacer explícitos los caminos de error.
- Limpieza general del archivo y eliminación de comentarios inline para mejorar legibilidad operativa.

### Archivo modificado
- `data/src/Modules/ExternalLoteriesProviderService/Providers/NewChanceProvider.php`

---

## [2026-02-24] — Refactor IjaposProvider: limpieza, logs claros y errores en español

### Corregido
- Se reorganizó `sendBets`, `anull`, `reverse` y `makeVoid` para mejorar legibilidad y reducir duplicación.
- Se reforzó la validación de configuración y credenciales del proveedor (`providercod`, `poscod`) antes de enviar o anular tickets.
- Se mejoró el control de respuestas del proveedor (HTTP no exitoso, body vacío, códigos de rechazo y payload inválido).

### Observabilidad
- Se centralizó el formato de logs con contexto consistente del proveedor (`Ijapos [Ijapos] ...`).
- Los mensajes quedaron en español y más entendibles para operación.
- Se removió el uso de `origen_falla`; los logs mantienen contexto técnico directo (ticket, status, códigos, serial, provider_ticket_id).

### Mantenibilidad
- Se retiró código no utilizado (`getConnectionStaticTicket`).
- Se removieron comentarios inline del archivo para dejar una base más limpia.
- Se mantuvo compatibilidad del contrato de respuesta para no romper flujos actuales.

### Archivo modificado
- `data/src/Modules/ExternalLoteriesProviderService/Providers/IjaposProvider.php`

---

## [2026-02-23] — Fix IjaposProvider: mapeo de signos CazaLoton y respuesta vacía

### Corregido
- **Mapeo obligatorio de CazaLoton a códigos de signo Ijapos (`01..38`):** Se corregió el envío para que las jugadas de CazaLoton no salgan con número visual (`0`, `00`, `1`, etc.) sino con el código esperado por Ijapos. Esto corrige de raíz los rechazos de trama cuando se incluyen números como `0` y `00`.

- **Normalización de respuesta parcial de Ijapos a formato interno:** Cuando Ijapos devuelve apuestas agotadas/rechazadas con código de signo, ahora se realiza el mapeo inverso (`01..38` -> `0..36` con `00`) para mantener consistencia y hacer matching correcto contra las apuestas originales.

- **Manejo explícito de body vacío en venta:** Si Ijapos responde HTTP `200` con body vacío, ahora se trata como error de integración (`Empty response body`) en lugar de clasificarlo incorrectamente como código de negocio `0` por conversión implícita.

- **Detección segura de códigos de negocio (0-16):** Se valida primero que la respuesta sea numérica pura antes de evaluar los códigos de error de negocio.

### Mantenibilidad
- Se centralizó el conocimiento de CazaLoton en helpers dedicados (`isCazalotonLottery`, `mapCazalotonNumberToProviderCode`, `mapProviderCodeToCazalotonNumber`) y en estructuras explícitas reutilizables para reducir regresiones futuras.

### Robustez adicional
- **Prevención de 500 en respuestas parciales:** Se amplió el `catch` de venta a `\Throwable` para capturar también errores de tipo en tiempo de ejecución y devolver una respuesta controlada del provider.
- **Normalización defensiva de códigos:** Se endureció el parseo de la respuesta parcial (`trim` por campo) y se agregó tolerancia a códigos de signo con y sin cero a la izquierda (`7` y `07`).
- **Entrada flexible para CazaLoton:** El número visual ahora se normaliza de forma centralizada (por ejemplo, `01` se interpreta como `1`, `00` se preserva) antes de mapear a código Ijapos.
- **Fix de tipado en mapeo inverso:** Se forzó retorno `string` en `mapProviderCodeToCazalotonNumber` para evitar `TypeError` cuando `array_flip` devuelve valores numéricos como enteros.

### Archivo modificado
- `data/src/Modules/ExternalLoteriesProviderService/Providers/IjaposProvider.php`

---

## [2026-02-21] — Fix IjaposProvider: Monto decimal y tk de 10 caracteres

### Corregido
- **Formato de monto en trama de datos:** El monto se enviaba como entero (`20`) en lugar de decimal con punto (`20.00`). La API Ijapos requiere formato decimal explícito, de lo contrario retorna error código 0 ("Error en trama de datos"). Se corrigió usando `number_format($amount, 2, '.', '')`.

- **Longitud del parámetro `tk`:** El número de transacción (`tk`) se generaba con `user_id + timestamp` sin límite de longitud, produciendo 13+ caracteres. La API Ijapos tiene un límite estricto de **máximo 10 caracteres**. Se reemplazó la estrategia por `date('His') . sprintf('%04d', mt_rand(0, 9999))` (misma estrategia que NewTachiraProvider, adaptada a 10 dígitos numéricos).

### Archivos modificados
- `data/src/Modules/ExternalLoteriesProviderService/Providers/IjaposProvider.php`

### Error original
```
Ijapos: API error code 0
URL: ...&data=208|07|5|20;208|07|7|20;...
```

### Corrección aplicada
```diff
- $formattedBets[] = "{$sorteoCode}|{$tipoNumero}|{$number}|{$amount};";
+ $amountFormatted = number_format($amount, 2, '.', '');
+ $formattedBets[] = "{$sorteoCode}|{$tipoNumero}|{$number}|{$amountFormatted};";
```

```diff
- $ticketNumber = $this->ticketSkeleton->user_id . ltrim((string) $unix, '1');
+ $ticketNumber = date('His') . sprintf('%04d', mt_rand(0, 9999));
```
