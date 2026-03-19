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

    def push_direct_to_db(self, data):
        from app.Models.models import ERPDeliveryKPI, ERPMirrorPick, ERPMirrorWorkOrder

        print(f"[{datetime.now()}] Starting direct mirror sync...")
        try:
            picks_data = data.get("picks", [])
            if picks_data:
                incoming_sos = list(set(str(p.get("so_number")) for p in picks_data))
                existing_picks = {}
                chunk_size = 900
                for i in range(0, len(incoming_sos), chunk_size):
                    chunk = incoming_sos[i:i + chunk_size]
                    db_picks = self.db_session.query(ERPMirrorPick).filter(ERPMirrorPick.so_number.in_(chunk)).all()
                    for p_obj in db_picks:
                        existing_picks[(p_obj.so_number, p_obj.sequence)] = p_obj

                seen_keys = set()

                for p in picks_data:
                    key = (str(p.get("so_number")), p.get("sequence"))
                    seen_keys.add(key)
                    address_text = p.get("address")

                    if key in existing_picks:
                        pick_obj = existing_picks[key]
                        address_changed = pick_obj.address != address_text
                        pick_obj.customer_name = p.get("customer_name")
                        pick_obj.address = address_text
                        pick_obj.reference = p.get("reference")
                        pick_obj.handling_code = p.get("handling_code")
                        pick_obj.item_number = p.get("item_number")
                        pick_obj.description = p.get("description")
                        pick_obj.qty = float(p.get("qty", 0))
                        pick_obj.line_count = int(p.get("line_count", 0))
                        pick_obj.so_status = p.get("so_status")
                        pick_obj.shipment_status = p.get("shipment_status")
                        pick_obj.status_flag_delivery = p.get("status_flag_delivery")
                        pick_obj.system_id = p.get("system_id")
                        pick_obj.expect_date = p.get("expect_date")
                        pick_obj.sale_type = p.get("sale_type")
                        pick_obj.ship_via = p.get("ship_via")
                        pick_obj.driver = p.get("driver")
                        pick_obj.route = p.get("route")
                        pick_obj.synced_at = datetime.utcnow()

                        if (not pick_obj.latitude or address_changed) and address_text:
                            addr_parts = [x.strip() for x in address_text.split(",")]
                            addr_line = addr_parts[0] if len(addr_parts) > 0 else address_text
                            city_line = addr_parts[1] if len(addr_parts) > 1 else ""
                            zip_line = p.get("zip", "")
                            lat, lon, geocode_status = self.geocoder.geocode_address(addr_line, city_line, zip_line)
                            if lat:
                                pick_obj.latitude = lat
                                pick_obj.longitude = lon
                                pick_obj.geocode_status = geocode_status
                            else:
                                pick_obj.geocode_status = "failed"

                        if p.get("printed_at") and not pick_obj.printed_at:
                            pick_obj.printed_at = self._parse_erp_datetime(p.get("printed_at"))
                        if p.get("staged_at") and not pick_obj.staged_at:
                            pick_obj.staged_at = self._parse_erp_datetime(p.get("staged_at"))
                        if p.get("delivered_at") and not pick_obj.delivered_at:
                            pick_obj.delivered_at = self._parse_erp_datetime(p.get("delivered_at"))
                    else:
                        new_pick = ERPMirrorPick(
                            so_number=key[0],
                            sequence=key[1],
                            customer_name=p.get("customer_name"),
                            address=address_text,
                            reference=p.get("reference"),
                            handling_code=p.get("handling_code"),
                            item_number=p.get("item_number"),
                            description=p.get("description"),
                            qty=float(p.get("qty", 0)),
                            line_count=int(p.get("line_count", 0)),
                            so_status=p.get("so_status"),
                            shipment_status=p.get("shipment_status"),
                            status_flag_delivery=p.get("status_flag_delivery"),
                            system_id=p.get("system_id"),
                            expect_date=p.get("expect_date"),
                            sale_type=p.get("sale_type"),
                            local_pick_state=p.get("local_pick_state", "Pick Printed"),
                            ship_via=p.get("ship_via"),
                            driver=p.get("driver"),
                            route=p.get("route"),
                            printed_at=self._parse_erp_datetime(p.get("printed_at")),
                            staged_at=self._parse_erp_datetime(p.get("staged_at")),
                            delivered_at=self._parse_erp_datetime(p.get("delivered_at")),
                            synced_at=datetime.utcnow(),
                        )

                        if address_text:
                            addr_parts = [x.strip() for x in address_text.split(",")]
                            addr_line = addr_parts[0] if len(addr_parts) > 0 else address_text
                            city_line = addr_parts[1] if len(addr_parts) > 1 else ""
                            zip_line = p.get("zip", "")
                            lat, lon, geocode_status = self.geocoder.geocode_address(addr_line, city_line, zip_line)
                            if lat:
                                new_pick.latitude = lat
                                new_pick.longitude = lon
                                new_pick.geocode_status = geocode_status
                            else:
                                new_pick.geocode_status = "failed"

                        self.db_session.add(new_pick)

                for key, obj in existing_picks.items():
                    if key not in seen_keys:
                        self.db_session.delete(obj)

            wos_data = data.get("work_orders", [])
            if wos_data:
                incoming_wo_ids = list(set(str(wo.get("wo_id")) for wo in wos_data))
                existing_wos = {}
                chunk_size = 900
                for i in range(0, len(incoming_wo_ids), chunk_size):
                    chunk = incoming_wo_ids[i:i + chunk_size]
                    db_wos = self.db_session.query(ERPMirrorWorkOrder).filter(ERPMirrorWorkOrder.wo_id.in_(chunk)).all()
                    for wo_obj in db_wos:
                        existing_wos[str(wo_obj.wo_id)] = wo_obj

                seen_wo_ids = set()
                for wo in wos_data:
                    wo_id = str(wo.get("wo_id"))
                    seen_wo_ids.add(wo_id)
                    if wo_id in existing_wos:
                        wo_obj = existing_wos[wo_id]
                        wo_obj.description = wo.get("description")
                        wo_obj.item_number = wo.get("item_number")
                        wo_obj.status = wo.get("status")
                        wo_obj.qty = float(wo.get("qty", 0))
                        wo_obj.department = wo.get("department")
                        wo_obj.synced_at = datetime.utcnow()
                    else:
                        new_wo = ERPMirrorWorkOrder(
                            wo_id=wo_id,
                            so_number=str(wo.get("so_number")),
                            description=wo.get("description"),
                            item_number=wo.get("item_number"),
                            status=wo.get("status"),
                            qty=float(wo.get("qty", 0)),
                            department=wo.get("department"),
                            synced_at=datetime.utcnow(),
                        )
                        self.db_session.add(new_wo)

                for wo_id, obj in existing_wos.items():
                    if wo_id not in seen_wo_ids:
                        self.db_session.delete(obj)

            kpis_data = data.get("kpis", [])
            if kpis_data:
                self.db_session.query(ERPDeliveryKPI).delete()
                for kpi in kpis_data:
                    kpi_date = self._coerce_date(kpi["date"])
                    if not kpi_date:
                        continue
                    self.db_session.add(
                        ERPDeliveryKPI(
                            date=kpi_date,
                            count=kpi["count"],
                            branch=kpi["branch"],
                        )
                    )

            self.db_session.commit()
            print(f"[{datetime.now()}] Direct mirror sync complete.")
        except Exception:
            self.db_session.rollback()
            raise

    def run(self):
        print("Starting Local ERP Sync Service with change monitoring...")
        while True:
            started_at = datetime.utcnow()
            try:
                data = self.fetch_local_data()
                self.push_to_cloud(data)
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
