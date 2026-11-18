"""Run the Lambda handler locally against in-memory tables, the way Zapier's Webhooks steps call it.

    python lambda/local_demo.py
"""
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
import handler  # noqa: E402


class MemoryTable:
    def __init__(self, key, items=()):
        self.key, self.items = key, {i[key]: i for i in items}

    def get_item(self, Key):
        return {"Item": self.items[Key[self.key]]} if Key[self.key] in self.items else {}

    def put_item(self, Item):
        self.items[Item[self.key]] = Item

    def scan(self, **_):
        return {"Items": list(self.items.values())}


jobs = json.loads((HERE.parent / "data" / "job_requirements.json").read_text(encoding="utf-8"))
tables = {"smarthire_job_requirements": MemoryTable("position", [
              {k: Decimal(str(v)) if isinstance(v, int) else v for k, v in j.items()} for j in jobs]),
          "smarthire_evaluations": MemoryTable("submission_id")}
handler.table = lambda name: tables[name]
os.environ["API_KEY"] = "demo-key"


def call(method, path, query=None, body=None, key="demo-key"):
    event = {"rawPath": path, "queryStringParameters": query, "requestContext": {"http": {"method": method}},
             "headers": {"x-api-key": key, "content-type": "application/json"} if key else {},
             "body": json.dumps(body) if body else None}
    r = handler.lambda_handler(event)
    shown = "&".join(f"{k}={v}" for k, v in (query or {}).items())
    print(f"> {method} {path}{'?' + shown if shown else ''}{'' if key else '   (no x-api-key)'}")
    if body:
        print(f"  body: {json.dumps(body)}")
    print(f"< {r['statusCode']} {r['body'][:600]}\n")


call("GET", "/requirements", {"position": "Software Engineer"}, key=None)
call("GET", "/requirements", {"position": "Software Engineer"})
call("GET", "/requirements", {"position": "Data Scientist"})
for sid, name, pos, score, decision in [("zap-101", "Alex Carter", "Software Engineer", 100, "advance"),
                                        ("zap-102", "John Smith", "Software Engineer", 17, "reject"),
                                        ("zap-103", "Alex Carter", "AI Engineer", 44, "reject")]:
    call("POST", "/evaluations", body={"submission_id": sid, "name": name, "position": pos,
                                       "score": str(score), "decision": decision, "timeline_flag": "false"})
call("GET", "/rankings", {"position": "software_engineer"})
