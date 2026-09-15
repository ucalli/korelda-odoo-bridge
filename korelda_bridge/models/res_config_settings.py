"""Ayarlar — paylaşılan secret + varsayılan ekipman.

Ekran (görünüm) FAZ 1.4'te; burada yalnız alanlar ve saklama yeri.
Her ikisi de ``ir.config_parameter``da durur, veritabanı kolonunda değil.
"""

from odoo import fields, models

from ..tools.params import DEFAULT_EQUIPMENT_PARAM, SECRET_PARAM


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    korelda_webhook_secret = fields.Char(
        string="KORELDA shared secret",
        config_parameter=SECRET_PARAM,
        help="Aynı değer KORELDA tarafında da yazılıdır. Gelen her isteğin "
        "imzası bununla doğrulanır — uzun ve rastgele olmalı, her Odoo "
        "kurulumu için ayrı.",
    )
    korelda_default_equipment_id = fields.Many2one(
        comodel_name="maintenance.equipment",
        string="Default equipment",
        config_parameter=DEFAULT_EQUIPMENT_PARAM,
        help="Bir kural hiçbir ekipmana eşlenmemişse talep bu ekipmana "
        "açılır. Boş bırakılabilir: o durumda talep yine açılır ve "
        "'eşlenmemiş' olarak işaretlenir.",
    )
