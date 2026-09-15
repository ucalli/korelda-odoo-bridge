"""Kural → ekipman eşlemesi (K10).

Eşleme **açıkça kurulur**: kullanıcı hangi KORELDA kuralının hangi Odoo
ekipmanına karşılık geldiğini söyler. Gövdedeki ``inputs[].ref`` gibi
alanlardan ekipman **çıkarılmaz** — o alanlar gönderen tarafın iç adresleme
biçimidir, bu modülün bilmesi gereken bir şey değildir ve biçim değişince
eşleme sessizce bozulurdu.
"""

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class KoreldaMapping(models.Model):
    _name = "korelda.mapping"
    _description = "KORELDA kuralı → bakım ekipmanı eşlemesi"
    _order = "rule_id"
    _rec_name = "rule_id"

    rule_id = fields.Char(
        string="KORELDA rule id",
        required=True,
        index=True,
        help="Gelen gövdedeki rule.id değeri. Birebir eşleşmelidir.",
    )
    equipment_id = fields.Many2one(
        comodel_name="maintenance.equipment",
        string="Equipment",
        required=True,
        ondelete="cascade",
        help="Bu kuraldan gelen alarmların açacağı talebin ekipmanı.",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "rule_id_uniq",
            "unique(rule_id)",
            "Bu KORELDA kuralı için zaten bir eşleme var.",
        ),
    ]

    @api.constrains("rule_id")
    def _check_rule_id(self):
        for kayit in self:
            if not (kayit.rule_id or "").strip():
                raise ValidationError(_("KORELDA rule id boş olamaz."))

    @api.model
    def _equipment_for(self, rule_key):
        """Kural anahtarı → ekipman kaydı; eşleme yoksa boş recordset.

        Devre dışı bırakılmış (``active=False``) eşleme **kullanılmaz** —
        kullanıcı onu bilerek kapatmıştır.
        """
        if not rule_key:
            return self.env["maintenance.equipment"].browse()
        kayit = self.search([("rule_id", "=", rule_key)], limit=1)
        return kayit.equipment_id
