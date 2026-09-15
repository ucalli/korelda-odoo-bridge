"""KORELDA webhook alıcısı.

Sözleşme: ``docs/dis-entegrasyon-webhook-sozlesmesi.md`` §2-§5.
Doğrulama çekirdeği ``..tools.webhook`` içinde (saf, Odoo'suz test edilebilir);
burada yalnız Odoo tutkalı var: secret okuma, görülmüş-imza deposu, yanıt.

🔴 **Secret ve imza asla log'a yazılmaz.** Hata kayıtları yalnız *hangi kontrol*
düştüğünü söyler; beklenen imzayı yanıta da yazmayız (sözleşme §3).
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone

import psycopg2

from odoo import SUPERUSER_ID, http
from odoo.http import request

from ..tools import webhook as wh
from ..tools.params import SECRET_PARAM

_logger = logging.getLogger(__name__)

#: Görülmüş-imza kayıtlarının yaşam süresi. Tazelik penceresinden KISA
#: OLAMAZ; kısa olursa pencere içinde tekrar açılırdı. Pay bırakılmıştır.
SEEN_TTL_SEC = wh.REPLAY_WINDOW_SEC * 4

#: Tek seferde budanacak azami kayıt — budama isteği geciktirmesin.
PRUNE_LIMIT = 500


class KoreldaWebhookController(http.Controller):
    """POST /korelda/webhook — imzalı alarm bildirimlerini alır."""

    @http.route(
        "/korelda/webhook",
        type="http",
        auth="none",
        methods=["POST"],
        csrf=False,
        save_session=False,
        # 🔴 AÇIKÇA yazılmalı. Odoo `readonly`yi `auth == "none"` olduğunda
        # **True** varsayar (`odoo/http.py`: `default_auth == 'none'`) —
        # kimliksiz uçları okuma sanır. Bu uç YAZAR (talep + görülmüş imza):
        # varsayılan bırakılırsa her istek önce salt-okunur imleçle koşup
        # "cannot execute INSERT in a read-only transaction" ile düşer, Odoo
        # yeniden dener ve sonuç doğru çıkar — ama her webhook iki kez koşar
        # ve günlüğe ERROR düşer.
        readonly=False,
    )
    def korelda_webhook(self, **kwargs):
        # 🔴 HAM BAYTLAR. `type="http"` bilinçli: `type="json"` gövdeyi
        # ayrıştırır ve biz tam baytları kaybederiz — imza onların üzerinde.
        body = request.httprequest.get_data()
        header = request.httprequest.headers.get(wh.SIGNATURE_HEADER) or ""

        # 🔴 `auth="none"` ortamı KULLANICISIZDIR (uid None) ve `sudo()` bunu
        # düzeltmez — Odoo 13'ten beri `sudo()` uid'i değiştirmez, yalnız
        # süper-kullanıcı bayrağı koyar. Kullanıcı yoksa `env.company` da boş
        # kalır ve `maintenance.request.company_id` NOT NULL kısıtına takılır.
        # Bu yüzden ortam AÇIKÇA gerçek bir kullanıcıya bağlanır.
        env = request.env(user=SUPERUSER_ID)

        secret = (
            env["ir.config_parameter"].get_param(SECRET_PARAM) or ""
        ).strip()
        if not secret:
            # Yapılandırılmamış kurulum imzasız gövdeyi kabul ETMEZ.
            _logger.warning(
                "KORELDA webhook: paylaşılan secret yapılandırılmamış (%s) — "
                "istek reddedildi",
                SECRET_PARAM,
            )
            return self._reject("not_configured")

        if not wh.signature_matches(secret, body, header):
            # Hangi imzayı beklediğimizi SÖYLEMEYİZ (sözleşme §3).
            _logger.info("KORELDA webhook: imza doğrulanamadı — reddedildi")
            return self._reject("bad_signature")

        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            _logger.info("KORELDA webhook: gövde JSON değil — reddedildi")
            return self._reject("bad_json")
        if not isinstance(payload, dict):
            return self._reject("bad_json")

        # K7 · 1. yarı — tazelik penceresi.
        if not wh.timestamp_is_fresh(payload.get("ts"), time.time()):
            _logger.info("KORELDA webhook: `ts` penceresi dışında — reddedildi")
            return self._reject("stale")

        # K7 · 2. yarı — görülmüş imza.
        if not self._remember(env, header):
            # Sözleşme §4/2: tekrar İŞLENMEZ ve 2xx döner (idempotent kabul).
            _logger.info("KORELDA webhook: imza daha önce işlendi — yok sayıldı")
            return self._ok(handled=False, reason="duplicate")

        kind, event = wh.classify(payload)
        if kind == "alarm":
            return self._handle_alarm(env, payload)
        # İmza geçerli; yalnız bu modülün işi değil → 401 DEĞİL, 200.
        return self._ok(handled=False, reason=kind, event=event)

    # ── alarm işleyicisi ────────────────────────────────────────────────

    def _handle_alarm(self, env, payload):
        """``rule_alarm`` → bakım talebi (K10-K13).

        Karar ve kayıt işlemleri modelde (``maintenance.request``); controller
        yalnız çağırır ve sonucu yanıta çevirir.
        """
        sonuc = env["maintenance.request"].korelda_process_alarm(payload)
        return self._ok(
            handled=sonuc.get("handled"),
            reason=sonuc.get("reason"),
            request_id=sonuc.get("request_id"),
        )

    # ── görülmüş-imza deposu ────────────────────────────────────────────

    def _remember(self, env, signature):
        """İmzayı kaydet. İlk kez görülüyorsa ``True``, tekrarsa ``False``.

        ``unique`` kısıtı kararı **veritabanına** verir: eşzamanlı iki özdeş
        istek yarışsa bile yalnız biri kaydı yazabilir. Savepoint, kısıt
        ihlalinin dış işlemi düşürmesini engeller.
        """
        seen = env["korelda.webhook.seen"]
        # Önce BAK: olağan tekrar yolu böylece sessizdir. Doğrudan INSERT
        # denemek her tekrarda PostgreSQL kısıt ihlali üretir ve Odoo onu
        # ERROR seviyesinde log'lar — yöneticinin gördüğü "hata" aslında
        # korumanın çalıştığı andır. Gürültü bir kusur değil ama yanıltıcı.
        if seen.search_count([("signature", "=", signature)]):
            return False
        try:
            with env.cr.savepoint():
                seen.create({"signature": signature})
                # INSERT'i şimdi zorla ki kısıt ihlali BURADA yakalansın.
                env.flush_all()
        except psycopg2.IntegrityError:
            # Buraya yalnız YARIŞ düşer: iki özdeş istek aynı anda geldi ve
            # ikisi de kontrolü geçti. Kısıt son sözü söyler.
            return False
        self._prune(seen)
        return True

    def _prune(self, seen):
        """TTL'i dolmuş kayıtları temizle (fırsatçı; ayrı cron gerekmez).

        Alarm trafiği seyrek olduğu için istek başına budama ucuzdur;
        ``PRUNE_LIMIT`` yine de tek isteğin uzun sürmesini engeller.
        """
        esik = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            seconds=SEEN_TTL_SEC
        )
        eski = seen.search([("create_date", "<", esik)], limit=PRUNE_LIMIT)
        if eski:
            eski.unlink()

    # ── yanıtlar ────────────────────────────────────────────────────────

    def _ok(self, handled, reason=None, **extra):
        govde = {"ok": True, "handled": bool(handled)}
        if reason:
            govde["reason"] = reason
        # `None` alanları gövdeye koymayız — alıcı "var ama boş" ile "yok"u
        # ayırt etmek zorunda kalmasın.
        govde.update({k: v for k, v in extra.items() if v is not None})
        return request.make_json_response(govde, status=200)

    def _reject(self, reason):
        """Tek durum kodu (401), gerekçe gövdede.

        Kod tek tutulur ki dışarıdan hangi kontrolün düştüğü durum koduyla
        taranamasın; entegratöre gereken açıklama gövdededir.
        """
        return request.make_json_response(
            {"ok": False, "error": reason}, status=401
        )
