{
    "name": "KORELDA Bridge — Alarm to Maintenance",
    "version": "18.0.1.0.0",
    "category": "Maintenance",
    "license": "LGPL-3",
    "author": "KORELDA",
    "website": "https://www.korelda.ai",
    "support": "support@korelda.ai",
    "summary": (
        "Turn signed HVAC alarm webhooks from a KORELDA installation into "
        "Odoo maintenance requests."
    ),
    "description": """
KORELDA Bridge — Alarm to Maintenance
=====================================

Receives **signed webhooks** from a KORELDA building-management installation
and opens a ``maintenance.request`` for each HVAC alarm.

KORELDA monitors HVAC plant over **Modbus TCP** (air handling units, pool
climate units and similar) and raises alarms from its own rules. This module
is the Odoo-side receiver for those alarms.

What it does
------------

* Listens on an HTTP endpoint for alarm events.
* Verifies every request with an **HMAC-SHA256 signature** and rejects
  unsigned, mis-signed, stale or replayed deliveries.
* Opens a maintenance request, mapping alarm severity to Odoo priority.
* Optionally maps an alarm source to a ``maintenance.equipment`` record.
* Posts a follow-up message when the alarm clears. It never closes a request
  on its own — a person decides when the work is done.

What it does not do
-------------------

* **One direction only.** The module receives. It never writes back, sends
  commands, or opens a connection to the monitored installation.
* It creates no Odoo object other than ``maintenance.request`` and its own
  small mapping table.
* It does not configure alarm rules, thresholds or devices. Those stay in
  KORELDA.

Requirements
------------

Odoo 18.0, Community or Enterprise, **self-hosted** — Odoo Online/SaaS cannot
install custom modules. The Odoo instance must be reachable over HTTPS from
the KORELDA installation.

Licence: LGPL-3.
""",
    "depends": [
        "maintenance",
        "mail",
    ],
    # 🔴 SIRA ANLAMLI: ayar ekranı `action_korelda_mapping` eylemine
    # `%(...)d` ile atıf yapıyor; eylem ondan ÖNCE tanımlanmış olmalı.
    "data": [
        "security/ir.model.access.csv",
        "views/korelda_mapping_views.xml",
        "views/res_config_settings_views.xml",
    ],
    "images": [
        "static/description/korelda_bridge_cover_screenshot.gif",
        "static/description/korelda_bridge_screenshot.png",
        "static/description/korelda_settings.png",
        "static/description/korelda_mapping.png",
    ],
    "application": False,
    "installable": True,
    "auto_install": False,
}
