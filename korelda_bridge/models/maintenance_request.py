"""Alarm gövdesi → ``maintenance.request`` (K10-K13).

Karar mantığı ``..tools.alarm`` içinde (saf, Odoo'suz sınanır); burada kayıt
işlemleri var.

🔴 **Gövde dış girdidir.** Mesajlara konan her metin (``subject``, ``message``,
kural adı) HTML olarak kaçırılır — alıcı tarafta bir alarm başlığının Odoo
sohbetine markup enjekte etmesi istenmez.
"""

import logging

from markupsafe import Markup

from odoo import _, api, fields, models
from odoo.tools import html_escape

from ..tools import alarm as al
from ..tools.params import DEFAULT_EQUIPMENT_PARAM

_logger = logging.getLogger(__name__)


class MaintenanceRequest(models.Model):
    _inherit = "maintenance.request"

    korelda_rule_id = fields.Char(
        string="KORELDA rule id",
        index=True,
        copy=False,
        help="Bu talebi açan KORELDA kuralı. Aynı kuralın tekrar eden "
        "alarmları açık talebe yorum olarak düşer, yeni talep açmaz.",
    )
    korelda_unmapped = fields.Boolean(
        string="KORELDA: equipment not mapped",
        copy=False,
        help="Alarm bir ekipmana eşlenemedi. Talep yine de açıldı; "
        "eşlemeyi tamamlayıp bu işareti kaldırın.",
    )

    # ── giriş noktası ───────────────────────────────────────────────────

    @api.model
    def korelda_process_alarm(self, payload):
        """``rule_alarm`` gövdesini işle → ``{handled, reason, request_id}``.

        Üç yol: alarm temizlendi (K12) · tekrar (K13) · yeni talep.
        """
        anahtar = al.rule_key(payload)
        acik = self._korelda_open_request(anahtar)

        if al.is_cleared(payload):
            return self._korelda_on_cleared(payload, acik)
        if acik:
            return self._korelda_on_repeat(payload, acik)
        return self._korelda_open_new(payload, anahtar)

    # ── üç yol ──────────────────────────────────────────────────────────

    def _korelda_on_cleared(self, payload, acik):
        """K12 — alarm temizlendi: talebi **KAPATMA**, yorum düş.

        Alarmın gitmesi işin bittiği anlamına gelmez; bunu bir insan
        değerlendirir. Otomatik kapatma, yapılmamış bir işi yapılmış
        gösterirdi.
        """
        if not acik:
            return {"handled": False, "reason": "no_open_request"}
        acik.message_post(
            body=self._korelda_body(
                _("Alarm cleared in KORELDA."), payload, olay=_("Cleared")
            )
        )
        return {
            "handled": True,
            "reason": "cleared_comment",
            "request_id": acik.id,
        }

    def _korelda_on_repeat(self, payload, acik):
        """K13 — aynı kural için açık talep varsa yeni açma, yorum düş."""
        acik.message_post(
            body=self._korelda_body(
                _("Alarm reported again in KORELDA."), payload, olay=_("Repeat")
            )
        )
        return {
            "handled": True,
            "reason": "duplicate_comment",
            "request_id": acik.id,
        }

    def _korelda_open_new(self, payload, anahtar):
        """Yeni bakım talebi aç."""
        ekipman, eslendi = self._korelda_equipment(anahtar)
        degerler = {
            "name": al.request_name(payload),
            "priority": al.priority_for(payload.get("severity")),
            "korelda_rule_id": anahtar or False,
            "korelda_unmapped": not eslendi,
        }
        if ekipman:
            degerler["equipment_id"] = ekipman.id
        talep = self.sudo().create(degerler)

        talep.message_post(
            body=self._korelda_body(
                _("Opened from a KORELDA alarm."), payload, olay=_("Alarm")
            )
        )
        if not eslendi:
            # K10 — sessiz kayıp YASAK: talep açıldı ama eşleme eksik;
            # kullanıcı bunu kayıtta görmeli, log'da değil.
            talep.message_post(
                body=Markup(
                    "<p>%s</p>"
                    % html_escape(
                        _(
                            "No equipment is mapped for this KORELDA rule, and "
                            "no default equipment is set. The request was opened "
                            "anyway — set the mapping so the next alarm lands on "
                            "the right equipment."
                        )
                    )
                )
            )
            _logger.info(
                "KORELDA: kural %s için ekipman eşlemesi yok — talep %s "
                "eşlenmemiş işaretiyle açıldı",
                anahtar or "(anahtarsız)",
                talep.id,
            )
        return {"handled": True, "reason": "created", "request_id": talep.id}

    # ── yardımcılar ─────────────────────────────────────────────────────

    @api.model
    def _korelda_open_request(self, anahtar):
        """Bu kural için **açık** talep (aşaması ``done`` olmayan), yoksa boş.

        Anahtar yoksa dedup yapılmaz — bkz. ``tools.alarm.rule_key``.
        """
        if not anahtar:
            return self.browse()
        return self.sudo().search(
            [
                ("korelda_rule_id", "=", anahtar),
                ("stage_id.done", "=", False),
            ],
            order="id desc",
            limit=1,
        )

    @api.model
    def _korelda_equipment(self, anahtar):
        """``(ekipman, eşlendi_mi)``. Eşleme → varsayılan → hiçbiri."""
        ekipman = self.env["korelda.mapping"].sudo()._equipment_for(anahtar)
        if ekipman:
            return ekipman, True
        ham = (
            self.env["ir.config_parameter"]
            .sudo()
            .get_param(DEFAULT_EQUIPMENT_PARAM)
        )
        try:
            varsayilan_id = int(ham or 0)
        except (TypeError, ValueError):
            varsayilan_id = 0
        if varsayilan_id:
            varsayilan = (
                self.env["maintenance.equipment"].sudo().browse(varsayilan_id).exists()
            )
            if varsayilan:
                return varsayilan, True
        return self.env["maintenance.equipment"].browse(), False

    @api.model
    def _korelda_body(self, baslik, payload, olay):
        """Sohbet mesajı gövdesi — dış metinler HTML olarak kaçırılır."""
        payload = payload or {}
        satirlar = [
            "<p><b>%s</b> %s</p>" % (html_escape(olay), html_escape(baslik))
        ]
        alanlar = [
            (_("Rule"), al.rule_label(payload) or al.rule_key(payload)),
            (_("Severity"), payload.get("severity")),
            (_("Message"), payload.get("message")),
        ]
        ogeler = [
            "<li>%s: %s</li>" % (html_escape(etiket), html_escape(str(deger)))
            for etiket, deger in alanlar
            if deger
        ]
        if ogeler:
            satirlar.append("<ul>%s</ul>" % "".join(ogeler))
        return Markup("".join(satirlar))
