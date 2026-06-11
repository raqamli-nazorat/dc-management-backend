import re
from rest_framework.throttling import ScopedRateThrottle

class CustomScopedRateThrottle(ScopedRateThrottle):
    def parse_rate(self, rate):
        if rate is None:
            return (None, None)
            
        try:
            num, period = rate.split('/')
            num_requests = int(num)
            
            match = re.match(r'^(\d+)?([smhd])', period)
            if match:
                multiplier = int(match.group(1)) if match.group(1) else 1
                unit = match.group(2)
                
                units = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}
                duration = units[unit] * multiplier
                
                return (num_requests, duration)
        except (ValueError, KeyError):
            pass
            
        raise ValueError(f"Throttling rate format not valid: {rate}. Correct format: 'count/unit' or 'count/Xunit' (e.g., '3/3m')")

    def get_cache_key(self, request, view):
        if hasattr(self, 'scope_attr'):
            self.scope = getattr(view, self.scope_attr, None)

        if not self.scope:
            return None

        if self.scope == 'login':
            ident = request.data.get('full_name') or self.get_ident(request)
        else:
            if request.user and request.user.is_authenticated:
                ident = request.user.pk
            else:
                ident = self.get_ident(request)

        return self.cache_format % {
            'scope': self.scope,
            'ident': ident
        }
