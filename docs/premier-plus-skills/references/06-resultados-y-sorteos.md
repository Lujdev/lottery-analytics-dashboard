# Resultados y Sorteos

## Resumen

El sistema gestiona dos aspectos: **sorteos disponibles** (qué loterías están abiertas para venta) y **resultados** (números ganadores tras el cierre). El controller principal es `LoteriesController.php` (707 líneas).

---

## Sorteos Disponibles

### Endpoint: `GET /api-v1/loteries`

```
GET /api-v1/loteries?moneda_id={1|2}
```

**Controller:** `LoteriesController::getSorteosV3()`

### Lógica de Consulta

```php
// 1. Determinar día de la semana
$day = strtolower(date('l', strtotime('today')));  // "monday", "tuesday", etc.

// 2. Consulta principal: loterías habilitadas para hoy
SELECT l.id, l.name, l.lotery_hour, l.product_new, l.type,
       np.name AS product_name, np.config
FROM loteries l
JOIN new_products np ON l.product_new = np.id
WHERE l.enable = 1
  AND l.{$day} = 1           -- Habilitada para este día de la semana
  AND l.lotery_hour > :hora   -- Aún no ha cerrado
  AND l.moneda_id = :moneda_id
  AND EXISTS (                 -- Moneda habilitada en la jerarquía:
      SELECT 1 FROM centers_currencies cc WHERE cc.center_id = :center AND cc.currency_id = :moneda AND cc.activo
      AND EXISTS (SELECT 1 FROM groups_currencies gc WHERE gc.group_id = :group AND gc.currency_id = :moneda AND gc.activo)
      AND EXISTS (SELECT 1 FROM agencys_currencies ac WHERE ac.agency_id = :agency AND ac.currency_id = :moneda AND ac.activo)
  )
ORDER BY l.lotery_hour ASC
```

### Campos de la tabla `loteries`

| Campo | Tipo | Descripción |
|---|---|---|
| `id` | int | PK |
| `name` | varchar | Nombre del sorteo (ej: "CazaLoton 9AM") |
| `lotery_hour` | time | Hora de cierre |
| `product_new` | int | FK a `new_products.id` |
| `type` | varchar | TRIPLETA, POLLA, ANIMALES, null |
| `enable` | bool | Habilitado/deshabilitado |
| `dia_lun..dia_dom` | bool | Días habilitados |
| `moneda_id` | int | Moneda asociada |

### `_verifySorteo($id)` en CreateController

```php
// Verifica que un sorteo aún acepta jugadas (con 5 min de margen)
$hora = date("H:i:s", strtotime("+5 minutes"));
$Loterie = Loteries->find()->where([
    'id' => $id,
    'lotery_hour >' => $hora,  // Cierre debe ser después de ahora + 5 min
    'enable' => 1
]);
return !empty($Loterie->all()->count());
```

---

## Resultados

### Endpoints

| Ruta | Controller | Descripción |
|---|---|---|
| `GET /api-v1/results` | `LoteriesController::results2()` | Resultados generales |
| `GET /api-v1/results/{product_id}/string` | `Results/GetAllFromProductInString` | Resultados de un producto como string |

### Flujo de Resultados con Servicios Nativos

Algunos productos tienen servicios nativos que consultan resultados directamente:

| Servicio | Archivo | Productos |
|---|---|---|
| `ChanceService` | `Services/Providers/ChanceService.php` | Chance (27, 28) |
| `InmejorableService` | `Services/Providers/InmejorableService.php` | Inmejorable |
| `MMSGOService` | `Services/Providers/MMSGOService.php` | MMSGO |
| `TachiraService` | `Services/Providers/TachiraService.php` | Tachira (14) |

### Cache de Resultados

```php
// Resultados se cachean en Redis
$cacheKey = "results:{$product_id}:{$date}";
$cached = Cache::get($cacheKey);
if ($cached) return json_decode($cached, true);

// Si no hay cache, consultar servicios nativos o BD
$results = $this->fetchResults($product_id, $date);
Cache::put($cacheKey, json_encode($results), $ttl);
```

---

## Hooks del Sistema

### PreAwardHook — `POST /api-v1/system/hook/preaward/{lotery_id}`

Este hook se ejecuta automáticamente (via Ofelia/cron) antes de la premiación:

```php
// System/PreAwardHookController
// 1. Marca el sorteo como cerrado
// 2. Prepara datos para el cálculo de premios
// 3. Puede invalidar cache de sorteos
```

### QuotasHook — `POST /api-v1/system/hook/set-limits`

```php
// System/QuotasHookController
// Actualiza cupos/límites de venta dinámicamente
// Usado para ajustes en tiempo real durante el día
```

---

## Estructura de `new_products`

```json
// Columna config (JSON) de new_products
{
    "result_source": "native|external",  // De dónde se obtienen resultados
    "ticket_cost": { "1": 1000, "2": 1.00 },  // Costo fijo por moneda (para POLLA)
    "playable_numbers": 6,                      // Cant. números (para POLLA)
    "min_bet": { "1": 100, "2": 0.10 },
    "max_bet": { "1": 50000, "2": 50.00 }
}
```
