from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

from flask import current_app
from sqlalchemy import func, text

from app.Models.models import (
    AppUser,
    POSubmission,
    PurchasingActivity,
    PurchasingApproval,
    PurchasingAssignment,
    PurchasingExceptionEvent,
    PurchasingNote,
    PurchasingTask,
    PurchasingWorkQueue,
)
from app.Services.po_service import get_purchase_order
from app.auth import get_current_user_permissions
from app.extensions import db


OPEN_PO_STATUSES = {"CLOSED", "COMPLETE", "CANCELLED", "CANCELED", "VOID", "RECEIVED"}


def _safe_iso(value: Any) -> str | None:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return None


def _decimal_to_float(value: Any) -> float:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def _serialize_basic(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


class PurchasingService:
    def __init__(self) -> None:
        self.permissions = get_current_user_permissions()

    def _can_view_all_branches(self) -> bool:
        return "*" in self.permissions or "purchasing.all_branches.view" in self.permissions

    def _query_rows(self, sql: str, params: dict | None = None) -> list[dict]:
        try:
            rows = db.session.execute(text(sql), params or {}).mappings().all()
            return [dict(row) for row in rows]
        except Exception:
            current_app.logger.debug("Purchasing query failed", exc_info=True)
            return []

    def _query_one(self, sql: str, params: dict | None = None) -> dict | None:
        try:
            row = db.session.execute(text(sql), params or {}).mappings().first()
            return dict(row) if row else None
        except Exception:
            current_app.logger.debug("Purchasing single-row query failed", exc_info=True)
            return None

    def _active_assignments(self) -> list[PurchasingAssignment]:
        return (
            PurchasingAssignment.query.filter(PurchasingAssignment.active.is_(True))
            .order_by(PurchasingAssignment.system_id.asc(), PurchasingAssignment.created_at.desc())
            .all()
        )

    def _system_owner_map(self) -> dict[str, AppUser]:
        owners: dict[str, AppUser] = {}
        for assignment in self._active_assignments():
            if assignment.assignment_type != "branch" or not assignment.system_id or not assignment.buyer:
                continue
            owners.setdefault(assignment.system_id, assignment.buyer)
        return owners

    def _scoped_system_id(self, current_user: dict, system_id_param: str | None = None) -> str | None:
        system_id = (system_id_param or current_user.get("branch") or "").strip().upper()
        if self._can_view_all_branches():
            return system_id or None
        if system_id:
            return system_id
        assignment = (
            PurchasingAssignment.query.filter(
                PurchasingAssignment.active.is_(True),
                PurchasingAssignment.buyer_user_id == current_user.get("id"),
                PurchasingAssignment.assignment_type == "branch",
            )
            .order_by(PurchasingAssignment.created_at.desc())
            .first()
        )
        if assignment and assignment.system_id:
            return assignment.system_id.strip().upper()
        return "__UNASSIGNED__"

    def _open_pos(self, system_id: str | None = None, limit: int = 500) -> list[dict]:
        system_clause = ""
        params: dict[str, Any] = {"limit": limit}
        if system_id and system_id != "__UNASSIGNED__":
            system_clause = "AND COALESCE(system_id, '') = :system_id"
            params["system_id"] = system_id

        rows = self._query_rows(
            f"""
            SELECT po_number, supplier_name, supplier_code, system_id,
                   expect_date, order_date, po_status, receipt_count
            FROM app_po_search
            WHERE UPPER(COALESCE(po_status, '')) NOT IN ('CLOSED', 'COMPLETE', 'CANCELLED', 'CANCELED', 'VOID', 'RECEIVED')
              {system_clause}
            ORDER BY expect_date ASC NULLS LAST, po_number ASC
            LIMIT :limit
            """,
            params,
        )
        for row in rows:
            row["expect_date_iso"] = _safe_iso(row.get("expect_date"))
            row["order_date_iso"] = _safe_iso(row.get("order_date"))
        return rows

    def _suggested_buys(self, system_id: str | None = None, limit: int = 200) -> list[dict]:
        system_clause = ""
        params: dict[str, Any] = {"limit": limit}
        if system_id and system_id != "__UNASSIGNED__":
            system_clause = "AND COALESCE(system_id, '') = :system_id"
            params["system_id"] = system_id

        rows = self._query_rows(
            f"""
            SELECT suggestion_number, supplier_name, buyer_id, system_id, status,
                   total_amount, generated_at
            FROM erp_mirror_ppo_header
            WHERE 1=1 {system_clause}
            ORDER BY generated_at DESC NULLS LAST
            LIMIT :limit
            """,
            params,
        )
        for row in rows:
            row["generated_at"] = _safe_iso(row.get("generated_at"))
            row["total_amount"] = _decimal_to_float(row.get("total_amount"))
        return rows

    def _supplier_watchlist(self, system_id: str | None = None) -> list[dict]:
        overdue = defaultdict(lambda: {"supplier_name": "", "late_po_count": 0, "system_id": None})
        for row in self._open_pos(system_id=system_id, limit=800):
            expect_date = row.get("expect_date")
            supplier_name = row.get("supplier_name") or "Unknown supplier"
            if isinstance(expect_date, datetime) and expect_date.date() < date.today():
                overdue[supplier_name]["supplier_name"] = supplier_name
                overdue[supplier_name]["late_po_count"] += 1
                overdue[supplier_name]["system_id"] = row.get("system_id")
        return sorted(overdue.values(), key=lambda item: item["late_po_count"], reverse=True)[:6]

    def _base_queue_query(self, system_id: str | None = None, buyer_user_id: int | None = None):
        query = PurchasingWorkQueue.query.filter(PurchasingWorkQueue.status != "resolved")
        if system_id:
            query = query.filter(PurchasingWorkQueue.system_id == system_id)
        if buyer_user_id:
            query = query.filter(PurchasingWorkQueue.buyer_user_id == buyer_user_id)
        return query

    def _derived_queue_items(self, system_id: str | None = None, buyer_user_id: int | None = None) -> list[dict]:
        today = date.today()
        owner_map = self._system_owner_map()
        items: list[dict] = []

        for row in self._open_pos(system_id=system_id, limit=300):
            owner = owner_map.get((row.get("system_id") or "").strip())
            if buyer_user_id and owner and owner.id != buyer_user_id:
                continue
            expect_date = row.get("expect_date")
            if isinstance(expect_date, datetime) and expect_date.date() < today:
                items.append({
                    "id": f"virtual-overdue-{row.get('po_number')}",
                    "queue_type": "overdue_po",
                    "reference_type": "po",
                    "reference_number": row.get("po_number"),
                    "po_number": row.get("po_number"),
                    "system_id": row.get("system_id"),
                    "supplier_name": row.get("supplier_name"),
                    "title": f"Follow up on overdue PO {row.get('po_number')}",
                    "description": f"Expected {expect_date.date().isoformat()} and still open.",
                    "status": "open",
                    "priority": "high",
                    "severity": "high",
                    "due_at": expect_date.isoformat(),
                    "buyer_name": owner.display_name if owner else None,
                })

        for sub in (
            POSubmission.query.filter(POSubmission.status == "pending")
            .order_by(POSubmission.created_at.desc())
            .limit(50)
            .all()
        ):
            if system_id and (sub.branch or "").upper() != system_id.upper():
                continue
            owner = owner_map.get((sub.branch or "").strip())
            if buyer_user_id and owner and owner.id != buyer_user_id:
                continue
            items.append({
                "id": f"virtual-checkin-{sub.id}",
                "queue_type": "receiving_checkin",
                "reference_type": "submission",
                "reference_number": sub.id,
                "po_number": sub.po_number,
                "system_id": (sub.branch or "").strip().upper() or None,
                "supplier_name": sub.supplier_name,
                "title": f"Review receiving evidence for PO {sub.po_number}",
                "description": sub.notes or "Warehouse submitted a new PO check-in.",
                "status": "open",
                "priority": sub.priority or "medium",
                "severity": "medium",
                "due_at": _safe_iso(sub.created_at),
                "buyer_name": owner.display_name if owner else None,
            })

        for suggestion in self._suggested_buys(system_id=system_id, limit=60):
            status = (suggestion.get("status") or "").lower()
            if status and status not in {"pending", "review", "saved", "draft", "open"}:
                continue
            items.append({
                "id": f"virtual-spo-{suggestion.get('suggestion_number')}",
                "queue_type": "suggested_buy",
                "reference_type": "suggested_po",
                "reference_number": suggestion.get("suggestion_number"),
                "po_number": None,
                "system_id": suggestion.get("system_id"),
                "supplier_name": suggestion.get("supplier_name"),
                "title": f"Review suggested buy {suggestion.get('suggestion_number')}",
                "description": f"Supplier {suggestion.get('supplier_name') or 'Unknown'}",
                "status": "open",
                "priority": "medium",
                "severity": "medium",
                "due_at": _safe_iso(suggestion.get("generated_at")),
                "buyer_name": suggestion.get("buyer_id"),
            })

        items.sort(key=lambda item: ((item.get("priority") != "high"), item.get("due_at") or "9999"))
        return items

    def list_work_queue(self, current_user: dict, system_id: str | None = None, include_virtual: bool = True) -> list[dict]:
        scoped_system_id = self._scoped_system_id(current_user, system_id)
        buyer_user_id = current_user["id"] if "purchasing" in (current_user.get("roles") or []) else None
        if self._can_view_all_branches():
            buyer_user_id = None

        rows = []
        query = self._base_queue_query(system_id=scoped_system_id, buyer_user_id=buyer_user_id).order_by(
            PurchasingWorkQueue.priority.desc(),
            PurchasingWorkQueue.due_at.asc().nulls_last(),
            PurchasingWorkQueue.created_at.desc(),
        )
        for item in query.limit(200).all():
            rows.append({
                "id": item.id,
                "queue_type": item.queue_type,
                "reference_type": item.reference_type,
                "reference_number": item.reference_number,
                "po_number": item.po_number,
                "system_id": item.system_id,
                "supplier_name": item.supplier_name,
                "title": item.title,
                "description": item.description,
                "status": item.status,
                "priority": item.priority,
                "severity": item.severity,
                "due_at": _safe_iso(item.due_at),
                "buyer_name": item.buyer.display_name if item.buyer else None,
            })
        if include_virtual:
            rows.extend(self._derived_queue_items(system_id=scoped_system_id, buyer_user_id=buyer_user_id))
        rows.sort(key=lambda item: (item.get("status") == "resolved", item.get("priority") != "high", item.get("due_at") or "9999"))
        return rows[:250]

    def get_manager_dashboard(self, current_user: dict, system_id: str | None = None) -> dict:
        scoped_system_id = self._scoped_system_id(current_user, system_id)
        open_pos = self._open_pos(system_id=scoped_system_id, limit=600)
        queue = self.list_work_queue(current_user, system_id=scoped_system_id, include_virtual=True)
        suggested = self._suggested_buys(system_id=scoped_system_id, limit=200)

        overdue_count = 0
        spend_at_risk = 0.0
        branch_health_map: dict[str, dict[str, Any]] = defaultdict(lambda: {
            "system_id": "",
            "open_pos": 0,
            "overdue_pos": 0,
            "issues": 0,
        })
        for row in open_pos:
            branch_system_id = (row.get("system_id") or "UNASSIGNED").strip() or "UNASSIGNED"
            branch_health_map[branch_system_id]["system_id"] = branch_system_id
            branch_health_map[branch_system_id]["open_pos"] += 1
            expect_date = row.get("expect_date")
            if isinstance(expect_date, datetime) and expect_date.date() < date.today():
                overdue_count += 1
                branch_health_map[branch_system_id]["overdue_pos"] += 1

        for item in queue:
            branch_system_id = (item.get("system_id") or "UNASSIGNED").strip() or "UNASSIGNED"
            branch_health_map[branch_system_id]["system_id"] = branch_system_id
            branch_health_map[branch_system_id]["issues"] += 1

        spend_row = self._query_one(
            """
            SELECT COALESCE(SUM(COALESCE(open_amount, total_amount, 0)), 0) AS spend_at_risk
            FROM app_po_header
            WHERE UPPER(COALESCE(po_status, '')) NOT IN ('CLOSED', 'COMPLETE', 'CANCELLED', 'CANCELED', 'VOID', 'RECEIVED')
              AND (:system_id IS NULL OR :system_id = '__UNASSIGNED__' OR COALESCE(system_id, '') = :system_id)
            """,
            {"system_id": scoped_system_id},
        )
        if spend_row:
            spend_at_risk = _decimal_to_float(spend_row.get("spend_at_risk"))

        workload: dict[str, dict[str, Any]] = defaultdict(lambda: {"buyer_name": "Unassigned", "open_items": 0, "overdue_items": 0, "blocked_approvals": 0})
        for assignment in self._active_assignments():
            buyer_name = assignment.buyer.display_name if assignment.buyer else "Unassigned"
            workload[buyer_name]["buyer_name"] = buyer_name
        for item in queue:
            buyer_name = item.get("buyer_name") or "Unassigned"
            workload[buyer_name]["buyer_name"] = buyer_name
            workload[buyer_name]["open_items"] += 1
            due_at = item.get("due_at")
            if due_at and str(due_at)[:10] < date.today().isoformat():
                workload[buyer_name]["overdue_items"] += 1

        for approval in PurchasingApproval.query.filter(PurchasingApproval.status == "pending").all():
            if scoped_system_id and (approval.system_id or "").upper() != scoped_system_id.upper():
                continue
            approver_name = approval.approver.display_name if approval.approver else "Unassigned"
            workload[approver_name]["buyer_name"] = approver_name
            workload[approver_name]["blocked_approvals"] += 1

        activity = self.get_recent_activity(current_user, system_id=scoped_system_id, limit=8)

        return {
            "header": {
                "branch": scoped_system_id or "ALL",
                "buyer_load": len([item for item in workload.values() if item["open_items"] > 0]),
                "open_approvals": len([approval for approval in PurchasingApproval.query.filter(PurchasingApproval.status == "pending").all() if not scoped_system_id or (approval.system_id or "").upper() == scoped_system_id.upper()]),
                "supplier_alerts": len(self._supplier_watchlist(system_id=scoped_system_id)),
            },
            "kpis": {
                "open_pos": len(open_pos),
                "overdue_pos": overdue_count,
                "suggested_buys_pending": len(suggested),
                "receiving_issues": len([item for item in queue if item["queue_type"] in {"receiving_checkin", "receiving_discrepancy"}]),
                "spend_at_risk": spend_at_risk,
            },
            "branch_health": sorted(branch_health_map.values(), key=lambda item: item["system_id"]),
            "buyer_workload": sorted(workload.values(), key=lambda item: item["open_items"], reverse=True)[:8],
            "supplier_watchlist": self._supplier_watchlist(system_id=scoped_system_id),
            "priority_exceptions": queue[:6],
            "recent_activity": activity,
        }

    def get_buyer_workspace(self, current_user: dict, system_id: str | None = None) -> dict:
        scoped_system_id = self._scoped_system_id(current_user, system_id)
        queue = self.list_work_queue(current_user, system_id=scoped_system_id, include_virtual=True)
        suggested = [item for item in queue if item["queue_type"] == "suggested_buy"]
        open_po_items = [item for item in queue if item["reference_type"] == "po"]
        receiving_issues = [item for item in queue if item["queue_type"] in {"receiving_checkin", "receiving_discrepancy"}]
        approvals = PurchasingApproval.query.filter(PurchasingApproval.status == "pending")
        if scoped_system_id:
            approvals = approvals.filter(PurchasingApproval.system_id == scoped_system_id)
        waiting_approval = approvals.count()

        priorities = queue[:3]
        quick_insights = [
            {"label": "POs linked to customer demand", "value": len([item for item in open_po_items if item.get("description") and "customer" in item["description"].lower()])},
            {"label": "Suppliers with repeat delays", "value": len({item.get("supplier_name") for item in open_po_items if item.get("priority") == "high"})},
            {"label": "Branch transfer opportunities", "value": "Not available yet"},
        ]

        shortcuts = [
            {"label": "Browse Suggested Buys", "endpoint": "purchasing.suggested_buys"},
            {"label": "Review Receiving Evidence", "endpoint": "po.review_dashboard"},
        ]
        if self._can_view_all_branches():
            shortcuts.insert(0, {"label": "Open Manager Dashboard", "endpoint": "purchasing.manager_dashboard"})

        return {
            "header": {
                "branch": scoped_system_id or current_user.get("branch") or "ALL",
                "buyer_name": current_user.get("display_name") or current_user.get("email") or "Buyer",
                "priority_count": len([item for item in queue if item.get("priority") == "high"]),
            },
            "tabs": {
                "suggested_buys": len(suggested),
                "open_pos": len(open_po_items),
                "due_today": len([item for item in queue if (item.get("due_at") or "")[:10] == date.today().isoformat()]),
                "receiving_issues": len(receiving_issues),
                "waiting_approval": waiting_approval,
            },
            "priorities": priorities,
            "queue": queue[:25],
            "quick_insights": quick_insights,
            "shortcuts": shortcuts,
        }

    def get_recent_activity(self, current_user: dict, system_id: str | None = None, limit: int = 10) -> list[dict]:
        activities: list[dict] = []
        for row in (
            PurchasingActivity.query.order_by(PurchasingActivity.created_at.desc()).limit(limit).all()
        ):
            if system_id and (row.system_id or "").upper() != system_id.upper():
                continue
            activities.append({
                "when": _safe_iso(row.created_at),
                "summary": row.summary,
                "activity_type": row.activity_type,
                "po_number": row.po_number,
            })

        if len(activities) < limit:
            subs = (
                POSubmission.query.order_by(POSubmission.created_at.desc())
                .limit(limit)
                .all()
            )
            for sub in subs:
                if system_id and (sub.branch or "").upper() != system_id.upper():
                    continue
                activities.append({
                    "when": _safe_iso(sub.created_at),
                    "summary": f"New PO check-in for {sub.po_number}",
                    "activity_type": "checkin",
                    "po_number": sub.po_number,
                })
        activities.sort(key=lambda item: item.get("when") or "", reverse=True)
        return activities[:limit]

    def get_po_workspace(self, po_number: str) -> dict:
        po_number = (po_number or "").strip().upper()
        po_payload = get_purchase_order(po_number) or {"header": {}, "lines": [], "receiving_summary": {}}

        notes = PurchasingNote.query.filter(
            (PurchasingNote.po_number == po_number) | ((PurchasingNote.entity_type == "po") & (PurchasingNote.entity_id == po_number))
        ).order_by(PurchasingNote.created_at.desc()).all()
        tasks = PurchasingTask.query.filter(PurchasingTask.po_number == po_number).order_by(PurchasingTask.due_at.asc().nulls_last()).all()
        approvals = PurchasingApproval.query.filter(PurchasingApproval.po_number == po_number).order_by(PurchasingApproval.requested_at.desc()).all()
        exceptions = PurchasingExceptionEvent.query.filter(PurchasingExceptionEvent.po_number == po_number).order_by(PurchasingExceptionEvent.created_at.desc()).all()
        submissions = POSubmission.query.filter(POSubmission.po_number == po_number).order_by(POSubmission.created_at.desc()).all()
        queue_items = PurchasingWorkQueue.query.filter(PurchasingWorkQueue.po_number == po_number).order_by(PurchasingWorkQueue.created_at.desc()).all()

        activity_rows = (
            PurchasingActivity.query.filter(PurchasingActivity.po_number == po_number)
            .order_by(PurchasingActivity.created_at.desc())
            .limit(12)
            .all()
        )
        activity = [
            {
                "when": _safe_iso(row.created_at),
                "summary": row.summary,
                "activity_type": row.activity_type,
                "po_number": row.po_number,
            }
            for row in activity_rows
        ]
        if len(activity) < 12:
            for sub in submissions[: max(0, 12 - len(activity))]:
                activity.append({
                    "when": _safe_iso(sub.created_at),
                    "summary": f"Submission {sub.status} for PO {sub.po_number}",
                    "activity_type": "checkin",
                    "po_number": sub.po_number,
                })

        return {
            "po_number": po_number,
            "po": po_payload,
            "notes": notes,
            "tasks": tasks,
            "approvals": approvals,
            "exceptions": exceptions,
            "submissions": submissions,
            "queue_items": queue_items,
            "activity": activity,
        }

    def serialize_po_workspace(self, workspace: dict) -> dict:
        def _serialize_model(model: Any, fields: list[str]) -> dict:
            payload = {}
            for field in fields:
                payload[field] = _serialize_basic(getattr(model, field))
            return payload

        return {
            "po_number": workspace["po_number"],
            "po": workspace["po"],
            "notes": [
                {
                    **_serialize_model(note, ["id", "entity_type", "entity_id", "po_number", "system_id", "body", "is_internal", "created_at"]),
                    "created_by": note.created_by.display_name if note.created_by else None,
                }
                for note in workspace["notes"]
            ],
            "tasks": [
                {
                    **_serialize_model(task, ["id", "title", "description", "po_number", "queue_item_id", "system_id", "status", "priority", "due_at", "completed_at", "created_at", "updated_at"]),
                    "assignee": task.assignee.display_name if task.assignee else None,
                    "created_by": task.created_by.display_name if task.created_by else None,
                }
                for task in workspace["tasks"]
            ],
            "approvals": [
                {
                    **_serialize_model(approval, ["id", "approval_type", "entity_type", "entity_id", "po_number", "system_id", "status", "reason", "decision_notes", "requested_at", "decided_at"]),
                    "requested_by": approval.requested_by.display_name if approval.requested_by else None,
                    "approver": approval.approver.display_name if approval.approver else None,
                }
                for approval in workspace["approvals"]
            ],
            "exceptions": [
                _serialize_model(issue, ["id", "event_type", "event_status", "po_number", "receiving_number", "queue_item_id", "system_id", "supplier_key", "severity", "summary", "details", "metadata_json", "created_at", "resolved_at"])
                for issue in workspace["exceptions"]
            ],
            "submissions": [
                {
                    "id": sub.id,
                    "po_number": sub.po_number,
                    "supplier_name": sub.supplier_name,
                    "status": sub.status,
                    "submission_type": sub.submission_type,
                    "priority": sub.priority,
                    "notes": sub.notes,
                    "branch": sub.branch,
                    "created_at": _safe_iso(sub.created_at),
                }
                for sub in workspace["submissions"]
            ],
            "queue_items": [
                _serialize_model(item, ["id", "queue_type", "reference_type", "reference_number", "po_number", "system_id", "supplier_key", "supplier_name", "title", "description", "status", "priority", "severity", "due_at", "metadata_json", "resolved_at", "created_at", "updated_at"])
                for item in workspace["queue_items"]
            ],
            "activity": workspace["activity"],
        }

    def create_note(self, current_user: dict, po_number: str, body: str) -> PurchasingNote:
        note = PurchasingNote(
            entity_type="po",
            entity_id=po_number,
            po_number=po_number,
            system_id=current_user.get("branch") or None,
            body=body.strip(),
            created_by_user_id=current_user["id"],
        )
        db.session.add(note)
        db.session.add(PurchasingActivity(
            activity_type="note_created",
            entity_type="po",
            entity_id=po_number,
            po_number=po_number,
            system_id=current_user.get("branch") or None,
            actor_user_id=current_user["id"],
            summary=f"Added note on PO {po_number}",
            after_state={"body": note.body},
        ))
        db.session.commit()
        return note

    def create_task(self, current_user: dict, payload: dict) -> PurchasingTask:
        task = PurchasingTask(
            title=(payload.get("title") or "").strip() or "Follow up",
            description=(payload.get("description") or "").strip() or None,
            po_number=(payload.get("po_number") or "").strip().upper() or None,
            system_id=(payload.get("system_id") or payload.get("branch_code") or current_user.get("branch") or "").strip().upper() or None,
            assignee_user_id=payload.get("assignee_user_id"),
            created_by_user_id=current_user["id"],
            status="open",
            priority=(payload.get("priority") or "medium").strip().lower(),
        )
        due_at = payload.get("due_at")
        if due_at:
            try:
                task.due_at = datetime.fromisoformat(due_at.replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                task.due_at = None
        db.session.add(task)
        db.session.add(PurchasingActivity(
            activity_type="task_created",
            entity_type="po" if task.po_number else "task",
            entity_id=task.po_number or "task",
            po_number=task.po_number,
            system_id=task.system_id,
            actor_user_id=current_user["id"],
            summary=f"Created task: {task.title}",
            after_state={"priority": task.priority, "due_at": _safe_iso(task.due_at)},
        ))
        db.session.commit()
        return task

    def update_approval(self, current_user: dict, approval_id: int, status: str, notes: str | None = None) -> PurchasingApproval | None:
        approval = PurchasingApproval.query.get(approval_id)
        if not approval:
            return None
        before = {"status": approval.status, "decision_notes": approval.decision_notes}
        approval.status = status
        approval.decision_notes = (notes or "").strip() or None
        approval.approver_user_id = current_user["id"]
        approval.decided_at = datetime.utcnow()
        db.session.add(PurchasingActivity(
            activity_type="approval_updated",
            entity_type=approval.entity_type,
            entity_id=approval.entity_id,
            po_number=approval.po_number,
            system_id=approval.system_id,
            actor_user_id=current_user["id"],
            summary=f"Approval {approval.id} marked {approval.status}",
            before_state=before,
            after_state={"status": approval.status, "decision_notes": approval.decision_notes},
        ))
        db.session.commit()
        return approval
