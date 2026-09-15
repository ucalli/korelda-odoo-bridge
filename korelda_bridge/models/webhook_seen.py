"""Görülmüş-imza deposu — K7 replay korumasının ikinci yarısı.

Sözleşme §4: zaman penceresi **ve** görülmüş-imza önbelleği, ikisi birlikte.
Yalnız pencere → pencere içinde yakalanan istek defalarca oynatılabilir.
Yalnız önbellek → TTL dolunca eski gövde yeniden geçerli olur.

🔴 **Neden bellekte değil, veritabanında:** Odoo üretimde birden çok worker
sürecinde koşar (``--workers=N``) ve süreçler bellek paylaşmaz. Bellek içi bir
sözlük, tekrarı **başka bir worker'a düşen** isteği hiç görmezdi — yani koruma
worker sayısı kadar delik taşırdı. Tablo + ``unique`` kısıtı ayrıca eşzamanlı
iki özdeş isteği de veritabanı düzeyinde atomik olarak ayıklar.
"""

from odoo import fields, models


class KoreldaWebhookSeen(models.Model):
    _name = "korelda.webhook.seen"
    _description = "KORELDA webhook — görülmüş imza (replay koruması)"
    # Kayıtlar kısa ömürlü; en yeniden başlamak teşhiste işe yarar.
    _order = "id desc"

    signature = fields.Char(
        string="Signature",
        required=True,
        index=True,
        help="Kaydedilen X-BMS-Signature başlığı. Gövde değil, secret değil.",
    )

    _sql_constraints = [
        (
            "signature_uniq",
            "unique(signature)",
            "Bu imza zaten işlendi (replay koruması).",
        ),
    ]
