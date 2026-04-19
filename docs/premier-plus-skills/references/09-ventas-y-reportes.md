# Ventas y Reportes

## Resumen

El sistema de reportes permite consultar ventas consolidadas, detalladas y por tripletas. Los endpoints están en `SalesController.php` y `Sales/` controllers. Los reportes se filtran por jerarquía organizacional.

---

## Endpoints de Ventas

| Ruta | Controller | Descripción |
|---|---|---|
| `GET /api-v1/sales/consolidado` | `SalesController::consolidado` | Resumen por agencia |
| `GET /api-v1/sales/detallado` | `SalesController::detallado` | Detalle por ticket/jugada |
| `GET /api-v1/sales/tripleta` | `SalesController::tripleta` | Ventas de tripletas |
| `GET /api-v1/sales/taq` | `Sales/ListByTaquilla` | Ventas por taquilla |
| `GET /api-v1/sales/agencies` | `Sales/ListByAgency` | Ventas por agencia |

---

## Control de Ventas por Agencia

### Límite diario por agencia y moneda

```php
// CreateController::agencyLimit($agency_id, $currency_id)
SELECT amount FROM agency_sale_by_currencies
WHERE agency_id = :agency_id AND currency_id = :currency_id
```

### Ventas actuales de la agencia

```php
// CreateController::salesByAgency($agency_id, $currency_id, $date)
SELECT SUM(amount) AS sales
FROM bets
JOIN tickets ON (tickets.created::date = bets.created::date AND tickets.id = bets.ticket_id)
WHERE tickets.created::date = :hoy
  AND tickets.ticket_status_id < 5      -- Solo tickets activos
  AND tickets.agency_id = :agency_id
  AND tickets.moneda_id = :currency_id
```

### Verificación durante creación de ticket

```php
$agencyLimit = $this->agencyLimit($user->agency_id, $moneda_id);
$salesByAgency = $this->salesByAgency($user->agency_id, $moneda_id, date('Y-m-d'));
$agencyAvailable = $agencyLimit - $salesByAgency;

// Si el monto de la jugada excede lo disponible:
if ($montoJugada >= $agencyAvailable) {
    $montoJugada = $agencyAvailable;  // Se reduce al monto disponible
}
if ($agencyAvailable <= 0) → rechazar jugada
```

---

## Ventas por Número (`_calcularVentaV3`)

Calcula las ventas actuales para números específicos, desglosadas por nivel jerárquico:

```sql
SELECT bets.number AS number,
    SUM(amount) AS admin,
    SUM(CASE WHEN tickets.master_center_id = :mc THEN amount ELSE 0 END) AS master_center,
    SUM(CASE WHEN tickets.center_id = :c THEN amount ELSE 0 END) AS center,
    SUM(CASE WHEN tickets.group_id = :g THEN amount ELSE 0 END) AS grupo,
    SUM(CASE WHEN tickets.agency_id = :a THEN amount ELSE 0 END) AS agency
FROM bets
JOIN tickets ON (tickets.created::date = bets.created::date AND tickets.id = bets.ticket_id)
WHERE tickets.created::date = :hoy
  AND bets.created::date = :hoy
  AND tickets.ticket_status_id < 5
  AND tickets.moneda_id = {moneda_id}
  AND bets.lotery_id = :lotery_id
  AND bets.number IN (:numbers)
GROUP BY bets.number
```

**Resultado:** Array de ventas por número, cada una con 5 niveles:
```php
[
    ['number' => '25', 'admin' => 50000, 'master_center' => 30000, 'center' => 20000, 'grupo' => 10000, 'agency' => 5000],
    ['number' => '30', 'admin' => 40000, 'master_center' => 25000, 'center' => 15000, 'grupo' => 8000, 'agency' => 3000],
]
```

---

## Ventas de Tripletas por Agencia

```php
// CreateController::_getTripletaSoldByAgency()
WITH TT AS (
    SELECT T.id, COUNT(CB.id) AS numeros_count
    FROM tickets T
    INNER JOIN bets B ON B.ticket_id = T.id AND B.created >= :fecha
    INNER JOIN combined_bets CB ON CB.bet_id = B.id
        AND CB.created >= :fecha
        AND CB.number IN ({numeros_individuales})
    WHERE T.created >= :fecha
      AND T.agency_id = :agency_id
      AND T.moneda_id = :moneda_id
      AND B.lotery_id = :lotery_id
    GROUP BY T.id, B.id
)
SELECT COUNT(TT.id) AS vendidos FROM TT
WHERE TT.numeros_count >= :count_numeros_tripleta
```

> **Nota:** Las tripletas se cuentan como "vendidas" solo si todos los números individuales coinciden (`numeros_count >= count`).

---

## Ventas de Tickets Individuales por Agencia

```php
// CreateController::_getTicketSoldByAgency()
SELECT count(DISTINCT T.id) AS vendidos
FROM tickets T
JOIN bets B ON (date(B.created) = :fecha AND B.ticket_id = T.id
    AND B.lotery_id = :lotery_id AND B.number = :numero)
WHERE date(T.created) >= :fecha
  AND T.ticket_status_id < 5
  AND T.agency_id = :agency_id
  AND T.moneda_id = :moneda_id
```

---

## Apuestas Sospechosas

```php
// CreateController::hasSuspiciousBets($agencyID, $bets, $threshold)
$amountOfBetsToBeSuspicious = 15;  // Más de 15 jugadas por lotería = sospechoso

// Consulta en tablas particionadas (tickets_YYYYMMDD, bets_YYYYMMDD)
SELECT count(1) AS jugadas_sospechosas FROM (
    SELECT t.id, count(t.id) AS numero_apuestas
    FROM tickets_{YYYYMMDD} t
    JOIN bets_{YYYYMMDD} b ON b.ticket_id = t.id
    WHERE t.agency_id = {agencyID}
    GROUP BY b.ticket_id, t.id, lotery_id
) tb WHERE tb.numero_apuestas > {amountOfBetsToBeSuspicious}

// Si historial + nuevas sospechosas >= threshold → rechazar ticket completo
if ($previusSuspiciosBets + $suspiciosBetsToCreate >= $threshold) → true
```

---

## Tablas de Límites

| Tabla | Campos clave | Uso |
|---|---|---|
| `agency_sale_by_currencies` | agency_id, currency_id, amount | Límite diario por agencia |
| `center_sale_by_currencies` | center_id, currency_id, amount, tripleta_amount | Límite por centro |
| `group_sale_by_currencies` | group_id, currency_id, amount, tripleta_amount | Límite por grupo |
| `quotas` | entity, role_id, lotery_id, number, moneda_id, amount, limit_sales, max_play, time_init, ttl | Cupos por número |
| `setups` | config JSON | quota_min, quota_max globales por moneda |

---

## Particionamiento de Tablas

Las tablas de alto volumen usan particiones diarias:

```
tickets       → tickets_20260221, tickets_20260222, ...
bets          → bets_20260221, bets_20260222, ...
combined_bets → (sin partición)
```

La consulta de apuestas sospechosas usa directamente las tablas particionadas:
```php
$dateFormatted = date_format(new \DateTimeImmutable(), 'Ymd');
"FROM tickets_{$dateFormatted} t JOIN bets_{$dateFormatted} b ..."
```
