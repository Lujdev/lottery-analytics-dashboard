# Usuarios y Autenticación

## Resumen

La autenticación usa **JWT** via el plugin `Authentication` de CakePHP. La jerarquía organizacional (Admin → Master Center → Center → Group → Agency → User) controla permisos y filtros de datos.

---

## AppController Base (125 líneas)

```php
// data/src/Controller/AppController.php
class AppController extends Controller {
    public function initialize(): void {
        $this->loadComponent('RequestHandler', ['enableBeforeRedirect' => false]);
        $this->loadComponent('Authentication.Authentication', [
            'requireIdentity' => true  // TODAS las rutas requieren auth por defecto
        ]);
    }
}
```

### Métodos standard de respuesta

| Método | HTTP | Uso |
|---|---|---|
| `responseJson($json, $code)` | Cualquiera | JSON genérico |
| `responseWithSuccess($data, $additional, $meta)` | 200 | `{ data: {...}, meta: {...} }` |
| `responseWithErrors($entity, $message)` | 400 | `{ errors: {...}, messages: {...}, message: "..." }` |
| `responseNotImplemented()` | 501 | Sin body |
| `responseOk()` | 201 | Sin body |

---

## Autenticación JWT

### Flow de Login

```
POST /api-v1/users/token/{idHardware}
    ↓
UsersController → Verificar credenciales → Generar JWT
    ↓
Response: { token: "eyJ...", user: {...} }
```

### Verificación en cada request

```
Request con header: Authorization: Bearer eyJ...
    ↓
AuthenticationMiddleware → Decodificar JWT → Inyectar identity
    ↓
Controller accede: $this->request->getAttribute('identity')
```

### Campos del Identity

```php
$identity = $this->request->getAttribute('identity');

$identity->id;                 // User ID
$identity->role_id;            // 1=Admin, 3=Center, 4=Group, 5=Agency, 11=Cliente, 13=Master Center
$identity->center_id;          // Centro al que pertenece
$identity->group_id;           // Grupo al que pertenece
$identity->agency_id;          // Agencia a la que pertenece
$identity->master_center_id;   // Master center
$identity->contact_info_id;    // Info de contacto (para clientes finales)
```

---

## Jerarquía Organizacional

```
Admin (role_id = 1)
  └── Master Center (role_id = 13)
        └── Center (role_id = 3)
              └── Group (role_id = 4)
                    └── Agency (role_id = 5)
                          └── User/Taquillero (role_id = 6)
                          └── Cliente Final (role_id = 11)
```

### Uso en cupos jerárquicos

Los cupos se aplican en cascada, del más amplio al más restrictivo:

```php
// CreateController::_validarJugadasV3()
$montoJugada = _getCupoJugada(1,  ...);  // Admin (más amplio)
$montoJugada = _getCupoJugada(13, ...);  // Master Center
$montoJugada = _getCupoJugada(3,  ...);  // Center
$montoJugada = _getCupoJugada(4,  ...);  // Group
$montoJugada = _getCupoJugada(5,  ...);  // Agency (más restrictivo)
```

---

## Endpoints de Usuarios

### Consulta/Autenticación

| Ruta | Controller | Descripción |
|---|---|---|
| `POST /api-v1/users/token/{hardware}` | `UsersController` | Login + JWT |
| `GET /api-v1/users/me` | `Users/FindByUsernameController` | Info del usuario autenticado |
| `PUT /api-v1/users/me/update` | `Users/UpdateController` | Actualizar perfil |
| `GET /api-v1/users/currencies` | `Users/GetUserCurrencies` | Monedas habilitadas |
| `PATCH /api-v1/user/password-change` | `Users/PasswordChangeController` | Cambiar contraseña |

### Contacto / SENIAT

| Ruta | Controller | Descripción |
|---|---|---|
| `GET /api-v1/users/contact/{cedula}` | `Users/ContactController` | Buscar contacto por cédula |
| `GET /api-v1/users/contact-info/{cedula}` | `Users/ContactInfoController` | Info detallada de contacto |
| `PATCH /api-v1/users/seniat-info` | `Seniat/UpdateSeniatInfo` | Actualizar datos SENIAT |
| `POST /api-v1/users/seniat-info` | `Seniat/CreateSeniatInfo` | Crear datos SENIAT |

### Cuentas bancarias

| Ruta | Método | Descripción |
|---|---|---|
| `GET /api-v1/user/accounts` | GET | Listar cuentas |
| `POST /api-v1/user/add-account` | POST | Agregar cuenta |
| `PATCH /api-v1/user/update-account` | PATCH | Actualizar cuenta |
| `PATCH /api-v1/user/delete-account` | PATCH | Eliminar cuenta |

### DTOs relacionados

```php
// ContactInfoParams
class ContactInfoParams {
    public string $cedula;
    public string $nombre;
    public string $telefono;
    // ... más campos
}

// SeniatInfoParams
class SeniatInfoParams {
    public string $rif;
    public string $razon_social;
    // ... más campos
}

// BankAccountByUser
class BankAccountByUser {
    public int $user_id;
    public string $bank_code;
    public string $account_number;
    public string $account_type;
}
```

---

## Middleware Stack Completo

```
Application::middleware()

1. ErrorHandlerMiddleware          # CakePHP: captura excepciones
2. AssetMiddleware                 # CakePHP: archivos estáticos
3. RoutingMiddleware               # CakePHP: resuelve ruta → controller
4. BodyParserMiddleware            # CakePHP: parsea JSON body → request data
5. RequestMiddleware               # Custom: logging y validación
6. AuthenticationMiddleware        # JWT: verifica token, inyecta identity
7. PersistenceOrmFailedMiddleware  # Custom: captura errores ORM
```

### `UnauthenticatedHandler`

```php
// Cuando AuthenticationMiddleware detecta token inválido/ausente
// Se retorna HTTP 401 con:
{ "message": "Unauthenticated" }
```

---

## Rutas sin autenticación

Definidas en el scope `/` de `routes.php` (sin middleware de auth):

```php
$routes->scope('/', function (RouteBuilder $builder) {
    // POST /tickets/add-v3 → Legacy, sin auth
    // POST /tickets/add-v4 → Legacy, sin auth
    // GET /validate-email/{token} → Validación de email
});
```

> **⚠️ IMPORTANTE:** Las rutas legacy `/tickets/add-v3` y `/tickets/add-v4` están fuera del scope autenticado. Considerar deprecarlas.

---

## Header especial: `Provider-Agency`

```php
// Usado en CreateController para determinar la agencia del proveedor
$provider_agency = $this->request->getHeaderLine('Provider-Agency');
// Se usa para verificar bloqueos en provider_agency_blocked
```
