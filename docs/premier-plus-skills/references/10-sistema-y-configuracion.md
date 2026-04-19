# Sistema y Configuración

## Health Check

```
GET /api-v1/system/live
→ HTTP 200 + { "status": "ok", "time": "2026-02-21T14:23:57" }
```

```
GET /api-v1/system/time
→ Hora del servidor (FrozenTime::now())
```

---

## Docker

### `compose.yaml`

```yaml
services:
  app:        # PHP-FPM + CakePHP
  nginx:      # Proxy reverso
  ofelia:     # Cron jobs (hooks, tareas periódicas)
```

### Contenedor PHP-FPM

- **Runtime:** PHP 8.x-fpm
- **Extensiones:** pgsql, pdo_pgsql, redis, mbstring, intl, gd, zip
- **Volume:** `./data:/var/www/html`
- **Config:** `./data/config/app_local.php` (variables de entorno)

### Ofelia — Cron Jobs

Ejecuta hooks del sistema automáticamente:
```
# PreAward Hook: Se ejecuta antes de cada sorteo
POST /api-v1/system/hook/preaward/{lotery_id}

# Quotas Hook: Actualiza cupos
POST /api-v1/system/hook/set-limits
```

---

## Hooks del Sistema

### PreAwardHook — `POST /api-v1/system/hook/preaward/{lotery_id}`

**Controller:** `System/PreAwardHookController`

```php
// Se ejecuta automáticamente antes de la premiación de un sorteo
// 1. Recibe el lotery_id del sorteo que va a cerrar
// 2. Marca el sorteo como cerrado
// 3. Prepara datos para cálculo de premios
// 4. Puede invalidar cache de sorteos disponibles
```

### QuotasHook — `POST /api-v1/system/hook/set-limits`

**Controller:** `System/QuotasHookController`

```php
// Actualiza cupos/límites de venta dinámicamente
// Permite ajustes en tiempo real durante el día
// Útil para agotar números específicos o modificar límites
```

---

## Amazon S3 — Archivos

### Endpoints

| Ruta | Método | Controller | Descripción |
|---|---|---|---|
| `POST /api-v1/s3/upload-file` | POST | `Files/UploadController` | Subir archivo |
| `POST /api-v1/user/upload-file` | POST | `Files/UploadController` | Subir archivo de usuario |
| `GET /api-v1/user/files` | GET | `Files/GetController` | Listar archivos |
| `PATCH /api-v1/user/update-file` | PATCH | `Files/UpdateController` | Actualizar archivo |
| `PATCH /api-v1/user/delete-file-id` | PATCH | `Files/DeleteByIdController` | Eliminar por ID |
| `PATCH /api-v1/user/delete-file-prefix` | PATCH | `Files/DeleteByPrefixController` | Eliminar por prefijo |

### DTO para archivos

```php
class FilesParams {
    public string $filename;
    public string $content_type;
    public string $s3_key;      // Ruta en S3
    public int $user_id;
}
```

---

## Cache Redis

### Servicio: `App\Services\Cache`

```php
// data/src/Services/Cache.php
class Cache {
    public static function get(string $key): ?string
    public static function put(string $key, string $value, int $ttlSeconds): void
}
```

### Claves conocidas

| Patrón de clave | TTL | Contenido |
|---|---|---|
| `provider_config_{ProviderName}` | 1200s (20 min) | JSON config del provider (encriptado→desencriptado) |
| `newtachira-token:{usuario}` | 86400s (1 día) | Token de autenticación NewTachira |
| `ticket:{user_id}:{audit}` | 180s (3 min) | Ticket completo para idempotencia |
| `sorteos:{scope}` | Variable | Sorteos disponibles por scope |
| `results:{product_id}:{date}` | Variable | Resultados cacheados |

### Invalidación de Cache

```php
// ExternalProvidersController — Al actualizar config de un provider:
Cache::put("provider_config_{$code}", null, 0);  // Invalida cache
// El próximo acceso al provider recargará la config desde BD
```

---

## External Providers CRUD

### Endpoints

| Ruta | Método | Descripción |
|---|---|---|
| `GET /api-v1/external-providers` | GET | Listar (sin config) |
| `POST /api-v1/external-providers` | POST | Crear (con encriptación) |
| `GET /api-v1/external-providers/{id}` | GET | Detalle (sin config) |
| `PUT /api-v1/external-providers/{id}` | PUT | Actualizar (re-encripta) |
| `DELETE /api-v1/external-providers/{id}` | DELETE | Eliminar |

### Migraciones de `external_providers`

- La migración `20250105000001_CreateExternalProviders` solo crea la tabla si no existe.
- Ya no existe migración de población automática desde variables de entorno.
- Ya no existe migración de re-encriptación de la columna `config`.
- Los datos existentes en la tabla se preservan; estos cambios aplican al flujo de migraciones del repositorio.

### Encriptación de Configuración

```php
// ExternalProvidersTable — beforeSave()
// La columna 'config' se encripta con clave dedicada (no Security.salt)
$encryptionKey = Configure::read('ExternalProviders.encryptionKey');
$encrypted = Security::encrypt(json_encode($config), $encryptionKey);

// Al leer:
$decrypted = Security::decrypt($encrypted, $encryptionKey);
$config = json_decode($decrypted, true);
```

> **IMPORTANTE:** La clave de encriptación es independiente de `Security.salt` para portabilidad entre aplicaciones (Api-Taquilla y BackOffice).

---

## Configuración General (`app_local.php`)

```php
return [
    'Datasources' => [
        'default' => [
            'driver' => 'Cake\Database\Driver\Postgres',
            'host' => env('DB_HOST'),
            'database' => env('DB_NAME'),
            'username' => env('DB_USER'),
            'password' => env('DB_PASS'),
        ]
    ],
    'Wallet' => [
        'url' => env('WALLET_API_URL'),
    ],
    'ExternalProviders' => [
        'encryptionKey' => env('EXTERNAL_PROVIDERS_KEY'),
    ],
    'Security' => [
        'salt' => env('SECURITY_SALT'),
    ],
    'Cache' => [
        'default' => [
            'className' => 'Redis',
            'host' => env('REDIS_HOST', '127.0.0.1'),
            'port' => env('REDIS_PORT', 6379),
        ]
    ],
];
```

---

## Geografía

| Ruta | Descripción |
|---|---|
| `GET /api-v1/system/states` | Listar estados de Venezuela |
| `GET /api-v1/system/municipios` | Listar municipios |
| `GET /api-v1/system/ciudades` | Listar ciudades |

---

## Logging

```php
// CakePHP Log — usado extensivamente en providers
Log::write('debug',   "..."); // Depuración, response times
Log::write('info',    "..."); // Transacciones exitosas
Log::write('warning', "..."); // Apuestas parcialmente rechazadas
Log::write('error',   "..."); // Fallos de API, excepciones

// Formato común en providers:
Log::write('info', "{$provider}: ✅ Ticket {$tk} sent. Provider ID: {$id}");
Log::write('error', "{$provider}: API error code {$code} - {$message}");
Log::write('error', "{$provider}: EXCEPTION - {$e->getMessage()}");
```

---

## Otros Endpoints de Sistema

| Ruta | Descripción |
|---|---|
| `GET /api-v1/products` | Listar productos |
| `GET /api-v1/products/available/{currency}` | Productos con moneda disponible |
| `GET /api-v1/rates` | Tasas de cambio actuales |
| `POST /api-v1/currency/update-rates` | Actualizar tasas |
| `GET /api-v1/banks-venezuela` | Bancos de Venezuela |
| `GET /api-v1/messages` | Mensajes del sistema |
| `POST /api-v1/messages/saw/{id}` | Marcar mensaje como leído |
| `GET /api-v1/figures-info` | Info de figuras/animales |
| `GET /api-v1/agencies` | Listar agencias |
| `POST /api-v1/agency-data` | Datos de agencia |
