# KORELDA Bridge — Alarm to Maintenance

Odoo module that receives **signed webhooks** from a KORELDA
building-management installation and opens a **maintenance request** for each
HVAC alarm.

KORELDA monitors HVAC plant over **Modbus TCP** (air handling units, pool
climate units and similar) and raises alarms from its own rules. This module
is the Odoo-side receiver for those alarms.

## What it does

| | |
|---|---|
| Endpoint | Listens for alarm events over HTTP(S). |
| Authentication | **HMAC-SHA256** signature on the raw request body. |
| Rejects | Unsigned, mis-signed, stale (older than 5 minutes) and replayed deliveries. |
| Creates | A `maintenance.request`, with alarm severity mapped to Odoo priority. |
| Equipment | Optional mapping from an alarm source to a `maintenance.equipment` record. |
| Alarm cleared | Posts a follow-up message on the request. |

## What it does not do

- **One direction only.** The module receives. It never writes back, sends
  commands, or opens a connection to the monitored installation.
- It creates no Odoo object other than `maintenance.request` and its own small
  mapping table.
- It does not configure alarm rules, thresholds or devices — those stay in
  KORELDA.
- It never closes a maintenance request on its own. When an alarm clears the
  module says so in a message; a person decides when the work is done.

## Requirements

- Odoo **18.0**, Community or Enterprise, **self-hosted**. Odoo Online/SaaS
  cannot install custom modules.
- Standard `maintenance` and `mail` modules (both shipped with Odoo).
- The Odoo instance must be reachable over **HTTPS** from the KORELDA
  installation.

## Installation

1. Copy `korelda_bridge/` into your Odoo addons path.
2. Restart Odoo, update the apps list, and install
   **KORELDA Bridge — Alarm to Maintenance**.
3. Open *Settings → Maintenance → KORELDA Bridge* and set the **shared
   secret**. Use a long random value.
4. On the KORELDA side, add this Odoo instance as a webhook target and store
   the same secret there.

The shared secret is what authenticates every delivery. Anyone who holds it
can open maintenance requests in your database — treat it like a password,
and use a different one for every Odoo instance.

## Status

Skeleton in place. The receiver, the model and the configuration screen land
in the following steps; see the repository branches `18.0` and `19.0`.

## Licence

LGPL-3. The LGPL adds permissions on top of the GPL, so both texts apply —
see [`LICENSE`](../LICENSE) and [`COPYING`](../COPYING) at the repository
root.
