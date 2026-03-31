from flask import request, url_for, jsonify

from app.Models.models import Pickster, Pick, WorkOrder
from app.Services.erp_service import ERPService
from app.Routes.main import main_bp
from app.Routes.main.helpers import localize_to_cst
from app import db


@main_bp.route('/search_results')
def search_results():
    query = request.args.get('query', '').strip()
    if not query:
        return jsonify([])

    results = []

    # 1. Sales orders / customers via ERP
    try:
        erp = ERPService()
        sales_rows = erp.get_sales_order_status(q=query, limit=8, open_only=False)
        seen_customers = {}
        for row in sales_rows:
            so_num = str(row.get('so_number') or '')
            cust_code = str(row.get('customer_code') or '')
            cust_name = str(row.get('customer_name') or '')

            # Add sales order result
            if so_num:
                results.append({
                    'title': f'SO #{so_num}',
                    'subtitle': cust_name or 'Open Order',
                    'url': url_for('main.pick_detail', so_number=so_num),
                    'type': 'order',
                })

            # Add unique customer result
            key = cust_code or cust_name
            if key and key not in seen_customers:
                seen_customers[key] = True
                results.append({
                    'title': cust_name or cust_code,
                    'subtitle': f'Customer #{cust_code}' if cust_code else 'Customer',
                    'url': url_for('sales.customer_profile', customer_number=cust_code or cust_name),
                    'type': 'customer',
                })
    except Exception:
        pass

    # 2. Work orders
    try:
        like_q = f'%{query}%'
        work_orders = WorkOrder.query.filter(
            WorkOrder.is_deleted == False,
            db.or_(
                WorkOrder.wo_id.ilike(like_q),
                WorkOrder.source_id.ilike(like_q),
                WorkOrder.item_ptr.ilike(like_q),
            )
        ).limit(5).all()
        for wo in work_orders:
            status = str(wo.wo_status or 'Open').title()
            results.append({
                'title': f'WO #{wo.wo_id}',
                'subtitle': f'SO {wo.source_id} — {wo.item_ptr or ""} — {status}',
                'url': url_for('main.supervisor_work_orders'),
                'type': 'work_order',
            })
    except Exception:
        pass

    # 3. Pick / picker search
    try:
        picks = Pick.query.join(Pickster).filter(
            (Pick.barcode_number.like(f'%{query}%')) |
            (Pickster.name.like(f'%{query}%'))
        ).limit(5).all()
        for pick in picks:
            results.append({
                'title': f'Pick — {pick.pickster.name}',
                'subtitle': f'SO {pick.barcode_number} — {localize_to_cst(pick.completed_time).strftime("%m/%d %I:%M %p") if pick.completed_time else "In Progress"}',
                'url': url_for('main.pick_detail', so_number=pick.barcode_number),
                'type': 'pick',
            })
    except Exception:
        pass

    return jsonify(results[:15])
