# Tickets — Ciclo de Vida Completo

## Resumen

Los tickets son la entidad central. Un ticket contiene una o más jugadas (bets) en diferentes sorteos. Su ciclo de vida incluye: creación con validaciones complejas, envío a providers externos, pago de premios, anulación y reversa.

---

## Controller Principal: `Tickets/CreateController.php` (1145 líneas)

### Método `index()` — Flujo Completo de Creación

```
POST /api-v1/tickets (body: { bets: [...], moneda_id?, contact_id?, audit? })
```

**Paso 1: Verificar horario de apertura**
```php
$horarioConfig = HorarioDeAperturaRepository::getConfiguration();
if ($horaApertura > $horaActual) → HTTP 403, code: 'LAT'
```

**Paso 2: Verificar cache de audit (idempotencia)**
```php
if ($audit !== null) {
    $ticket = Cache::get("ticket:{$user_id}:{$audit}");
    if ($ticket !== null) → Retornar ticket cacheado (evita duplicado)
}
```

**Paso 3: Determinar moneda**
```php
$monedaID = $center->moneda_id;  // Default: moneda del centro
if (input['moneda_id'] in [1..10]) $monedaID = input['moneda_id'];
if (!currencyAvailable($user_id, $monedaID)) → HTTP 422, code: 'ERR_CU1'
```

**`currencyAvailable()` — SQL que verifica 3 niveles:**
```sql
SELECT CASE
    WHEN cc.activo = false THEN false   -- Centro
    WHEN gc.activo = false THEN false   -- Grupo
    WHEN ac.activo = false THEN false   -- Agencia
    ELSE true
END
FROM users u
JOIN agencys_currencies ac ON u.agency_id = ac.agency_id
JOIN groups_currencies gc ON u.group_id = gc.group_id
JOIN centers_currencies cc ON u.center_id = cc.center_id
WHERE u.id = {user_id}
```

**Paso 4: Verificar contacto y agencia bloqueada**
```php
if ($contactID) → SELECT * FROM contact_info WHERE id = {contactID}
if (isClient($user_role_id)) $contactID = identity->contact_info_id;

// Verificar bloqueo de agencia
$agency_provider_block = SELECT * FROM provider_agency_blocked
    WHERE provider_agency = {provider_agency} AND id_center = {super_banca}
if (count > 0) → HTTP 422, code: 'ERR_PAB'
```

**Paso 5: Validar jugadas — `_validarJugadasV3()`**
(Ver sección detallada abajo)

**Paso 6: Wallet — débito (solo clientes finales)**
```php
if (isClient($user_role_id)) {
    $walletBalance = WalletService::debit(new TransactionParams(
        userID: $user_id,
        reference: "{$user_id}-{YmdHis.u}",
        currency: $monedaID,
        amount: $amountToDebit,
        amountType: 0  // cash
    ));
    if ($walletBalance->hasError()) → HTTP 400, code: 'WALL_ERR_D1'
}
```

**Paso 7: External Providers**
```php
$ticketSkeleton = new TicketSkeleton($monedaID, $center_id, $group_id, $agency_id, $user_id, $bets);
$externalLoteriesService = new ExternalLoteriesProviderService($ticketSkeleton);
$externalLoteriesService->processTickets();
$input['bets'] = $externalLoteriesService->getBets();  // Solo bets con amount > 0
```

**Paso 8: Ajuste de wallet si montos cambiaron**
```php
if (isClient && $newAmountToDebit !== $amountToDebit) {
    WalletService::rollback(...);    // Reversar débito original
    WalletService::debit(...);       // Nuevo débito con monto correcto
}
```

**Paso 9: Guardar en BD**
```php
$ticket->total_amount  = sum(bets.amount)
$ticket->cant_bets     = count(bets)
$ticket->confirm       = hexdec(substr(sha1(time + user_id), 0, 7))
$ticket->security      = date("YmdHis") . user_id
$ticket->ticket_status_id = 1  // Activo
$ticket->reference     = "{user_id}-{YmdHis.u}"
$Tickets->save($ticket);  // Incluye bets asociados

// Para tripletas: separar números combinados
foreach (betList as $bet) {
    if (str_contains($bet->number, '-')) {  // ej: "15-23-47"
        $numbers = explode("-", $bet->number);
        foreach ($numbers as $key => $number) {
            INSERT INTO combined_bets (bet_id, number, position)
        }
    }
}
```

**Paso 10: Guardar relación ticket↔provider**
```php
foreach ($externalLoteriesService->tickets as $provider => $ticketByProvider) {
    if ($provider == 'Default') continue;
    if ($ticketByProvider['ticket_number'] === null) continue;
    
    $ticket_provider_row->ticket_id = $ticket->id;
    $ticket_provider_row->provider = $provider;           // "Ijapos", "NewTachira", etc.
    $ticket_provider_row->provider_ticket = $ticketByProvider['ticket_number'];
    $ticket_provider_row->provider_extra_data = $ticketByProvider['extra_data'];
    $ticketsProvider->save($ticket_provider_row);
}
```

**Paso 11: Cache para idempotencia y respuesta**
```php
if ($ticket->audit !== null) {
    Cache::put("ticket:{user_id}:{audit}", json_encode($ticketResponse), 180); // 3 min
}
return { ticket: { id, security, moneda_id, contact, audit, total_amount, confirm, number, created, bets }, serverTime }
```

---

## `_validarJugadasV3()` — Motor de Validación (líneas 480-798)

Valida cada jugada y determina el monto final aceptado.

### Fase 1: Preparación
```php
$groupByLoteries = groupBy($input, 'lotery_id');
foreach ($groupByLoteries as $lotery => $numeros) {
    $venta = _calcularVentaV3($user, $bet, $moneda_id);     // Ventas actuales
    $result = _findquotasV3([user, lotery_id, numbers]);      // Cupos disponibles
}
$agencyLimit = agencyLimit($user->agency_id, $moneda_id);     // Límite agencia
$agencyAvailable = $agencyLimit - salesByAgency(...);          // Disponible
```

### Fase 2: Bloqueo Aleatorio
```php
$bloqueoConfig = BloqueoAleatorioRepository::getConfiguration();
$umbral = (int)$bloqueoConfig->umbral;       // Cantidad mínima de jugadas para activar
$porcentaje = (float)$bloqueoConfig->porcentaje;  // % de jugadas a bloquear

foreach ($jugadasByLotery as $lotery_id => $jugadas) {
    if (count($jugadas) >= $umbral) {
        $numerosAAgotar = floor(count($jugadas) * $porcentaje);
        $numerosAAgotarPorLoteria[$lotery_id] = sample($jugadas, $numerosAAgotar);
    }
}
```

### Fase 3: Validación por jugada
```php
foreach ($input as $jugada) {
    // 1. TRIPLETA: máximo de jugadas por ticket
    if ($lotery->type == 'TRIPLETA' && $tripleta_bets >= $tripleta_limits) → rechazar
    
    // 2. TRIPLETA: validar 3 números distintos
    if (type == 'TRIPLETA' && count(array_unique(explode('-', number))) < 3) → rechazar
    
    // 3. POLLA: costo fijo por moneda, validar cantidad de números
    if (type == 'POLLA') {
        $jugada['amount'] = config['ticket_cost'][$moneda_id];
        if (count(explode('-', number)) != config['playable_numbers']) → rechazar
    }
    
    // 4. ANIMALES: validar número, bloqueo aleatorio
    if (type == 'ANIMALES' && isInvalidAnimal(number)) → normalizar
    if (type == 'ANIMALES' && en lista de bloqueo aleatorio) → rechazar
    
    // 5. Verificar sorteo abierto (hora_cierre > now + 5 minutos)
    if (!_verifySorteo(lotery_id)) → rechazar
    
    // 6. Verificar montos mín/máx
    if ($jugada_min > amount) → rechazar
    if (amount > $jugada_max) → amount = $jugada_max
    
    // 7. Verificar cupo por número (max_play)
    if ($playCupo['max_play'] !== null && amount > max_play) → amount = max_play
    
    // 8. Verificar límite de ventas por agencia (limit_sales)
    if ($playCupo['limit_sales'] && $ticketsSold >= limit_sales) → rechazar
    
    // 9. Verificar cupo restante por agencia
    if (amount >= $agencyAvailable) → amount = $agencyAvailable
    
    // 10. CUPOS JERÁRQUICOS (5 niveles, del más amplio al más restrictivo):
    _getCupoJugada(1,  ...)  // Admin
    _getCupoJugada(13, ...)  // Master Center
    _getCupoJugada(3,  ...)  // Center
    _getCupoJugada(4,  ...)  // Group
    _getCupoJugada(5,  ...)  // Agency
}
```

### `_getCupoJugada()` — Cálculo de cupo
```php
function _getCupoJugada($role, $lotery_id, $number, $venta, $cupos, $montoJugada) {
    $cupoJugada = $cupos[$lotery_id][$role][$number] ?? $cupos[$lotery_id][$role]['SN'];
    $cupo_restante = $cupoJugada - $venta - $montoJugada;
    if ($cupo_restante < 0) $montoJugada = $cupoJugada - $venta;
    return $montoJugada;
}
// 'SN' = "Sin Número" = cupo genérico para cualquier número no especificado
```

### `_calcularVentaV3()` — Ventas actuales por número
```sql
SELECT bets.number, SUM(amount) AS admin,
    SUM(CASE WHEN tickets.master_center_id = :mc THEN amount ELSE 0 END) AS master_center,
    SUM(CASE WHEN tickets.center_id = :c THEN amount ELSE 0 END) AS center,
    SUM(CASE WHEN tickets.group_id = :g THEN amount ELSE 0 END) AS grupo,
    SUM(CASE WHEN tickets.agency_id = :a THEN amount ELSE 0 END) AS agency
FROM bets JOIN tickets ON ... WHERE date = today AND status < 5
GROUP BY bets.number
```

---

## Tripletas — Lógica Especial

### Definición
- Números de 6 dígitos divididos en 3 pares: `"15-23-47"`
- Se almacenan en `combined_bets` como registros individuales

### Validaciones adicionales
- `getTripletaBetsPerTicket()`: límite de tripletas por ticket (mínimo entre center, group, agency; default: 2)
- Los 3 números deben ser distintos
- Cupos especiales: `_getTripletaQuota()` con SQL CTE
- Ventas: `_getTripletaSoldByAgency()` cruza combined_bets

### Fechas de tripleta
```php
// Calcula sorteos desde/hasta (11 sorteos) para mostrar en el ticket
SELECT name, lotery_hour FROM loteries WHERE product_new = (result_source)
ORDER BY lotery_hour ASC LIMIT 11
// Resultado: "DESDE: CAZALOTON 9AM 21-02-2026\nHASTA: CAZALOTON 7PM 21-02-2026"
```

---

## Rollback en Caso de Error

```php
try {
    $Tickets->save($ticket);
} catch (Exception $ex) {
    $externalLoteriesService->rollbackRecentTickets();  // Anular en providers
    rollBackTransaccionIfIsFinalClient($role, $user_id, $reference);  // Wallet rollback
}
```

---

## Error Codes de Creación

| Code | Significado | HTTP |
|---|---|---|
| `LAT` | Fuera de horario de apertura | 403 |
| `ERR_CU1` | Moneda no disponible | 422 |
| `ERR_C1` | contact_id no existe | 422 |
| `ERR_PAB` | Agencia bloqueada | 422 |
| `ERR_1` | Bets no es array | 422 |
| `ERR_2` | Bets vacío | 422 |
| `ERR_3` | Todas las jugadas rechazadas | 422 |
| `ERR_4` | Sin jugadas tras providers | 422 |
| `WALL_ERR_D1` | Error de wallet en débito | 400 |
| `WALL_ERR_D2` | Error de wallet en re-débito | 400 |
| `WALL_ERR_ROLLBACK` | Error en rollback de wallet | 400 |
