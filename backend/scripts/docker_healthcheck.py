"""Docker HEALTHCHECK: is the API process answering?

Any HTTP response counts as alive, including `503 degraded` from /api/health (low disk space):
Traefik stops routing to unhealthy containers, which would take the whole app down instead of
just reporting the problem.
"""

import sys
import urllib.error
import urllib.request

try:
    urllib.request.urlopen("http://127.0.0.1:8000/api/health", timeout=4)
except urllib.error.HTTPError:
    pass
except Exception:
    sys.exit(1)
