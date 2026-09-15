# KORELDA Bridge — Alarm to Maintenance

Odoo module that receives **signed webhooks** from a KORELDA building-management
installation and opens a **maintenance request** for each HVAC alarm.

Free and open source (LGPL-3).

## What it does

- Listens on an HTTP endpoint for alarm events sent by KORELDA.
- Verifies every request with an **HMAC-SHA256 signature** and rejects
  unsigned, mis-signed, stale or replayed deliveries.
- Opens a `maintenance.request`, mapping alarm severity to Odoo priority.
- Optionally maps an alarm source to a `maintenance.equipment` record.
- Posts a follow-up message when the alarm clears — it never closes a request
  on its own; a human decides when the work is done.

## What it does not do

- **One direction only.** The module receives; it never writes back, sends
  commands, or opens a connection to the monitored installation.
- It does not create or manage any Odoo object other than
  `maintenance.request` (plus its own small mapping table).
- It does not configure alarm rules, thresholds or devices — those stay in
  KORELDA.

## Scope

KORELDA monitors HVAC plant over **Modbus TCP** (air handling units, pool
climate units and similar) and raises alarms from its own rules. This module
is the Odoo-side receiver for those alarms.

## Requirements

- Odoo **18.0** or **19.0**, Community or Enterprise, **self-hosted**
  (Odoo Online/SaaS cannot install custom modules).
- Depends on the standard `maintenance` and `mail` modules.
- The Odoo instance must be reachable over **HTTPS** from the KORELDA
  installation.

Branches: `18.0` (default) · `19.0`.

## Installation

1. Copy `korelda_bridge/` into your Odoo addons path, or add this repository
   to it.
2. Update the apps list and install **KORELDA Bridge — Alarm to Maintenance**.
3. Open *Settings → Maintenance → KORELDA Bridge* and set the **shared
   secret**. Use the same value on the KORELDA side.
4. In KORELDA, add this Odoo instance as a webhook target using the endpoint
   URL shown on that settings page.

The shared secret is what authenticates every delivery — keep it secret and
use a long random value.

## Licence

LGPL-3 — see [LICENSE](LICENSE).
