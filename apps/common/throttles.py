import hashlib
import logging
import re

from rest_framework.exceptions import Throttled
from rest_framework.throttling import ScopedRateThrottle

logger = logging.getLogger("api.throttling")

RATE_RE = re.compile(r"^(\d+)/(\d+)?([smhd])[a-z]*$")
UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


class CustomScopedRateThrottle(ScopedRateThrottle):
    def parse_rate(self, rate):
        if rate is None:
            return (None, None)

        match = RATE_RE.match(str(rate).strip().lower())
        if not match:
            raise ValueError(
                f"Throttle formati noto'g'ri kiritilgan: {rate!r}. "
                "To'g'ri format: 'son/birlik' yoki 'son/Xbirlik' "
                "(masalan: '5/m', '3/3m', '10/12h')"
            )

        num_requests = int(match.group(1))
        multiplier = int(match.group(2)) if match.group(2) else 1
        duration = UNITS[match.group(3)] * multiplier

        if num_requests < 1 or duration < 1:
            raise ValueError(f"Throttle qiymatlari musbat bo'lishi kerak: {rate!r}")

        return (num_requests, duration)

    def get_cache_key(self, request, view):
        if not getattr(self, "scope", None) and hasattr(self, "scope_attr"):
            self.scope = getattr(view, self.scope_attr, None)

        if not self.scope:
            return None

        if self.scope == "login":
            ident = self._login_ident(request)
        elif request.user and request.user.is_authenticated:
            ident = f"user:{request.user.pk}"
        else:
            ident = f"ip:{self.get_ident(request)}"

        ident = hashlib.sha256(ident.encode("utf-8")).hexdigest()

        return self.cache_format % {"scope": self.scope, "ident": ident}

    def _login_ident(self, request):
        try:
            username = str(request.data.get("username") or "").strip().lower()
        except Exception:
            username = ""
        return f"login:{self.get_ident(request)}:{username}"


class ThrottleExceptionHandlerMixin:
    def handle_exception(self, exc):
        response = super().handle_exception(exc)

        if response is None or not isinstance(response.data, dict):
            return response

        if isinstance(exc, Throttled):
            wait = int(exc.wait or 0)
            response.data["detail"] = (
                f"Urinishlar soni tugadi. "
                f"Iltimos {wait} soniyadan so'ng qayta urinib ko'ring."
            )
            response.data["retry_after_seconds"] = wait
            response.data["attempts_left"] = 0
        elif response.status_code in (400, 401):
            attempts_left = self._get_attempts_left()
            if attempts_left is not None:
                response.data["attempts_left"] = attempts_left

        return response

    def _get_attempts_left(self):
        try:
            for throttle in self.get_throttles():
                if not isinstance(throttle, ScopedRateThrottle):
                    continue

                throttle.scope = getattr(self, throttle.scope_attr, None)
                if not throttle.scope:
                    continue

                num_requests, duration = throttle.parse_rate(throttle.get_rate())
                if not num_requests or not duration:
                    continue

                cache_key = throttle.get_cache_key(self.request, view=self)
                if not cache_key:
                    continue

                history = throttle.cache.get(cache_key, [])
                now = throttle.timer()
                recent = [t for t in history if t > now - duration]

                return max(0, num_requests - len(recent))
        except Exception:
            logger.warning("attempts_left hisoblashda xatolik", exc_info=True)

        return None