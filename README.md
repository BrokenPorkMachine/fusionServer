# FusionX — FastAPI server for roaming food truck ordering

This repo includes:
- **Mobile API** for the iOS TruckKDS app (auth, device register, shift check-in/out, pause/resume, per-shift inventory, KDS, WebSocket).
- **Dev tools**: seed data and simulated orders.

## Quickstart
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
make run
```
Open: http://127.0.0.1:8000

Seed data:
```bash
make seed
# username: chef   password: password
```

### Endpoints
- `POST /api/mobile/login` → `{ token, staff }`
- `POST /api/mobile/devices/register` → registers APNs token
- `GET /api/mobile/shift/active`
- `POST /api/mobile/shift/checkin {truck_id, location_id}`
- `POST /api/mobile/shift/{id}/checkout`
- `POST /api/mobile/shift/{id}/pause` (reason, minutes)
- `POST /api/mobile/shift/{id}/resume`
- `GET /api/mobile/shift/{id}/menu` → per-shift prices/stock
- `PATCH /api/mobile/shift/{id}/inventory` → bulk stock updates
- `GET /api/mobile/shift/{id}/kds` → tickets
- `POST /api/mobile/order/{order_id}/advance` → guarded transitions
- `WS /api/mobile/ws/shift/{id}` → events: `new_order`, `low_stock`, `pause`, `resume`

Dev helpers:
- `POST /dev/seed`
- `POST /dev/sim-order/{shift_id}`

### Wire to TruckKDS (iOS)
Set `Config.swift` in the TruckKDS app:
```swift
static let apiBase = URL(string: "http://YOUR-IP:8000")!
static let wsBase  = URL(string: "ws://YOUR-IP:8000")!
```

### Production notes
- Replace token system with real JWT/OIDC.
- Replace SQLite with Postgres.
- Add APNs push (server-side) and rate limits.
- Enforce role-based access per truck.
- Add atomic stock decrement on payment success in the **customer checkout** flow.
