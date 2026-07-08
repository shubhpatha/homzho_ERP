"""
routes/inventory_routes.py - Inventory item and stock movement management.
"""
from datetime import date
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from extensions import db
from models.inventory import InventoryItem, InventoryMovement
from services.accounting_service import upsert_ledger_entry
from utils.helpers import get_page_items, log_activity

inventory_bp = Blueprint('inventory', __name__, url_prefix='/inventory')

CATEGORIES = ['Filter', 'Membrane', 'Spare Part', 'Fitting', 'Chemical', 'Tool', 'Machine', 'Other']
UNITS = ['pcs', 'set', 'box', 'ltr', 'kg', 'meter']
MOVEMENT_TYPES = ['In', 'Out', 'Adjustment']
PAYMENT_MODES = ['Cash', 'UPI', 'Bank Transfer', 'Cheque', 'Online']


def _amount(value, default=0.0):
    try:
        return max(float(value or 0), 0.0)
    except (TypeError, ValueError):
        return default


@inventory_bp.route('/')
@login_required
def index():
    """Inventory item list."""
    if not current_user.has_permission('inventory'):
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard.index'))

    page = request.args.get('page', 1, type=int)
    search = request.args.get('search', '').strip()
    category_filter = request.args.get('category', '').strip()
    low_stock = request.args.get('low_stock', '').strip()

    query = InventoryItem.query.filter_by(is_active=True)
    if search:
        like = f'%{search}%'
        query = query.filter(db.or_(InventoryItem.item_name.ilike(like), InventoryItem.vendor_name.ilike(like)))
    if category_filter:
        query = query.filter(InventoryItem.category == category_filter)
    if low_stock:
        query = query.filter(InventoryItem.current_stock <= InventoryItem.reorder_level)

    query = query.order_by(InventoryItem.item_name.asc())
    pagination = get_page_items(query, page)

    all_items = InventoryItem.query.filter_by(is_active=True).all()
    total_value = sum(item.stock_value for item in all_items)
    low_stock_count = sum(1 for item in all_items if item.is_low_stock)
    recent_movements = (
        InventoryMovement.query
        .order_by(InventoryMovement.movement_date.desc(), InventoryMovement.movement_id.desc())
        .limit(8)
        .all()
    )

    return render_template(
        'inventory/index.html',
        items=pagination.items,
        pagination=pagination,
        search=search,
        category_filter=category_filter,
        low_stock=low_stock,
        categories=CATEGORIES,
        total_items=len(all_items),
        total_value=total_value,
        low_stock_count=low_stock_count,
        recent_movements=recent_movements,
        active_page='inventory',
    )


@inventory_bp.route('/add', methods=['GET', 'POST'])
@login_required
def add_item():
    """Create a new inventory item."""
    if not current_user.has_permission('inventory'):
        flash('Access denied.', 'danger')
        return redirect(url_for('inventory.index'))

    if request.method == 'POST':
        try:
            item_name = request.form['item_name'].strip()
            if InventoryItem.query.filter_by(item_name=item_name).first():
                flash(f'Inventory item "{item_name}" already exists.', 'danger')
                return redirect(url_for('inventory.add_item'))

            item = InventoryItem(
                item_name=item_name,
                category=request.form.get('category') or 'Spare Part',
                unit=request.form.get('unit') or 'pcs',
                current_stock=_amount(request.form.get('current_stock')),
                reorder_level=_amount(request.form.get('reorder_level')),
                unit_cost=_amount(request.form.get('unit_cost')),
                vendor_name=request.form.get('vendor_name', '').strip(),
                remarks=request.form.get('remarks', '').strip(),
            )
            db.session.add(item)
            db.session.commit()
            log_activity(current_user.username, 'Add', 'Inventory', item.item_id, f'Added item {item.item_name}', request.remote_addr)
            flash('Inventory item added.', 'success')
            return redirect(url_for('inventory.index'))
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error adding inventory item: {exc}', exc_info=True)
            flash(f'Error: {exc}', 'danger')

    return render_template('inventory/add.html', categories=CATEGORIES, units=UNITS, active_page='inventory')


@inventory_bp.route('/<int:item_id>/movement', methods=['GET', 'POST'])
@login_required
def add_movement(item_id):
    """Record stock in, stock out, or stock adjustment."""
    if not current_user.has_permission('inventory'):
        flash('Access denied.', 'danger')
        return redirect(url_for('inventory.index'))

    item = db.get_or_404(InventoryItem, item_id)
    if request.method == 'POST':
        try:
            movement_date = date.fromisoformat(request.form['movement_date'])
            movement_type = request.form['movement_type']
            quantity = _amount(request.form.get('quantity'))
            unit_cost = _amount(request.form.get('unit_cost'), item.unit_cost)
            if quantity <= 0:
                flash('Quantity must be greater than zero.', 'danger')
                return redirect(url_for('inventory.add_movement', item_id=item_id))

            if movement_type == 'In':
                item.current_stock += quantity
                if unit_cost > 0:
                    item.unit_cost = unit_cost
            elif movement_type == 'Out':
                if quantity > item.current_stock:
                    flash('Stock out quantity cannot exceed current stock.', 'danger')
                    return redirect(url_for('inventory.add_movement', item_id=item_id))
                item.current_stock -= quantity
            elif movement_type == 'Adjustment':
                item.current_stock = quantity
            else:
                flash('Invalid movement type.', 'danger')
                return redirect(url_for('inventory.add_movement', item_id=item_id))

            movement = InventoryMovement(
                item_id=item.item_id,
                movement_date=movement_date,
                movement_type=movement_type,
                quantity=quantity,
                unit_cost=unit_cost,
                reference_type=request.form.get('reference_type', '').strip(),
                notes=request.form.get('notes', '').strip(),
                created_by=current_user.username,
            )
            db.session.add(movement)
            db.session.flush()

            if movement_type == 'In' and movement.total_value > 0:
                upsert_ledger_entry(
                    entry_date=movement_date,
                    entry_type='Expense',
                    category='Inventory Purchase',
                    amount=movement.total_value,
                    payment_mode=request.form.get('payment_mode'),
                    party_name=item.vendor_name,
                    description=f'{quantity:g} {item.unit} {item.item_name}',
                    source_type='inventory_movement',
                    source_id=movement.movement_id,
                    reference_no=str(movement.movement_id),
                    created_by=current_user.username,
                )

            db.session.commit()
            log_activity(current_user.username, 'Add', 'InventoryMovement', movement.movement_id, f'{movement_type} {quantity:g} {item.unit} {item.item_name}', request.remote_addr)
            flash('Stock movement recorded.', 'success')
            return redirect(url_for('inventory.index'))
        except Exception as exc:
            db.session.rollback()
            current_app.logger.error(f'Error adding inventory movement: {exc}', exc_info=True)
            flash(f'Error: {exc}', 'danger')

    movements = item.movements.order_by(db.desc('movement_date'), db.desc('movement_id')).limit(10).all()
    return render_template(
        'inventory/movement.html',
        item=item,
        movements=movements,
        movement_types=MOVEMENT_TYPES,
        payment_modes=PAYMENT_MODES,
        movement_date_default=date.today().isoformat(),
        active_page='inventory',
    )