# Wallet y Transacciones

## Resumen

El servicio Wallet gestiona el saldo de usuarios tipo "cliente final" a través de una **API HTTP externa**. El archivo principal es `Services/Wallet/Service.php` (290 líneas).

---

## Clase `WalletService` — Métodos Estáticos

### `balance(TransactionParams $param): BalanceResponse`

```php
// Consulta saldo del usuario
POST {Wallet.url}/Balance
Body: { "userID": 123, "currency": "VES" }

// Respuesta exitosa:
BalanceResponse {
    transactionID: null,
    cash: CurrencyBalance { VES: 5000.00, USD: 25.00 },
    bonus: CurrencyBalance { VES: 100.00, USD: 0.00 }
}
```

### `debit(TransactionParams $param): BalanceResponse`

```php
POST {Wallet.url}/Debit
Body: {
    "userID": 123,
    "reference": "123-20260221142357123456",  // "{user_id}-{YmdHis.u}"
    "currency": "VES",                         // getCurrencyISO()
    "amount": 500.00,
    "amountType": 0                             // 0 = cash
}

// Respuesta exitosa: BalanceResponse con saldo actualizado
// Error: BalanceResponse->addError("Insufficient funds")
```

### `credit(TransactionParams $param): BalanceResponse`

```php
POST {Wallet.url}/Credit
Body: {
    "userID": 123,
    "reference": "PAGO-{ticket_id}",
    "currency": "VES",
    "amount": 10000.00,
    "amountType": 0
}
```

### `rollback(TransactionParams $param): BalanceResponse`

```php
POST {Wallet.url}/RollbackBet
Body: {
    "userID": 123,
    "reference": "123-20260221142357123456"  // Misma referencia del débito
}
// La referencia es la clave para identificar qué transacción reversar
```

### `transactionsList(TransactionListParams $param): TransactionResponse`

```php
POST {Wallet.url}/Transactions
Body: {
    "userID": 123,
    "since": "2026-02-01",
    "until": "2026-02-21",
    "currency": "VES",
    "PageNumber": 1,
    "PageSize": 50
}
```

---

## DTOs del Wallet

### `TransactionParams`

```php
// data/src/DTO/TransactionParams.php (23 líneas)
class TransactionParams {
    public int|null $userID;
    public string|null $reference;    // Formato: "{user_id}-{YmdHis.u}"
    public int|null $currency;        // 1=VES, 2=USD (ID interno)
    public float|null $amount;
    public int|null $amountType;      // 0=cash

    public function getCurrencyISO(): string {
        return MonedasTable::MONEDAS[$this->currency]['sigla'];
        // 1 → 'VES', 2 → 'USD'
    }
}
```

### `BalanceResponse`

```php
// data/src/DTO/BalanceResponse.php (32 líneas)
class BalanceResponse {
    public int|null $transactionID;
    public CurrencyBalance|null $cash;   // Saldo efectivo
    public CurrencyBalance|null $bonus;  // Saldo bonificado
    private $errors = [];

    public function addError(string $message, $exception = null): void
    public function getErrors(): array
    public function hasError(): bool    // count($errors) > 0
}
```

### Otros DTOs

| DTO | Campos | Uso |
|---|---|---|
| `CurrencyBalance` | VES, USD | Valores de saldo por moneda |
| `TransactionListParams` | since, until, currency, PageNumber, PageSize | Filtros de listado |
| `TransactionList` | Detalle individual | Una transacción |
| `TransactionResponse` | items[], total, page | Wrapper de listado |

---

## Monedas

```php
// MonedasTable::MONEDAS
[
    1 => ['nombre' => 'Bolívares', 'sigla' => 'VES'],
    2 => ['nombre' => 'Dólares',   'sigla' => 'USD'],
]
```

---

## Configuración

La URL base del wallet está en `data/config/app_local.php`:

```php
'Wallet' => [
    'url' => env('WALLET_API_URL', 'https://wallet-api.example.com/api'),
],
```

Acceso: `Configure::read('Wallet.url')`

---

## Flujo de Wallet en Creación de Ticket

```
CreateController::index()
    ↓
if (isClient($role_id)):            // (Actualmente deshabilitado: return false)
    ↓
    WalletService::debit(...)        // Débito por el monto total de las jugadas
    if hasError → HTTP 400 + rollback
    ↓
    processTickets()                 // Enviar a providers
    ↓
    if (monto cambió):               // Providers pueden reducir montos (agotados)
        WalletService::rollback(...) // Reversar débito original
        WalletService::debit(...)    // Nuevo débito con monto correcto
    ↓
    save ticket
    ↓
    if (error al guardar):
        WalletService::rollback(...) // Reversar todo
```

---

## Rutas de Wallet/Financiero

```
GET  /api-v1/taquilla-final/user-balance         → Balance
GET  /api-v1/taquilla-final/listTransactions      → Listado
POST /api-v1/intentions                           → Crear intención de retiro/depósito
GET  /api-v1/user/WithdrawalAndDepositIntentions  → Ver intenciones
```

---

## Error Handling del Wallet

```php
// Si la API no responde o retorna error HTTP
try {
    $response = $http->post($url, json_encode($body), ['type' => 'json']);
    if ($response->getStatusCode() !== 200) {
        $balanceResponse->addError("Wallet API error: {$response->getStatusCode()}");
    }
    // Parse JSON body...
} catch (\Exception $e) {
    $balanceResponse->addError("Wallet connection error", $e);
}
```
