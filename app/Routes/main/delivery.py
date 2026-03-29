from datetime import datetime
from flask import render_template, request, redirect, url_for, jsonify

from app.Models.models import Pick
from app.Services.erp_service import ERPService
from app.Services.samsara_service import SamsaraService
from app.branch_utils import normalize_branch
from app.Routes.main import main_bp


@main_bp.route('/delivery')
def delivery_board():
    """
    Deprecated: Redirects to the unified Delivery Tracker.
    """
    return redirect(url_for('main.sales_delivery_tracker'))


@main_bp.route('/delivery/map')
@main_bp.route('/delivery/map/<branch>')
def delivery_map(branch=None):
    """
    Full-screen fleet map page designed for large TV display in dispatch office.
    Shows truck locations via Samsara GPS on an interactive map.
    Can be filtered by branch (e.g., Grimes, Birchwood).
    """
    truck_name = request.args.get('truck')
    samsara = SamsaraService()

    branch_display_map = {
        'grimes': 'Grimes Branch', 'gr': 'Grimes Branch',
        'birchwood': 'Birchwood Branch', 'bw': 'Birchwood Branch',
        '10fd': 'Fort Dodge Branch', '20gr': 'Grimes Branch',
        '25bw': 'Birchwood Branch', '40cv': 'Coralville Branch',
    }
    display_name = branch_display_map.get((branch or '').lower(), 'All Branches')
    branch_filter = (branch or '').upper() or None

    payload = samsara.get_dispatch_vehicle_payload(branch=branch_filter)
    gps_error = payload.get('error') or payload.get('warning')

    # Normalise to the format expected by the map template
    locations = []
    for v in payload.get('vehicles', []):
        locations.append({
            'vehicle_id': v.get('id'),
            'name': v.get('name', 'Unknown'),
            'latitude': v.get('lat'),
            'longitude': v.get('lon'),
            'speed_mph': v.get('speed') or 0,
            'heading': v.get('heading') or 0,
            'time': v.get('located_at', ''),
            'address': '',
        })

    moving_count = sum(1 for loc in locations if loc.get('speed_mph', 0) > 0)
    stopped_count = len(locations) - moving_count

    return render_template('delivery/map.html',
                           locations=locations,
                           moving_count=moving_count,
                           stopped_count=stopped_count,
                           current_branch=display_name,
                           branch_code=(branch or 'all').lower(),
                           focus_truck=truck_name,
                           gps_error=gps_error)


@main_bp.route('/delivery/detail/<so_number>')
def delivery_detail(so_number):
    """
    Delivery detail page for a specific Sales Order.
    Shows SO header, line items, and delivery/truck assignment info.
    """
    erp = ERPService()
    header = erp.get_so_header(so_number)
    items = erp.get_so_details(so_number)

    # Fetch local pick timestamps if available
    local_pick = Pick.query.filter_by(barcode_number=so_number).first()
    if local_pick and header:
        header['picking_started_at'] = local_pick.start_time
        header['picking_completed_at'] = local_pick.completed_time

    return render_template('delivery/detail.html',
                           so_number=so_number,
                           header=header,
                           items=items)


@main_bp.route('/api/delivery/locations')
@main_bp.route('/api/delivery/locations/<branch>')
def api_delivery_locations(branch=None):
    """
    JSON API endpoint for vehicle locations (used by map auto-refresh).
    Returns the full dispatch payload so clients can detect GPS errors.
    """
    samsara = SamsaraService()
    branch_filter = (branch or '').upper() if branch and branch.lower() != 'all' else None
    payload = samsara.get_dispatch_vehicle_payload(branch=branch_filter)

    # Normalise to legacy list format expected by the map JS
    locations = []
    for v in payload.get('vehicles', []):
        locations.append({
            'vehicle_id': v.get('id'),
            'name': v.get('name', 'Unknown'),
            'latitude': v.get('lat'),
            'longitude': v.get('lon'),
            'speed_mph': v.get('speed') or 0,
            'heading': v.get('heading') or 0,
            'time': v.get('located_at', ''),
            'address': '',
        })

    return jsonify({
        'locations': locations,
        'count': len(locations),
        'fetched_at': payload.get('fetched_at'),
        'error': payload.get('error') or payload.get('warning'),
        'source': payload.get('source', 'unknown'),
    })


@main_bp.route('/sales/tracker')
@main_bp.route('/sales/deliveries')
@main_bp.route('/sales/deliveries/<branch>')
def sales_delivery_tracker(branch=None):
    """
    Unified Sales Delivery Tracker & Fleet Board:
    Real-time status for today's deliveries + Samsara Fleet GPS tracking.
    """
    from flask import session as flask_session
    erp = ERPService()
    samsara = SamsaraService()

    # Branch precedence: URL path > URL param > session > None
    raw_branch = branch or request.args.get('branch') or flask_session.get('selected_branch')
    normalized_branch = normalize_branch(raw_branch)
    branch_slug_map = {
        '20GR': '20gr',
        '25BW': '25bw',
        '10FD': '10fd',
        '40CV': '40cv',
    }
    current_branch = branch_slug_map.get(normalized_branch)

    deliveries = erp.get_sales_delivery_tracker(branch_id=normalized_branch)
    kpis = erp.get_delivery_kpis(branch_id=normalized_branch)

    # Get vehicle locations from Samsara for Fleet Status table
    gps_payload = samsara.get_dispatch_vehicle_payload(branch=normalized_branch or None)
    gps_error = gps_payload.get('error') or gps_payload.get('warning')
    vehicle_locations = [
        {
            'vehicle_id': v.get('id'),
            'name': v.get('name', 'Unknown'),
            'latitude': v.get('lat'),
            'longitude': v.get('lon'),
            'speed_mph': v.get('speed') or 0,
            'heading': v.get('heading') or 0,
            'time': v.get('located_at', ''),
            'address': v.get('address') or '',
        }
        for v in gps_payload.get('vehicles', [])
    ]
    active_trucks = len(vehicle_locations)
    in_transit_count = sum(1 for loc in vehicle_locations if loc.get('speed_mph', 0) > 0)

    return render_template('sales/delivery_tracker.html',
                           deliveries=deliveries,
                           kpis=kpis,
                           vehicle_locations=vehicle_locations,
                           active_trucks=active_trucks,
                           in_transit_count=in_transit_count,
                           current_branch=current_branch,
                           current_branch_code=normalized_branch or 'all',
                           gps_error=gps_error,
                           today=datetime.now().strftime('%Y-%m-%d'))
