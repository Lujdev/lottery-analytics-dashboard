# Anulaciones y Reversos — Flujos Completos

## Tipos de Cancelación

| Tipo | Controller | Ruta | Descripción |
|---|---|---|---|
| **Anulación estándar** | `Tickets/AnullController` | `POST /api-v1/tickets/{id}/anull` | Con límite de tiempo |
| **Anulación ilimitada** | `Tickets/AnullUnlimitedController` | `POST /api-v1/tickets/{id}/unlimited-anull` | Sin límite de tiempo |
| **Anulación por auditoría** | `Tickets/AnullByAuditController` | `POST /api-v1/tickets/audit/{audit}/anull` | Busca por campo audit |
| **Anulación SUCA** | `Tickets/AnullSucaController` | `DELETE /api-v1/tickets/suca-anull/{id}/anull` | Delete HTTP method |
| **Reversa** | `Tickets/ReverseController` | `POST /api-v1/tickets/{id}/reverse` | Reversa del provider, mantiene nuestro ticket |

---

## Flujo de Anulación Estándar

```
POST /api-v1/tickets/{id}/anull
    ↓
1. Buscar ticket en BD: tickets WHERE id = {id}
2. Verificar que el ticket pertenece al usuario/agencia
3. Verificar estado: ticket_status_id debe ser < 5 (activo)
4. Verificar tiempo: hora actual < hora_cierre + margen
    ↓
5. Buscar relación en tickets_provider WHERE ticket_id = {id}
6. Para cada provider asociado:
   Factory::anull($providerName, $ticketID, $currencyID)
    ↓
7. Provider ejecuta anulación en API externa
    ↓
8. Si es cliente final: Wallet::rollback(reference)
9. Actualizar ticket_status_id = 5 (Anulado)
```

---

## Mecanismo de Anulación por Provider

### Flujo dentro del Provider

```php
// Factory llama:
ProviderClass::anull($ticketID, $currencyID)
    ↓
// El provider busca su ticket en tickets_provider
$ticket_by_provider = connection->find()
    ->where(['ticket_id' => $ticketID, 'provider' => PROVIDER_NAME])
    ->first();
    ↓
// Decodifica extra_data para obtener el serial/ID
$extraData = json_decode($ticket_by_provider['provider_extra_data'], true);
    ↓
// Ejecuta la anulación en la API del provider
makeVoid($serial, $currencyID)
```

### IjaposProvider — Anulación

```php
// anull($ticketID, $currencyID)
$extraData = json_decode($provider_extra_data, true);
$serialNumber = $extraData['serial'];  // ← Nuestro tk (NO el ID del provider)

// makeVoid($serialNumber, $currencyID)
$queryParams = http_build_query([
    'operation' => 1,          // 1 = anulación
    'data' => $serialNumber,   // El serial/tk que enviamos al crear
    'providercod' => $config['providercod'],
    'poscod' => $config['poscod']
]);
$url = self::VOID_TICKET_API_URL() . '?' . $queryParams;
$response = $http->post($url);
```

> **⚠️ IMPORTANTE:** Para Ijapos, la anulación usa el campo `serial` del `extra_data` (que es nuestro `tk` generado), NO el `id` retornado por Ijapos.

### Respuesta de anulación (Ijapos)

```php
$responseCodes = [
    '0' => 'Ticket anulado exitosamente',
    '1' => 'Error general',
    '2' => 'Tiempo agotado para anular',
    '3' => 'Ticket ya fue pagado',
    '4' => 'Ticket ya fue cancelado',
    '5' => 'Ticket no existe',
    '8' => 'Proveedor desactivado',
    '9' => 'Proveedor no existe',
    '10' => 'POS administrativo no asignado',
    '11' => 'Acceso restringido por IP',
];

// Éxito: código '0'
return ['success' => true, 'status' => 200, 'code' => '0', 'message' => '...', 'body' => '0'];

// Error: cualquier otro código
return ['success' => false, 'status' => 200, 'code' => '2', 'message' => 'Tiempo agotado', 'body' => '2'];
```

---

## Reversa (Rollback Inmediato)

La reversa ocurre cuando hay un error **después** de que el provider aceptó la venta (ej: fallo al guardar en BD).

```php
// BaseService::rollbackRecentTickets()
foreach ($this->tickets as $integrator => $ticket) {
    Factory::anullRecent($integrator, $ticket);
}

// Factory::anullRecent() llama al método estático reverse() del provider
IjaposProvider::reverse($ticket);

// IjaposProvider::reverse($ticket)
$extraData = json_decode($ticket['extra_data'], true);
$serialNumber = $extraData['serial'] ?? $ticket['ticket_number'];
$currency = $extraData['currency'] ?? 1;
return self::makeVoid($serialNumber, $currency);  // Misma lógica que anull
```

### Diferencia entre reverse() y anull()

| Aspecto | `reverse()` | `anull()` |
|---|---|---|
| **Cuándo** | Rollback inmediato durante creación | Anulación posterior por el usuario |
| **Input** | Datos en memoria (`$ticket` array) | `$ticketID` (busca en BD) |
| **BD** | Ticket aún no guardado | Ticket ya guardado en `tickets_provider` |
| **Wallet** | También se hace rollback | También se hace rollback (si cliente) |

---

## Rollback de Wallet

```php
// CreateController::rollBackTransaccionIfIsFinalClient()
if ($this->isClient($user_role_id)) {
    $walletBalance = WalletService::rollback(new TransactionParams(
        userID: $user_id,
        reference: $reference,   // La misma referencia del débito original
    ));
    if ($walletBalance->hasError()) {
        // Log silencioso — TODO: implementar alertas
    }
}
```

> **Nota:** `isClient()` actualmente retorna `false` siempre (comentado). Cuando se habilite, el flujo de wallet estará activo.

---

## Estructura de `extra_data` por Provider

### Ijapos
```json
{
    "id": "87654321",           // ID asignado por Ijapos
    "serial": "1423570847",     // Nuestro tk (USADO PARA ANULACIÓN)
    "currency": 1,
    "raw_response": "87654321;14|07|25|50.00;"
}
```

### NewTachira
```json
{
    "id": "TACH-00123",
    "serial": "PPS1423570847",
    "token_used": "eyJ...",
    "raw_response": "{...}"
}
```

---

## Estados de Ticket

| ticket_status_id | Estado | Descripción |
|---|---|---|
| 1 | Activo | Ticket creado exitosamente |
| 2 | Pagado | Ticket ganador cobrado |
| 3 | Parcialmente pagado | Parte del premio cobrado |
| 4 | Expirado | Tiempo de cobro expirado |
| 5 | Anulado | Ticket cancelado |
| 6 | Reversado | Ticket reversado en provider |

> **Filtro clave:** `ticket_status_id < 5` = ticket válido para venta/cupos
