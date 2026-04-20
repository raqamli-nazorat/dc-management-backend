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
            
        raise ValueError(f"Throttling rate formati noto'g'ri: {rate}. "
                         f"To'g'ri format: 'son/birlik' yoki 'son/Xbirlik' (masalan: '3/3m')")
