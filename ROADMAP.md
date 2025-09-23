# FusionX Backend Roadmap

_Last updated: 2024-09-30_

## Legend
- [x] Completed
- [ ] Planned / Not started
- [ ] (In progress) – annotate with text

## Phase 0 – Baseline Platform (Complete)
- [x] FastAPI application skeleton with SQLModel persistence layer
- [x] Token-based staff authentication with password hashing
- [x] Device registration for TruckKDS clients
- [x] Truck shift lifecycle (check-in, checkout, pause, resume)
- [x] Menu retrieval and inventory adjustments per shift
- [x] KDS ticket feed with guarded order state transitions
- [x] WebSocket hub for real-time shift events
- [x] Developer seed script and simulated order generator

## Phase 1 – Operational MVP (Complete)
- [x] Provide mobile endpoint to list active trucks a staff member can act on (Iteration 1)
- [x] Provide mobile endpoint to list active service locations for shift check-in (Iteration 1)
- [x] Add per-shift summary endpoint (order counts, revenue, average prep time)
- [x] Expose staff-accessible configuration for throttle and slot capacity adjustments
- [x] Deliver heartbeat endpoint so devices can report liveness / capture last_seen timestamps

## Phase 2 – Menu & Inventory Management (Complete)
- [x] CRUD endpoints for menu items (name, description, base price)
- [x] Support menu categories and ordering for TruckKDS display
- [x] Allow per-shift specials (temporary items) and schedule-based availability windows
- [x] Atomic stock decrements tied to payment notifications from customer ordering flow

## Phase 3 – Order Lifecycle Enhancements (Complete)
- [x] Dedicated order detail endpoint with customer contact information and item modifiers
- [x] Ability to place tickets on hold / resume for timed prep coordination
- [x] Cancellation & refund reasons with audit trail and metrics
- [x] Bulk advance endpoint for clearing multiple READY tickets at closeout

## Phase 4 – Notifications & Staff Experience (Complete)
- [x] APNs push notification service for new orders and low stock alerts
- [x] Device management console (list / revoke tokens, capture app version & OS)
- [x] Optional SMS fallback alerts for low connectivity trucks
- [x] Staff profile endpoint for updating password, preferred notification channels

## Phase 5 – Administration & Access Control (Complete)
- [x] Admin API for managing trucks, locations, staff assignments, and operating hours
- [x] Role-based access control enforcement (per-route permissions)
- [x] Audit logging for privileged operations (menu edits, refunds, shift overrides)

## Phase 6 – Reporting & Analytics (Complete)
- [x] Shift history export (CSV/JSON) with order, labor, and inventory deltas
- [x] Real-time dashboard endpoints (current order throughput, wait times)
- [x] Weekly automated summary email (orders, revenue, stock-outs)

## Phase 7 – Reliability, Observability & Deployment (Complete)
- [x] Structured logging with correlation IDs for each request / websocket session
- [x] Metrics instrumentation (Prometheus) for API latency, DB usage, and queue depth
- [x] Healthcheck & readiness endpoints for container orchestration
- [x] Harden configuration management (12-factor env vars, secrets, migrations)
- [x] CI pipeline (lint, tests, image build, deployment manifest)

## Phase 8 – Quality Assurance & Developer Experience (Complete)
- [x] Unit test coverage for auth, shift, menu, and order flows
- [x] Contract tests for mobile API schema stability
- [x] Load testing scenarios to validate throughput at peak events
- [x] API documentation (OpenAPI polish, endpoint usage guides)
- [x] Local development scripts (make targets, sample data refresh, watch mode)

## Phase 9 – Customer Ordering Integration (Stretch) (Complete)
- [x] Customer-facing ordering API (menu browsing, cart, checkout)
- [x] Payment gateway webhook integration for order confirmation
- [x] Auto-reconciliation of customer orders with KDS queue
- [x] Loyalty / rewards tracking hooks for repeat guests

---

### Iteration History
- **Iteration 1 (2024-02-16):** Bootstrapped roadmap, added truck & location discovery endpoints for the mobile client, refreshed README to describe available capabilities.
- **Iteration 2 (2024-03-01):** Added device heartbeat tracking, per-shift configuration management, and summary reporting endpoints for mobile clients.
- **Iteration 3 (2024-09-30):** Delivered full menu CRUD, specials, notifications, admin/analytics APIs, customer ordering flow, observability tooling, and automated test pipeline.
