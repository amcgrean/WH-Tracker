import os
from flask import render_template, request, redirect, url_for, flash, Blueprint, jsonify
from app.Services.erp_service import ERPService
from app.Services.samsara_service import SamsaraService
from app.extensions import db
from app.Models.models import Pickster, Pick, PickTypes, WorkOrder, PickAssignment, ERPMirrorPick, ERPMirrorWorkOrder
from datetime import datetime, timedelta
from sqlalchemy import func, text
from werkzeug.security import check_password_hash, generate_password_hash
import pytz
#from pytz import timezone  # Import pytz to handle timezone conversions
# Create a Blueprint
main = Blueprint('main', __name__)

def localize_to_cst(naive_utc_datetime):
    utc_zone = pytz.timezone('UTC')
    cst_zone = pytz.timezone('America/Chicago')

    # Check if the datetime object is naive before localizing
    if naive_utc_datetime.tzinfo is None or naive_utc_datetime.tzinfo.utcoffset(naive_utc_datetime) is None:
        utc_datetime = utc_zone.localize(naive_utc_datetime)
    else:
        utc_datetime = naive_utc_datetime

    cst_datetime = utc_datetime.astimezone(cst_zone)
    return cst_datetime

def calculate_business_elapsed_time(start_time, end_time=None):
    BUSINESS_START = 7  # 7 AM
    BUSINESS_END = 17   # 5 PM
    start_time_cst = localize_to_cst(start_time)
    end_time_cst = localize_to_cst(end_time if end_time else datetime.utcnow())
    elapsed = timedelta()
    current = start_time_cst
    while current < end_time_cst:
        next_day = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = current.replace(hour=BUSINESS_END, minute=0, second=0, microsecond=0)
        start_of_day = current.replace(hour=BUSINESS_START, minute=0, second=0, microsecond=0)
        if current.hour < BUSINESS_START:
            current = start_of_day
        elif current.hour < BUSINESS_END:
            if end_time_cst < end_of_day:
                elapsed += end_time_cst - current
                break
            else:
                elapsed += end_of_day - current
                current = next_day
        else:
            current = next_day
    return elapsed  # Return the timedelta object directly
def format_elapsed_time(start_time, end_time=None):
    # Define business hours in CST
    BUSINESS_START = 7  # 7 AM
    BUSINESS_END = 17   # 5 PM

    # Localize the start time to CST
    start_time_cst = localize_to_cst(start_time)
    end_time_cst = localize_to_cst(end_time if end_time else datetime.utcnow())

    # Initialize elapsed time
    elapsed = timedelta()

    # Loop over each day from start to end
    current = start_time_cst
    while current < end_time_cst:
        # Calculate next day to handle edge cases
        next_day = (current + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = current.replace(hour=BUSINESS_END, minute=0, second=0, microsecond=0)
        start_of_day = current.replace(hour=BUSINESS_START, minute=0, second=0, microsecond=0)

        if current.hour < BUSINESS_START:
            # If current time is before business hours, jump to business hours start
            current = start_of_day
        elif current.hour < BUSINESS_END:
            # If during business hours, calculate until end of business or end time
            if end_time_cst < end_of_day:
                elapsed += end_time_cst - current
                break
            else:
                elapsed += end_of_day - current
                current = next_day
        else:
            # If after business hours, jump to next day
            current = next_day

    # Format elapsed time into hours and minutes
    total_seconds = int(elapsed.total_seconds())
    hours, remainder = divmod(total_seconds, 3600)
    minutes, _ = divmod(remainder, 60)
    return f"{hours}h {minutes}m"

def get_pick_type_name(pick_type_id):
    # Mock-up of a function to convert pick_type_id to its name
    pick_types = {
        1: 'Yard',
        2: 'Door 1',
        3: 'Decking',
        4: 'EWP',
        5: 'Millwork',
        6: 'Will Call'
    }
    return pick_types.get(pick_type_id, 'Unknown')

###MAIN PAGE####
###MAIN PAGE####
@main.route('/')
def work_center():
    return render_template('workcenter.html')

@main.route('/pick_tracker')
def index():
    # Filter for pickers only (or show all if type is NULL for backward compat)
    pickers = Pickster.query.filter(
        (Pickster.user_type == 'picker') | (Pickster.user_type == None)
    ).order_by(Pickster.name).all()
    return render_template('index.html', pickers=pickers)

#####PICKER ADMIN STUFF#####
@main.route('/admin')
def admin():
    # Example admin page that might show all pickers for management
    pickers = Pickster.query.all()
    return render_template('admin.html', pickers=pickers)

@main.route('/add_picker', methods=['POST'])
def add_picker():
    picker_name = request.form['picker_name']
    user_type = request.form.get('user_type', 'picker')
    if picker_name:
        picker = Pickster(name=picker_name, user_type=user_type)  # Use the correct class name
        db.session.add(picker)
        db.session.commit()
        flash('Picker added successfully.')
    else:
        flash('Please enter a picker name.')
    return redirect(url_for('main.admin'))

@main.route('/edit_picker/<int:picker_id>', methods=['GET', 'POST'])
def edit_picker(picker_id):
    picker = Pickster.query.get_or_404(picker_id)
    if request.method == 'POST':
        new_name = request.form['picker_name']
        new_type = request.form.get('user_type')
        if new_name:
            picker.name = new_name
            if new_type:
                picker.user_type = new_type
            db.session.commit()
            flash('Picker name updated successfully.', 'success')
            return redirect(url_for('main.admin'))
    return render_template('edit_picker.html', picker=picker)

@main.route('/delete_picker/<int:picker_id>', methods=['POST'])
def delete_picker(picker_id):
    # Hardcoded password hash (you should generate this securely and store it, example shown below)
    password_hash = generate_password_hash('beisser1')
    # Get the password from the form
    password = request.form.get('password')
    if check_password_hash(password_hash, password):
        picker = Pickster.query.get_or_404(picker_id)  # Use the correct class name
        db.session.delete(picker)
        db.session.commit()
        flash('Picker deleted successfully.', 'success')
    else:
       flash('Incorrect password.', 'error')

    return redirect(url_for('main.admin'))

###INPUT PICK AND COMPLETE TRACKING#####
@main.route('/confirm_picker/<int:picker_id>', methods=['GET', 'POST'])
def confirm_picker(picker_id):
    picker = Pickster.query.get_or_404(picker_id)
    incomplete_picks = Pick.query.filter_by(picker_id=picker.id, completed_time=None).all()

    # Directly render the template with incomplete picks, if any
    # The POST method behavior needs to be adjusted based on your form handling
    return render_template('complete_pick.html', picker=picker, incomplete_picks=incomplete_picks)

@main.route('/input_pick/<int:picker_id>/<int:pick_type_id>', methods=['GET', 'POST'])##
def input_pick(picker_id, pick_type_id):
    picker = Pickster.query.get_or_404(picker_id)
    if request.method == 'POST':
        barcode = request.form.get('barcode')
        if barcode:
            start_time = datetime.now()
            completed_time = start_time if pick_type_id == 6 else None  # Set completed_time to start_time if pick_type_id is 6
            new_pick = Pick(
                barcode_number=barcode,
                start_time=start_time,
                picker_id=picker.id,
                pick_type_id=pick_type_id,
                completed_time=completed_time
            )
            db.session.add(new_pick)
            db.session.commit()
            flash('Pick added successfully.')
            return redirect(url_for('main.index'))  # Redirect as needed
        else:
            flash('Barcode is required.', 'error')
    return render_template('input_pick.html', picker=picker, pick_type_id=pick_type_id)

@main.route('/complete_pick/<int:pick_id>', methods=['GET', 'POST'])
def complete_pick(pick_id):
    pick = Pick.query.get_or_404(pick_id)  # Retrieves the pick or shows a 404 error

    if request.method == 'POST':
        # Updating the completed_time to now
        pick.completed_time = datetime.utcnow()  # Consider using UTC
        db.session.commit()
        flash('Pick completed successfully.')
        return redirect(url_for('main.index'))
    else:
        # For GET request, show a confirmation page or directly complete the pick
        return render_template('complete_pick.html', pick=pick)

@main.route('/start_pick/<int:picker_id>/<int:pick_type_id>', methods=['POST'])
def start_pick(picker_id, pick_type_id):
    picker = Pickster.query.get_or_404(picker_id)
    barcode = request.form.get('barcode')
    if not barcode:
        flash('Barcode is required.', 'error')
        return redirect(url_for('main.index'))  # Adjust redirect as needed

    start_time = datetime.utcnow()  # Consistently use UTC for all datetime records
    completed_time = start_time if pick_type_id == 6 else None  # Automatically complete if type_id is 6

    new_pick = Pick(
        barcode_number=barcode,
        start_time=start_time,
        completed_time=completed_time,
        picker_id=picker.id,
        pick_type_id=pick_type_id
    )
    db.session.add(new_pick)
    db.session.commit()
    flash('Pick started successfully.')
    return redirect(url_for('main.index'))

# Add logging to debug
import logging
logging.basicConfig(level=logging.DEBUG)


###OPEN PICKS####
@main.route('/api/pickers_picks')
def api_pickers_picks():
    today = datetime.now().date()
    five_days_ago = today - timedelta(days=5)

    will_call_type_id = 6

    # Count of all completed picks today excluding will call picks
    today_count = Pick.query.filter(
        func.date(Pick.completed_time) == today,
        Pick.pick_type_id != will_call_type_id  # Exclude will call picks
    ).count()

    # Debug: Ensure that the correct pick_type_id is being targeted

    print("Using pick_type_id for will call:", will_call_type_id)

    # Count for will call tickets today
    will_call_count = Pick.query.filter(
        func.date(Pick.completed_time) == today,
        Pick.pick_type_id == will_call_type_id
    ).count()

    print("Will Call Count for today:", will_call_count)  # Debug output

    # Average count of completed picks over the last 5 days excluding will call picks
    recent_counts = db.session.query(
        func.date(Pick.completed_time), func.count('*').label('daily_count')
    ).filter(
        func.date(Pick.completed_time) >= five_days_ago,
        func.date(Pick.completed_time) < today,
        Pick.pick_type_id != will_call_type_id  # Exclude will call picks
    ).group_by(
        func.date(Pick.completed_time)
    ).all()

    average_count = sum(count for _, count in recent_counts) / len(recent_counts) if recent_counts else 0

    data = []
    pickers = Pickster.query.order_by(Pickster.name).all()
    for picker in pickers:
        open_picks = Pick.query.filter_by(picker_id=picker.id, completed_time=None)\
                               .order_by(Pick.start_time.asc()).all()  # Sorting by start time

        for pick in open_picks:
            start_time_localized = localize_to_cst(pick.start_time)
            data.append({
                'barcode_number': pick.barcode_number,
                'start_time': start_time_localized.strftime('%Y-%m-%d %I:%M %p %Z'),
                'elapsed_time': format_elapsed_time(start_time_localized),
                'picker_name': picker.name,
                'pick_type': get_pick_type_name(pick.pick_type_id)
            })

    return jsonify({
        "picks": data,
        "today_count": today_count,
        "will_call_count": will_call_count,
        "average_count": average_count
    })



@main.route('/pickers_picks')
def pickers_picks():
    today = datetime.now().date()  ###new insert 7.9.24 2pm
    five_days_ago = today - timedelta(days=5)

    # Count of completed picks today
    today_count = Pick.query.filter(
        func.date(Pick.completed_time) == today
    ).count()

    # Average count of completed picks over the last 5 days
    recent_counts = db.session.query(
        func.date(Pick.completed_time), func.count('*').label('daily_count')
    ).filter(
        func.date(Pick.completed_time) >= five_days_ago,
        func.date(Pick.completed_time) < today
    ).group_by(
        func.date(Pick.completed_time)
    ).all()

    # Calculate average
    if recent_counts:
        average_count = sum(count for _, count in recent_counts) / len(recent_counts)
    else:
        average_count = 0

    # Pass the counts to the template #new insert

    return render_template('pickers_picks.html', today_count=today_count, average_count=average_count)

####PICK STATS#####
@main.route('/api/picks')
def api_picks():
    data = []
    picker_id = request.args.get('picker_id')

    if picker_id:
        picker = Pickster.query.get(picker_id)
        if not picker:
            return jsonify({'error': 'Picker not found'}), 404
        pickers = [picker]
    else:
        pickers = Pickster.query.order_by(Pickster.name).all()

    for picker in pickers:
        open_picks = Pick.query.filter_by(picker_id=picker.id, completed_time=None)\
                               .order_by(Pick.id.asc()).all()  # Sorting by ID

        picks_data = [{
            'barcode_number': pick.barcode_number,
            'start_time': localize_to_cst(pick.start_time).strftime('%Y-%m-%d %I:%M %p %Z'),  # Localizing and formatting time
            'elapsed_time': calculate_business_elapsed_time(pick.start_time),
            'picker_name': picker.name,
            'pick_type': get_pick_type_name(pick.pick_type_id)  # Using function to get pick type name
        } for pick in open_picks]

        data.extend(picks_data)

    return jsonify(data)

@main.route('/picker_stats', methods=['GET'])
def picker_stats():
    sort_by = request.args.get('sort', 'id')
    order = request.args.get('order', 'asc')
    period = request.args.get('period', 'custom')

    today = datetime.now().date()
    if period == '7days':
        start_date = today - timedelta(days=7)
        end_date = today
    elif period == '30days':
        start_date = today - timedelta(days=30)
        end_date = today
    elif period == 'ytd':
        start_date = datetime(today.year, 1, 1)
        end_date = today
    else:
        start_date_str = request.args.get('start_date', (today - timedelta(days=7)).strftime('%Y-%m-%d'))
        end_date_str = request.args.get('end_date', today.strftime('%Y-%m-%d'))
        start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()

    query_end_date = end_date + timedelta(days=1)

    query_end_date = end_date + timedelta(days=1)

    # 1. Overall Stats
    total_picks = Pick.query.filter(
        Pick.completed_time >= start_date,
        Pick.completed_time < query_end_date
    ).count()

    # SQLite compatible time difference in seconds
    time_diff_expr = func.strftime('%s', Pick.completed_time) - func.strftime('%s', Pick.start_time)

    avg_time = db.session.query(func.avg(time_diff_expr)).filter(
        Pick.completed_time >= start_date,
        Pick.completed_time < query_end_date
    ).scalar()

    avg_time_minutes = round(avg_time / 60, 2) if avg_time else 0

    # 2. Stats by Pick Type (Dynamic)
    type_stats_query = db.session.query(
        PickTypes.type_name,
        func.count(Pick.id).label('count'),
        func.avg(time_diff_expr).label('avg_seconds')
    ).join(Pick, Pick.pick_type_id == PickTypes.pick_type_id)\
     .filter(Pick.completed_time >= start_date, Pick.completed_time < query_end_date)\
     .group_by(PickTypes.type_name)\
     .all()
     
    type_stats = []
    for t in type_stats_query:
        type_stats.append({
            'name': t.type_name,
            'count': t.count,
            'avg_time': round(t.avg_seconds / 60, 2) if t.avg_seconds else 0
        })

    # 3. Top Pickers
    top_pickers = db.session.query(
        Pickster.name,
        func.count(Pick.id).label('pick_count')
    ).join(Pick).filter(
        Pick.completed_time >= start_date,
        Pick.completed_time < query_end_date
    ).group_by(Pickster.name).order_by(func.count(Pick.id).desc()).limit(5).all()

    # Legacy return for now, but passing extra data
    # Note: The original template expects 'stats' list for the table. 
    # We should reconstruct that table logic or update the template.
    # For now, let's keep the table logic roughly same but using the new query style if possible, 
    # OR just pass the new type_stats to be displayed *above* the table.
    
    # 4. Detailed Table Data (Existing Logic, slightly cleaned)
    picks = Pick.query.join(Pickster).filter(
        Pick.start_time >= start_date,
        Pick.completed_time < query_end_date,
        Pick.completed_time.isnot(None)
    ).all()

    picker_stats = {}
    for pick in picks:
        picker_id = pick.picker_id
        if picker_id not in picker_stats:
            picker_stats[picker_id] = {
                'id': picker_id,
                'name': pick.pickster.name,
                'yard_picks': 0, # Keep for legacy compatibility
                'will_call_picks': 0,
                'total_time': timedelta(),
                'count': 0
            }
        
        # Simple/Legacy counters (Optional: can be removed if template stops using them)
        if pick.pick_type_id == 1: 
            picker_stats[picker_id]['yard_picks'] += 1
        elif pick.pick_type_id == 6:
            picker_stats[picker_id]['will_call_picks'] += 1

        elapsed_time = pick.completed_time - pick.start_time
        picker_stats[picker_id]['total_time'] += elapsed_time
        picker_stats[picker_id]['count'] += 1

    stats_list = []
    for pid, stats in picker_stats.items():
        average_time = stats['total_time'] / stats['count'] if stats['count'] > 0 else timedelta()
        hours, remainder = divmod(average_time.total_seconds(), 3600)
        minutes = remainder // 60
        avg_picks_per_day = stats['count'] / ((end_date - start_date).days or 1)

        stats_list.append({
            'id': stats['id'],
            'name': stats['name'],
            'yard_picks': stats['yard_picks'],
            'will_call_picks': stats['will_call_picks'],
            'avg_pick_time': f"{int(hours)}:{int(minutes):02d}",
            'avg_picks_per_day': round(avg_picks_per_day, 2)
        })

    return render_template(
        'picker_stats.html',
        stats=stats_list,
        type_stats=type_stats, # New data
        total_picks=total_picks, # New data
        avg_time=avg_time_minutes, # New data
        top_pickers=top_pickers, # New data
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d'),
        order=order,
        period=period
    )


@main.route('/picker_details/<int:picker_id>')
def picker_details(picker_id):
    picker = Pickster.query.get_or_404(picker_id)
    picks = Pick.query.filter_by(picker_id=picker_id).order_by(Pick.start_time.desc()).all()

    # Enrich picks with ERP data
    so_numbers = [p.barcode_number for p in picks]
    erp = ERPService()
    hist_data = erp.get_historical_so_summary(so_numbers=so_numbers) if so_numbers else []
    erp_map = {item['so_number']: item for item in hist_data}

    # Convert and format the pick times
    updated_picks = []
    for pick in picks:
        start_time_cst = localize_to_cst(pick.start_time)
        time_to_complete = "In progress"
        if pick.completed_time:
            time_to_complete = format_elapsed_time(pick.start_time, pick.completed_time)

        erp_info = erp_map.get(pick.barcode_number, {})

        updated_picks.append({
            'barcode_number': pick.barcode_number,
            'customer_name': erp_info.get('customer_name', 'Unknown'),
            'reference': erp_info.get('reference', ''),
            'start_time': start_time_cst.strftime('%Y-%m-%d %I:%M %p %Z'),
            'time_to_complete': time_to_complete
        })

    return render_template('picker_details.html', picker=picker, picks=updated_picks)

@main.route('/search_results')
def search_results():
    query = request.args.get('query', '')
    if query:
        # Perform search with explicit join and filter by picker name or barcode number
        picks = Pick.query.join(Pickster).filter(
            (Pick.barcode_number.like(f'%{query}%')) |
            (Pickster.name.like(f'%{query}%'))
        ).all()

        # Ensure that the query results are properly formatted
        results = [
            {
                'id': pick.id,
                'name': pick.pickster.name,  # Ensure that this attribute access is correct
                'barcode': pick.barcode_number,
                'completed_time': localize_to_cst(pick.completed_time).strftime('%m/%d %I:%M %p') if pick.completed_time else 'Not Completed'

            }
            for pick in picks
        ]
        return jsonify(results)
    return jsonify([])

@main.route('/api/sync', methods=['POST'])
def sync_erp_data():
    api_key = request.headers.get('X-API-KEY')
    # Simple security check
    if not api_key or api_key != os.environ.get('SYNC_API_KEY'):
        return jsonify({'error': 'Unauthorized'}), 401

    data = request.json
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    try:
        # Determine if we should clear existing data (default to True for backward compatibility)
        should_reset = request.args.get('reset', 'true').lower() == 'true'

        # 1. Sync Picks
        if 'picks' in data:
            if should_reset:
                # Clear existing Mirror table
                db.session.query(ERPMirrorPick).delete()
            
            # Bulk insert new records
            for p in data['picks']:
                new_pick = ERPMirrorPick(
                    so_number=str(p.get('so_number')),
                    customer_name=p.get('customer_name'),
                    address=p.get('address'),
                    reference=p.get('reference'),
                    handling_code=p.get('handling_code'),
                    line_count=int(p.get('line_count', 0))
                )
                db.session.add(new_pick)

        # 2. Sync Work Orders
        if 'work_orders' in data:
            if should_reset:
                # Clear existing Mirror table
                db.session.query(ERPMirrorWorkOrder).delete()
            
            # Bulk insert new records
            for wo in data['work_orders']:
                new_wo = ERPMirrorWorkOrder(
                    wo_id=str(wo.get('wo_id')),
                    so_number=str(wo.get('so_number')),
                    description=wo.get('description'),
                    item_number=wo.get('item_number'),
                    status=wo.get('status'),
                    qty=float(wo.get('qty', 0)),  # Ensure float
                    department=wo.get('department')
                )
                db.session.add(new_wo)

        db.session.commit()
        return jsonify({'status': 'success', 'message': 'Data synced successfully'}), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500

@main.route('/api/dashboard', methods=['GET'])
def api_dashboard():
    period = request.args.get('period', default='today')

    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())  # Monday as the first day
    start_of_month = today.replace(day=1)  # First day of the current month

    def get_counts(start_date, end_date):
        query_end_date = end_date + timedelta(days=1)
        completed_picks = Pick.query.filter(
            Pick.completed_time.between(start_date, query_end_date)
        ).count()
        will_calls = Pick.query.filter(
            Pick.completed_time.between(start_date, query_end_date),
            Pick.pick_type_id == 6  # Assuming 6 is the ID for will call picks
        ).count()
        return completed_picks, will_calls

    # Gather counts
    if period == 'today':
        start_date = today
        end_date = today
    elif period == 'week':
        start_date = start_of_week
        end_date = today
    elif period == 'month':
        start_date = start_of_month
        end_date = today
    else:
        return jsonify({'error': 'Invalid period'}), 400

    today_picks, today_will_calls = get_counts(start_date, end_date)
    week_picks, week_will_calls = get_counts(start_of_week, today)
    month_picks, month_will_calls = get_counts(start_of_month, today)

    # Gather completed picks for the period
    completed_picks = Pick.query.join(Pickster).options(
        db.joinedload(Pick.pickster)
    ).filter(
        func.date(Pick.completed_time).between(start_date, end_date + timedelta(days=1))
    ).order_by(Pickster.name).all()

    completed_picks_data = [{
        'picker_name': pick.pickster.name,
        'barcode_number': pick.barcode_number,
        'pick_type': get_pick_type_name(pick.pick_type_id),
        'start_time': localize_to_cst(pick.start_time).strftime('%Y-%m-%d %I:%M %p %Z'),
        'complete_time': localize_to_cst(pick.completed_time).strftime('%Y-%m-%d %I:%M %p %Z')
    } for pick in completed_picks]

    return jsonify({
        'todayStats': {'picks': today_picks, 'willCalls': today_will_calls},
        'weekStats': {'picks': week_picks, 'willCalls': week_will_calls},
        'monthStats': {'picks': month_picks, 'willCalls': month_will_calls},
        'completedPicks': completed_picks_data
    })

@main.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


### WORK ORDER TRACKER ROUTES ###

@main.route('/work_orders')
def work_orders():
    # Page 1: Select User - Filter for Door Builders
    pickers = Pickster.query.filter_by(user_type='door_builder').order_by(Pickster.name).all()
    return render_template('work_order/user_selection.html', pickers=pickers)

@main.route('/work_orders/open/<int:user_id>')
def work_orders_open(user_id):
    # Page 2: Open Work Orders
    user = Pickster.query.get_or_404(user_id)
    open_orders = WorkOrder.query.filter_by(assigned_to_id=user.id, status='Open').order_by(WorkOrder.created_at.desc()).all()
    return render_template('work_order/open_orders.html', user=user, open_orders=open_orders)

@main.route('/work_orders/complete/<int:wo_id>', methods=['POST'])
def complete_work_order(wo_id):
    wo = WorkOrder.query.get_or_404(wo_id)
    wo.status = 'Complete'
    wo.completed_at = datetime.utcnow()
    db.session.commit()
    flash(f'Work Order {wo.work_order_number} completed!')
    return redirect(url_for('main.work_orders_open', user_id=wo.assigned_to_id))

@main.route('/work_orders/scan/<int:user_id>')
def work_order_scan(user_id):
    # Page 3: Scan Barcode
    user = Pickster.query.get_or_404(user_id)
    return render_template('work_order/scan_barcode.html', user=user)

@main.route('/work_orders/select')
def work_order_select():
    # Page 4: Select Work Orders (Live Lookup)
    user_id = request.args.get('user_id')
    barcode = request.args.get('barcode')
    user = Pickster.query.get_or_404(user_id)
    
    erp = ERPService()
    items = erp.get_work_orders_by_barcode(barcode)
    
    return render_template('work_order/select_orders.html', user=user, barcode=barcode, items=items)
@main.route('/warehouse')
def warehouse_select():
    return render_template('warehouse/select_handling.html')

@main.route('/warehouse/list')
def warehouse_list():
    code = request.args.get('code')
    erp = ERPService()
    raw_picks = erp.get_open_picks()
    
    # Filter by selected Handling Code and Group by SO
    grouped_picks = {}
    for pick in raw_picks:
        # Check if pick matches the selected code (case insensitive check just in case)
        if pick['handling_code'] and pick['handling_code'].lower() == code.lower():
            so = pick['so_number']
            
            if so not in grouped_picks:
                grouped_picks[so] = []
                
            grouped_picks[so].append(pick)
    
    return render_template('warehouse/view_picks.html', grouped_picks=grouped_picks, handling_code=code)

@main.route('/warehouse/board')
def warehouse_board():
    erp = ERPService()
    summary = erp.get_open_so_summary()
    
    assignments = PickAssignment.query.all()
    assignment_map = {a.so_number: a.picker_id for a in assignments}
    
    pickers = Pickster.query.filter_by(user_type='picker').order_by(Pickster.name).all()
    picker_map = {p.id: p for p in pickers}

    final_summary = []
    for item in summary:
        so_num = item['so_number']
        picker_id = assignment_map.get(so_num)
        item['assigned_picker'] = picker_map.get(picker_id) if picker_id else None
        final_summary.append(item)
        
    return render_template('warehouse/picks_board.html', summary=final_summary, pickers=pickers)

@main.route('/warehouse/board/orders')
def board_orders():
    """
    Main Order Board: Aggregates multiple handling codes into a single SO card.
    """
    erp = ERPService()
    raw_summary = erp.get_open_so_summary()
    
    # Aggregate by SO Number
    so_map = {}
    for item in raw_summary:
        so_num = item['so_number']
        if so_num not in so_map:
            so_map[so_num] = {
                'so_number': so_num,
                'customer_name': item['customer_name'],
                'address': item['address'],
                'reference': item['reference'],
                'line_count': 0,
                'handling_codes': set()
            }
        
        so_map[so_num]['line_count'] += item['line_count']
        if item['handling_code']:
            so_map[so_num]['handling_codes'].add(item['handling_code'])
    
    # Convert sets to sorted lists for template
    order_summary = []
    for so_num, data in so_map.items():
        data['handling_codes'] = sorted(list(data['handling_codes']))
        order_summary.append(data)
    
    # Fetch assignments (SO level)
    assignments = {a.so_number: a.picker_id for a in PickAssignment.query.all()}
    pickers = {p.id: p for p in Pickster.query.filter_by(user_type='picker').all()}
    
    for item in order_summary:
        picker_id = assignments.get(item['so_number'])
        item['assigned_picker'] = pickers.get(picker_id) if picker_id else None
        
    return render_template('warehouse/order_board.html', orders=order_summary)

@main.route('/warehouse/board/tv/<handling_code>')
def board_tv(handling_code):
    """
    Department-Specific TV Board: Shows only one handling code.
    Designed for large displays.
    """
    erp = ERPService()
    raw_summary = erp.get_open_so_summary()
    
    # Filter for specific handling code
    filtered_summary = [item for item in raw_summary if item['handling_code'] and item['handling_code'].upper() == handling_code.upper()]
    
    # Fetch assignments
    assignments = {a.so_number: a.picker_id for a in PickAssignment.query.all()}
    pickers = {p.id: p for p in Pickster.query.filter_by(user_type='picker').all()}
    
    for item in filtered_summary:
        picker_id = assignments.get(item['so_number'])
        item['assigned_picker'] = pickers.get(picker_id) if picker_id else None
        
    return render_template('warehouse/tv_board.html', summary=filtered_summary, handling_code=handling_code.upper())

@main.route('/warehouse/assign', methods=['POST'])
def assign_picker():
    so_number = request.form.get('so_number')
    picker_id = request.form.get('picker_id')
    
    # Check if assignment exists
    assignment = PickAssignment.query.filter_by(so_number=so_number).first()
    
    if not picker_id:
        # If picker_id is empty, remove assignment
        if assignment:
            db.session.delete(assignment)
    else:
        if assignment:
            assignment.picker_id = picker_id
            assignment.assigned_at = datetime.utcnow()
        else:
            new_assignment = PickAssignment(so_number=so_number, picker_id=picker_id)
            db.session.add(new_assignment)
            
    db.session.commit()
    return redirect(url_for('main.warehouse_board'))

@main.route('/warehouse/detail/<so_number>')
def pick_detail(so_number):
    erp = ERPService()
    header = erp.get_so_header(so_number)
    items = erp.get_so_details(so_number)
    return render_template('warehouse/pick_detail.html', so_number=so_number, header=header, items=items)

@main.route('/supervisor/dashboard')
def supervisor_dashboard():
    # 1. Fetch all pickers
    pickers = Pickster.query.all()
    
    # 2. Get active assignments (who is assigned to what)
    # Picks
    pick_assignments = {a.picker_id: a.so_number for a in PickAssignment.query.all()}
    # Work Orders (Production)
    wo_assignments = {wo.assigned_to_id: wo.work_order_number for wo in WorkOrder.query.filter(WorkOrder.assigned_to_id != None, WorkOrder.completed_at == None).all()}
    
    # 3. Get currently Active Picks (Started but not Completed)
    active_picks = Pick.query.filter(Pick.completed_time == None).all()
    active_map = {p.picker_id: p for p in active_picks}

    picker_data = []
    for p in pickers:
        p_info = {
            'name': p.name,
            'user_type': p.user_type,
            'status': 'idle',
            'current_task': None,
            'task_type': None,
            'active_duration': 0
        }
        
        # 1. Check Active Picks (Live "Doing")
        if p.id in active_map:
            pick = active_map[p.id]
            p_info['status'] = 'active'
            p_info['current_task'] = pick.barcode_number
            p_info['task_type'] = 'Pick'
            duration = (datetime.utcnow() - pick.start_time).total_seconds() / 60
            p_info['active_duration'] = int(duration)
        
        # 2. Check Pick Assignments (Planned)
        elif p.id in pick_assignments:
            p_info['status'] = 'assigned'
            p_info['current_task'] = pick_assignments[p.id]
            p_info['task_type'] = 'Pick'
            
        # 3. Check Work Order Assignments (Production)
        elif p.id in wo_assignments:
            p_info['status'] = 'assigned'
            p_info['current_task'] = wo_assignments[p.id]
            p_info['task_type'] = 'Production (WO)'
            
        picker_data.append(p_info)

    # 4. Recent Completed Picks
    recent_picks = Pick.query.filter(Pick.completed_time != None).order_by(Pick.completed_time.desc()).limit(10).all()
    
    # Enrich recent picks with ERP data
    recent_so_numbers = [p.barcode_number for p in recent_picks]
    erp = ERPService()
    hist_data = erp.get_historical_so_summary(so_numbers=recent_so_numbers) if recent_so_numbers else []
    erp_map = {item['so_number']: item for item in hist_data}

    return render_template('supervisor/dashboard.html', 
                          pickers=picker_data, 
                          recent_picks=recent_picks, 
                          erp_map=erp_map,
                          now=datetime.utcnow())

@main.route('/supervisor/work_orders')
def supervisor_work_orders():
    erp = ERPService()
    erp_wos = erp.get_open_work_orders()
    
    # Fetch local assignments for these WOs in chunks to avoid SQLite limit
    wo_ids = [str(wo['wo_id']) for wo in erp_wos]
    local_wos_list = []
    chunk_size = 900
    for i in range(0, len(wo_ids), chunk_size):
        chunk = wo_ids[i:i + chunk_size]
        local_wos_list.extend(WorkOrder.query.filter(WorkOrder.work_order_number.in_(chunk)).all())
    local_wos = {wo.work_order_number: wo for wo in local_wos_list}
    
    # Staff for dropdown
    staff = Pickster.query.order_by(Pickster.name).all()

    # Merge data
    final_wos = []
    for erp_wo in erp_wos:
        wo_id_str = str(erp_wo['wo_id'])
        local_wo = local_wos.get(wo_id_str)
        
        erp_wo['assigned_to'] = local_wo.assigned_to.name if local_wo and local_wo.assigned_to else None
        erp_wo['local_status'] = local_wo.status if local_wo else 'Open'
        final_wos.append(erp_wo)

    return render_template('supervisor/wo_board.html', work_orders=final_wos, staff=staff)

@main.route('/supervisor/assign_wo', methods=['POST'])
def assign_wo():
    wo_id = request.form.get('wo_id')
    staff_id = request.form.get('staff_id')
    so_number = request.form.get('so_number')
    item_number = request.form.get('item_number')
    description = request.form.get('description')

    if not wo_id:
        flash("Work Order ID is required.", "danger")
        return redirect(url_for('main.supervisor_work_orders'))

    # Check if local record exists
    local_wo = WorkOrder.query.filter_by(work_order_number=str(wo_id)).first()

    if not staff_id:
        # Clear assignment if staff_id is empty
        if local_wo:
            local_wo.assigned_to_id = None
            local_wo.status = 'Open'
    else:
        if not local_wo:
            # Create local record if it doesn't exist
            local_wo = WorkOrder(
                work_order_number=str(wo_id),
                sales_order_number=str(so_number),
                item_number=item_number,
                description=description,
                assigned_to_id=staff_id,
                status='Assigned'
            )
            db.session.add(local_wo)
        else:
            # Update existing record
            local_wo.assigned_to_id = staff_id
            local_wo.status = 'Assigned'

    db.session.commit()
    flash(f"Work Order {wo_id} updated successfully.", "success")
    return redirect(url_for('main.supervisor_work_orders'))

@main.route('/work_orders/start', methods=['POST'])
def start_work_orders():
    user_id = request.form.get('user_id')
    selected_items = request.form.getlist('selected_items')
    
    for item_str in selected_items:
        # Expected format: wo_number|item_number|description
        parts = item_str.split('|')
        if len(parts) == 3:
            wo_number, item_number, description = parts
            
            # Check if exists to avoid duplicates (simplified)
            existing = WorkOrder.query.filter_by(work_order_number=wo_number).first()
            if not existing:
                new_wo = WorkOrder(
                    sales_order_number='SO-MOCK', # In real app, pass this through
                    work_order_number=wo_number,
                    item_number=item_number,
                    description=description,
                    status='Open',
                    assigned_to_id=user_id,
                    created_at=datetime.utcnow()
                )
                db.session.add(new_wo)
    
    db.session.commit()
    flash(f'{len(selected_items)} work orders started.')
    return redirect(url_for('main.work_orders_open', user_id=user_id))


### DELIVERY BOARD ROUTES ###

@main.route('/delivery')
def delivery_board():
    """
    Main Delivery Board: KPIs, fleet status, and open deliveries list.
    """
    erp = ERPService()
    samsara = SamsaraService()

    # Get open deliveries from ERP (status 'k' orders that have delivery-related handling codes)
    deliveries = erp.get_delivery_orders()

    # Get vehicle locations from Samsara
    vehicle_locations = samsara.get_vehicle_locations()

    # Calculate KPIs
    open_delivery_count = len(deliveries)
    in_transit_count = sum(1 for loc in vehicle_locations if loc.get('speed_mph', 0) > 0)
    completed_count = 0  # TODO: Wire to ERP delivered status query
    active_trucks = len(vehicle_locations)

    return render_template('delivery/board.html',
                           deliveries=deliveries,
                           vehicle_locations=vehicle_locations,
                           open_delivery_count=open_delivery_count,
                           in_transit_count=in_transit_count,
                           completed_count=completed_count,
                           active_trucks=active_trucks)


@main.route('/delivery/map')
@main.route('/delivery/map/<branch>')
def delivery_map(branch=None):
    """
    Full-screen fleet map page designed for large TV display in dispatch office.
    Shows truck locations via Samsara GPS on an interactive map.
    Can be filtered by branch (e.g., Grimes, Birchwood).
    """
    samsara = SamsaraService()
    tag_ids = None
    display_name = "All Branches"

    if branch:
        all_tags = samsara.get_tags()
        # Search for tags matching the branch name or its common abbreviations
        # Grimes -> "Grimes", "GR"
        # Birchwood -> "Birchwood", "BW"
        if branch.lower() in ['grimes', 'gr']:
            matches = [t['id'] for t in all_tags if any(x in t['name'].upper() for x in ['GRIMES', 'GR'])]
            tag_ids = matches if matches else None
            display_name = "Grimes Branch"
        elif branch.lower() in ['birchwood', 'bw']:
            matches = [t['id'] for t in all_tags if any(x in t['name'].upper() for x in ['BIRCHWOOD', 'BW'])]
            tag_ids = matches if matches else None
            display_name = "Birchwood Branch"

    locations = samsara.get_vehicle_locations(tag_ids=tag_ids)

    moving_count = sum(1 for loc in locations if loc.get('speed_mph', 0) > 0)
    stopped_count = len(locations) - moving_count

    return render_template('delivery/map.html',
                           locations=locations,
                           moving_count=moving_count,
                           stopped_count=stopped_count,
                           current_branch=display_name,
                           branch_code=(branch or 'all').lower())


@main.route('/delivery/detail/<so_number>')
def delivery_detail(so_number):
    """
    Delivery detail page for a specific Sales Order.
    Shows SO header, line items, and delivery/truck assignment info.
    """
    erp = ERPService()
    header = erp.get_so_header(so_number)
    items = erp.get_so_details(so_number)
    return render_template('delivery/detail.html',
                           so_number=so_number,
                           header=header,
                           items=items)


@main.route('/api/delivery/locations')
@main.route('/api/delivery/locations/<branch>')
def api_delivery_locations(branch=None):
    """
    JSON API endpoint for vehicle locations (used by map auto-refresh).
    """
    samsara = SamsaraService()
    tag_ids = None

    if branch and branch.lower() != 'all':
        all_tags = samsara.get_tags()
        if branch.lower() in ['grimes', 'gr']:
            tag_ids = [t['id'] for t in all_tags if any(x in t['name'].upper() for x in ['GRIMES', 'GR'])]
        elif branch.lower() in ['birchwood', 'bw']:
            tag_ids = [t['id'] for t in all_tags if any(x in t['name'].upper() for x in ['BIRCHWOOD', 'BW'])]

    locations = samsara.get_vehicle_locations(tag_ids=tag_ids)
    return jsonify(locations)


