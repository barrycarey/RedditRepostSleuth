import json
from falcon import Request, Response


class Health:
    def on_get(self, req: Request, resp: Response):
        resp.text = json.dumps({"status": "healthy"})
