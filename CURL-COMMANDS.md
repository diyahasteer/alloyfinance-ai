# Curl Commands — Items API

## List all items

```bash
curl http://localhost:8000/items
```

## Get a single item

```bash
curl http://localhost:8000/items/1
```

## Create an item

```bash
curl -X POST http://localhost:8000/items \
  -H "Content-Type: application/json" \
  -d '{"name": "Test item", "value": "123"}'
```

## Update an item

```bash
curl -X PUT http://localhost:8000/items/1 \
  -H "Content-Type: application/json" \
  -d '{"name": "Updated name", "value": "456"}'
```

## Delete an item

```bash
curl -X DELETE http://localhost:8000/items/1
```

---

# Curl Commands — Transactions API

## Create a transaction

```bash
curl -X POST http://localhost:8000/api/transactions \
  -H "Content-Type: application/json" \
  -d '{
    "amount": -42.50,
    "merchant_name": "Trader Joes",
    "merchant_category": "supermarket",
    "spending_category": "groceries",
    "transaction_type": "debit",
    "payment_method": "debit_card",
    "city": "Berkeley",
    "country": "US",
    "currency": "USD",
    "description": "Weekly grocery run"
  }'
```

## Fetch transactions by spending category

```bash
curl http://localhost:8000/api/transactions/category/groceries
```

## Fetch current month transactions

```bash
curl http://localhost:8000/api/transactions/current-month
```

## Fetch previous month transactions

```bash
curl http://localhost:8000/api/transactions/previous-month
```

## Fetch N most recent transactions (default 10)

```bash
curl "http://localhost:8000/api/transactions/recent?limit=5"
```
