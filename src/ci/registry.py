"""Per-host encrypted CI records. Manual metadata survives discovery failures."""
from datetime import datetime, date
import hashlib

from shared.ci_schema import FIELDS, AUTO_FIELDS
from shared.sorting import sort_key


def stamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


class CIRegistry:
    def __init__(self, store):
        self.store = store
        self.cache = {}

    def key(self, hostname):
        return "ci/" + hashlib.sha256(hostname.encode()).hexdigest() + ".json.enc"

    def get(self, hostname):
        if hostname not in self.cache:
            self.cache[hostname] = self.store.read_json(self.key(hostname), {})
        return dict(self.cache[hostname])

    def save(self, hostname, value):
        self.store.write_json(self.key(hostname), value)
        self.cache[hostname] = value

    def observe(self, host, observation=None, error=""):
        row = self.get(host["hostname"])
        row.update(last_attempt=stamp(), collection_status="failed" if error else "completed", error=error[:1500])
        if observation is not None:
            row.update(observed=observation, observed_ip=host["ip"], last_success=row["last_attempt"])
        self.save(host["hostname"], row)

    def update(self, inventory, hosts, patch):
        if not isinstance(hosts, list) or not hosts or len(hosts) > 5000 or len(hosts) != len(set(hosts)):
            raise ValueError("Select 1–5000 distinct inventory hosts")
        known = {r["hostname"] for r in inventory}
        if any(h not in known for h in hosts):
            raise ValueError("Unknown inventory host")
        if not isinstance(patch, dict) or not patch or set(patch) - FIELDS.keys():
            raise ValueError("Invalid CI metadata fields")
        for key, value in patch.items():
            if not isinstance(value, str) or len(value) > (4000 if key == "notes" else 256):
                raise ValueError("Invalid CI metadata value: " + key)
            if key == "operational_status" and value not in {"", "운영", "유휴", "폐기"}:
                raise ValueError("Invalid operational status")
            if key in {"purchase_date", "support_end"} and value:
                if date.fromisoformat(value).isoformat() != value:
                    raise ValueError("Use YYYY-MM-DD dates")
        updated, failed = [], []
        for host in hosts:
            row = self.get(host)
            row["manual"] = {**row.get("manual", {}), **patch}
            row["updated_at"] = stamp()
            try:
                self.save(host, row)
                updated.append(host)
            except OSError:
                failed.append(host)
        return {"updated": updated, "failed": failed}

    def listing(self, inventory, params):
        query = str(params.get("query", "")).casefold()
        status = params.get("operational_status", "")
        hosts = params.get("hosts")
        if hosts is not None and (not isinstance(hosts, list) or len(hosts) > 5000):
            raise ValueError("Invalid host filter")
        chosen = set(hosts) if hosts is not None else None
        rows = []
        counts = {"운영": 0, "유휴": 0, "폐기": 0, "미지정": 0}
        for host in inventory:
            if chosen is not None and host["hostname"] not in chosen:
                continue
            saved = self.get(host["hostname"])
            row = {**saved, **host, "stale": bool(saved.get("observed_ip") and saved["observed_ip"] != host["ip"])}
            manual = row.get("manual", {})
            if status and manual.get("operational_status", "") != status:
                continue
            values = [host["hostname"], host["ip"], *manual.values(), *[str(v) for v in row.get("observed", {}).values()]]
            if query and query not in " ".join(values).casefold():
                continue
            rows.append(row)
            counts[manual.get("operational_status") or "미지정"] += 1
        field = params.get("sort_key")
        if field:
            if field not in {"hostname", "ip", "os", "profile", "last_attempt", "last_success", "collection_status", "error", "updated_at", "observed_ip", "stale", *FIELDS, *AUTO_FIELDS}:
                raise ValueError("Invalid CI sort attribute")
            def value(row):
                if field == "collection_status":
                    if row.get("stale"): return "주소 변경 · 재수집 필요"
                    if row.get("collection_status") == "failed": return "실패 · 상세 확인"
                    if row.get("observed", {}).get("warnings"): return "완료 · 참고 있음"
                return {**row.get("observed", {}), **row.get("manual", {}), **{k:v for k,v in row.items() if k not in {"observed", "manual"}}}.get(field)
            present = [row for row in rows if value(row) is not None and value(row) != ""]
            missing = [row for row in rows if value(row) is None or value(row) == ""]
            present.sort(key=lambda row: (sort_key(value(row)), row["hostname"].casefold()), reverse=bool(params.get("descending", False)))
            rows = present + missing
        offset = max(0, int(params.get("offset", 0)))
        size = min(200, max(1, int(params.get("page_size", 100))))
        return {"rows": rows[offset:offset+size], "total": len(rows), "counts": counts, "offset": offset}
