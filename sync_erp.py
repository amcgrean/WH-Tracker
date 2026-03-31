import hashlib
import json
import os
import sys
import time
from datetime import datetime, date
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.runtime_settings import get_sync_settings, load_tracker_env

load_tracker_env()


class LocalSync:
    def __init__(self):
        from app.Services.erp_service import ERPService
        from app.Services.geocoding_service import GeocodingService

        self.settings = get_sync_settings()
        self.database_url = self.settings["database_url"]
        self.sync_interval = self.settings["interval_seconds"]
        self.change_monitoring = self.settings["change_monitoring"]
        self.worker_name = self.settings["worker_name"]
        self.worker_mode = self.settings["worker_mode"]
        self.status_file = Path(__file__).resolve().parent / "logs" / "erp_sync_status.json"

        self.erp = ERPService()
        self.erp.cloud_mode = False
        self.geocoder = GeocodingService()
        self.db_session = None
        self.engine = None
        self.Session = None
        self.last_payload_hash = None
        self.last_change_token = None

        if not self.database_url:
            raise RuntimeError(
                "DATABASE_URL is required for sync_erp.py. Legacy API sync mode has been retired."
            )

        print(f"[{datetime.now()}] Direct SQL Mode Enabled. Connecting to mirror DB...")
        try:
            self.engine = create_engine(self.database_url)
            self.Session = sessionmaker(bind=self.engine)
            self.db_session = self.Session()
            with self.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            print(f"[{datetime.now()}] Mirror DB connection successful.")
        except Exception as e:
            print(f"[{datetime.now()}] Mirror DB connection failed: {e}")
            raise

    def _parse_erp_datetime(self, date_str):
        if not date_str:
            return None
        if isinstance(date_str, (datetime, date)):
            return date_str
            
        s = str(date_str).strip()
        if not s or s.lower() == 'none':
            return None
            
        parts = s.split()
        if len(parts) >= 2:
            date_part = parts[0]
            time_part = parts[-1] 
            try:
                return datetime.strptime(f"{date_part} {time_part}", "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
                
        try:
            return datetime.strptime(parts[0], "%Y-%m-%d")
        except ValueError:
            pass
            
        return None

    def fetch_local_data(self):
        print(f"[{datetime.now()}] Fetching data from local ERP...")
        picks = self.erp.get_open_picks()
        work_orders = self.erp.get_open_work_orders()

        kpis = []
        for branch_id in [None, "20gr", "25bw", "10fd", "40cv"]:
            kpis.extend(self.erp.get_historical_delivery_stats(days=14, branch_id=branch_id))

        return {
            "picks": picks,
            "work_orders": work_orders,
            "kpis": kpis,
        }

    def _serialize(self, value):
        if isinstance(value, dict):
            return {str(k): self._serialize(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
        if isinstance(value, (list, tuple)):
            normalized = [self._serialize(v) for v in value]
            return sorted(
                normalized,
                key=lambda item: json.dumps(item, sort_keys=True, default=str) if isinstance(item, (dict, list)) else str(item),
            )
        if isinstance(value, datetime):
            return value.isoformat()
        return value

    def _counts(self, data):
        return {
            "picks": len(data.get("picks", [])),
            "work_orders": len(data.get("work_orders", [])),
            "kpis": len(data.get("kpis", [])),
        }

    def _payload_hash(self, data):
        payload = self._serialize(data)
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _status_payload(self, *, status, counts, payload_hash, push_reason, last_error=None):
        if status in ("success", "noop"):
            self.last_payload_hash = payload_hash
            self.last_change_token = payload_hash[:12]

        return {
            "worker_name": self.worker_name,
            "worker_mode": self.worker_mode,
            "source_mode": "local_sql",
            "target_mode": "direct_db",
            "interval_seconds": self.sync_interval,
            "change_monitoring": self.change_monitoring,
            "status": status,
            "last_error": last_error,
            "last_change_token": self.last_change_token,
            "last_payload_hash": self.last_payload_hash or payload_hash,
            "last_push_reason": push_reason,
            "counts": counts,
        }

    def _coerce_date(self, value):
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value).split("T")[0]).date()
        except Exception:
            return None

    def _write_status_file(self, payload):
        self.status_file.parent.mkdir(parents=True, exist_ok=True)
        body = dict(payload)
        body["written_at"] = datetime.utcnow().isoformat() + "Z"
        self.status_file.write_text(json.dumps(body, indent=2), encoding="utf-8")

    def _record_status_direct(self, payload):
        from app.Models.models import ERPSyncState
        state = self.db_session.query(ERPSyncState).filter_by(worker_name=payload["worker_name"]).first()
        if state is None:
            state = ERPSyncState(worker_name=payload["worker_name"])
            self.db_session.add(state)

        now = datetime.utcnow()
        state.worker_mode = payload["worker_mode"]
        state.source_mode = payload["source_mode"]
        state.target_mode = payload["target_mode"]
        state.interval_seconds = payload["interval_seconds"]
        state.change_monitoring = payload["change_monitoring"]
        state.last_status = payload["status"]
        state.last_error = payload.get("last_error")
        state.last_change_token = payload.get("last_change_token")
        state.last_payload_hash = payload.get("last_payload_hash")
        state.last_push_reason = payload.get("last_push_reason")
        state.last_counts_json = json.dumps(payload.get("counts", {}))
        state.last_heartbeat_at = now
        if payload["status"] in ("success", "noop"):
            state.last_success_at = now
        if payload["status"] == "error":
            state.last_error_at = now
        self.db_session.commit()

    def record_status(self, payload):
        self._write_status_file(payload)
        try:
            self._record_status_direct(payload)
        except Exception as e:
            print(f"[{datetime.now()}] Failed to persist sync status: {e}")

    def push_to_cloud(self, data):
        payload_hash = self._payload_hash(data)
        counts = self._counts(data)
        sync_started_at = datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

        if self.change_monitoring and payload_hash == self.last_payload_hash:
            status = self._status_payload(
                status="noop",
                counts=counts,
                payload_hash=payload_hash,
                push_reason="no_changes_detected",
            )
            self.record_status(status)
            print(f"[{datetime.now()}] No ERP changes detected. Recorded heartbeat only.")
            return status

        try:
            self.push_direct_to_db(data)

            status = self._status_payload(
                status="success",
                counts=counts,
                payload_hash=payload_hash,
                push_reason="changes_pushed",
            )
            self.record_status(status)
            return status
        except Exception as e:
            status = self._status_payload(
                status="error",
                counts=counts,
                payload_hash=payload_hash,
                push_reason="push_failed",
                last_error=str(e),
            )
            self.record_status(status)
            raise

    def _update_dashboard_stats(self, data):
        """Compute dashboard counts from already-fetched ERP data and push to
        the dashboard_stats table so the web dashboard can read a single row
        instead of running heavy multi-join queries."""
        picks = data.get("picks", [])
        work_orders = data.get("work_orders", [])

        # Count distinct SOs (a pick line list may have multiple lines per SO)
        seen_sos = set()
        handling_sos = {}  # handling_code -> set of (system_id, so_id)
        for p in picks:
            key = (str(p.get('system_id', '')), str(p.get('so_number', '')))
            seen_sos.add(key)
            code = str(p.get('handling_code', '') or '').strip().upper() or '—'
            handling_sos.setdefault(code, set()).add(key)

        total_picks = len(seen_sos)
        handling_breakdown = {code: len(sos) for code, sos in sorted(handling_sos.items())}
        total_wo = len(work_orders)

        try:
            self.db_session.execute(
                text(
                    "UPDATE dashboard_stats "
                    "SET open_picks = :picks, "
                    "    handling_breakdown_json = :breakdown, "
                    "    open_work_orders = :wo, "
                    "    updated_at = :ts "
                    "WHERE id = 1"
                ),
                {
                    "picks": total_picks,
                    "breakdown": json.dumps(handling_breakdown),
                    "wo": total_wo,
                    "ts": datetime.utcnow(),
                },
            )
            self.db_session.commit()
            print(f"[{datetime.now()}] Dashboard stats updated: {total_picks} picks, {total_wo} WOs")
        except Exception as e:
            self.db_session.rollback()
            print(f"[{datetime.now()}] Failed to update dashboard_stats: {e}")

    def push_direct_to_db(self, data):
        # Legacy direct mirror tables are retired.
        # Now updates pre-computed dashboard stats and records heartbeat.

        print(f"[{datetime.now()}] Pushing dashboard stats and heartbeat...")
        try:
            self._update_dashboard_stats(data)
            self.db_session.commit()
            print(f"[{datetime.now()}] Heartbeat recorded.")
        except Exception:
            self.db_session.rollback()
            raise

    def geocode_pending_shiptos(self, batch_size=10):
        """Geocode erp_mirror_cust_shipto records that have no lat/lon yet.

        Uses Nominatim (OpenStreetMap) — free, no API key required.
        Nominatim requires ≤1 req/sec; we sleep 1.1s between calls.
        Processes `batch_size` records per invocation so we don't block the loop.
        """
        import requests as _req

        try:
            rows = self.db_session.execute(
                text(
                    "SELECT id, address_1, city, state, zip "
                    "FROM erp_mirror_cust_shipto "
                    "WHERE lat IS NULL AND (address_1 IS NOT NULL OR city IS NOT NULL) "
                    "LIMIT :n"
                ),
                {"n": batch_size},
            ).fetchall()
        except Exception as exc:
            print(f"[{datetime.now()}] geocode_pending_shiptos: query failed: {exc}")
            return

        if not rows:
            return

        print(f"[{datetime.now()}] Geocoding {len(rows)} pending ship-to records...")
        updated = 0
        for row in rows:
            parts = [p for p in [row.address_1, row.city, row.state, row.zip] if p and str(p).strip()]
            if not parts:
                continue
            query = ", ".join(str(p).strip() for p in parts)
            try:
                resp = _req.get(
                    "https://nominatim.openstreetmap.org/search",
                    params={"q": query, "format": "json", "limit": 1},
                    headers={"User-Agent": "WH-Tracker/1.0 (dispatch geocoder)"},
                    timeout=10,
                )
                resp.raise_for_status()
                results = resp.json()
                if results:
                    lat = float(results[0]["lat"])
                    lon = float(results[0]["lon"])
                    self.db_session.execute(
                        text(
                            "UPDATE erp_mirror_cust_shipto "
                            "SET lat=:lat, lon=:lon, geocoded_at=:ts, geocode_source='nominatim' "
                            "WHERE id=:id"
                        ),
                        {"lat": lat, "lon": lon, "ts": datetime.utcnow(), "id": row.id},
                    )
                    updated += 1
                else:
                    # Mark as attempted so we don't retry in a tight loop
                    self.db_session.execute(
                        text(
                            "UPDATE erp_mirror_cust_shipto "
                            "SET geocoded_at=:ts, geocode_source='nominatim_no_result' "
                            "WHERE id=:id"
                        ),
                        {"ts": datetime.utcnow(), "id": row.id},
                    )
            except Exception as exc:
                print(f"[{datetime.now()}] Nominatim error for id={row.id} ({query!r}): {exc}")

            time.sleep(1.1)  # Nominatim rate limit: 1 req/sec

        try:
            self.db_session.commit()
            print(f"[{datetime.now()}] Geocoded {updated}/{len(rows)} ship-to records.")
        except Exception as exc:
            self.db_session.rollback()
            print(f"[{datetime.now()}] geocode_pending_shiptos: commit failed: {exc}")

    def run(self):
        print("Starting Local ERP Sync Service with change monitoring...")
        while True:
            started_at = datetime.utcnow()
            try:
                data = self.fetch_local_data()
                self.push_to_cloud(data)
                self.geocode_pending_shiptos(batch_size=10)
            except Exception as e:
                error_payload = self._status_payload(
                    status="error",
                    counts={"picks": 0, "work_orders": 0, "kpis": 0},
                    payload_hash=self.last_payload_hash or "",
                    push_reason="cycle_failed",
                    last_error=str(e),
                )
                self.record_status(error_payload)
                print(f"[{datetime.now()}] Sync cycle failed: {e}")

            elapsed = max(0.0, (datetime.utcnow() - started_at).total_seconds())
            sleep_seconds = max(0.0, self.sync_interval - elapsed)
            print(f"[{datetime.now()}] Sleeping for {sleep_seconds:.1f} seconds...")
            time.sleep(sleep_seconds)


if __name__ == "__main__":
    import argparse
    from app import create_app

    parser = argparse.ArgumentParser(description="ERP Sync Service")
    parser.add_argument("--once", action="store_true", help="Run a single sync cycle and exit")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        try:
            syncer = LocalSync()
            if args.once:
                print(f"[{datetime.now()}] Running single sync cycle...")
                data = syncer.fetch_local_data()
                syncer.push_to_cloud(data)
                print(f"[{datetime.now()}] Single sync cycle complete.")
            else:
                syncer.run()
        except KeyboardInterrupt:
            print("\nStopping Sync Service.")
        except Exception as e:
            print(f"[{datetime.now()}] Fatal Error: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
