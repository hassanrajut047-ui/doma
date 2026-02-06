import os
from functools import wraps
from flask import Flask, render_template, abort, request, redirect, url_for, session, jsonify, flash
from data import get_restaurants, get_restaurant, update_restaurant, update_menu_item, load_data, save_data, \
    create_restaurant
from QRD import generate_qr, delete_qr
import analytics
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET", "devsecret")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "adminpass")
RESTAURANT_DEFAULT_THEME = os.environ.get("RESTAURANT_DEFAULT_THEME", "default")


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect(url_for("admin_login", next=request.path))
        return f(*args, **kwargs)

    return decorated


@app.route("/")
def home():
    restaurants = get_restaurants()
    links = "".join([f"<li><a href='/{slug}'>{r['name']}</a></li>" for slug, r in restaurants.items()])
    return f"<h2>QR Menu SaaS</h2><ul>{links}</ul>"


@app.route("/<slug>")
def menu(slug):
    restaurant = get_restaurant(slug)
    if not restaurant:
        abort(404)

    # Get table number from URL if present
    table_num = request.args.get('table', type=int)

    analytics.record_scan(slug)
    qr_path = generate_qr(slug)

    return render_template(
        "menu.html",
        restaurant=restaurant,
        qr_image=qr_path,
        table_num=table_num
    )


@app.route('/api/<slug>/item/<int:index>/click', methods=['POST'])
def api_click(slug, index):
    analytics.record_click(slug, index)
    return jsonify({'ok': True})


@app.route('/api/<slug>/click', methods=['POST'])
def api_click_generic(slug):
    analytics.record_click(slug, None)
    return jsonify({'ok': True})


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    next_url = request.args.get("next") or url_for("home")
    if request.method == "POST":
        pw = request.form.get("password")
        if pw == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect(next_url)
        return render_template("admin_login.html", error="Invalid password")
    return render_template("admin_login.html", error=None)


@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/admin/<slug>")
@admin_required
def admin_panel(slug):
    restaurant = get_restaurant(slug)
    if not restaurant:
        abort(404)
    return render_template("admin.html", restaurant=restaurant, slug=slug)


@app.route("/admin/<slug>/analytics")
@admin_required
def admin_analytics(slug):
    restaurant = get_restaurant(slug)
    if not restaurant:
        abort(404)
    now = datetime.utcnow()
    report = analytics.get_monthly_summary(slug, now.year, now.month)
    for it in report['top_items']:
        idx = it['index']
        if idx is None:
            it['name'] = 'General'
        else:
            try:
                it['name'] = restaurant['menu'][idx]['name']
            except Exception:
                it['name'] = f'Item {idx}'
    return render_template('admin_analytics.html', restaurant=restaurant, report=report, slug=slug)


# ==================== TABLE QR CODES ====================

@app.route("/admin/<slug>/tables")
@admin_required
def admin_tables(slug):
    """Manage table-specific QR codes."""
    restaurant = get_restaurant(slug)
    if not restaurant:
        abort(404)

    tables = restaurant.get('tables', [])
    return render_template('admin_tables.html', restaurant=restaurant, slug=slug, tables=tables)


@app.route("/admin/<slug>/tables/add", methods=["POST"])
@admin_required
def admin_add_table(slug):
    """Generate new table QR code."""
    restaurant = get_restaurant(slug)
    if not restaurant:
        abort(404)

    table_num = request.form.get('table_num', type=int)
    if not table_num or table_num < 1:
        flash('Invalid table number')
        return redirect(url_for('admin_tables', slug=slug))

    # Check if exists
    existing = [t for t in restaurant.get('tables', []) if t['num'] == table_num]
    if existing:
        flash(f'Table {table_num} already exists')
        return redirect(url_for('admin_tables', slug=slug))

    # Generate QR with table parameter
    qr_path = generate_qr(slug, table_num)

    # Save to data
    if 'tables' not in restaurant:
        restaurant['tables'] = []
    restaurant['tables'].append({
        'num': table_num,
        'qr_path': qr_path
    })
    restaurant['tables'].sort(key=lambda x: x['num'])

    update_restaurant(slug, restaurant)
    flash(f'Table {table_num} QR generated successfully')
    return redirect(url_for('admin_tables', slug=slug))


@app.route("/admin/<slug>/tables/delete/<int:table_num>")
@admin_required
def admin_delete_table(slug, table_num):
    """Delete a table QR code."""
    restaurant = get_restaurant(slug)
    if not restaurant:
        abort(404)

    # Remove from data
    tables = restaurant.get('tables', [])
    restaurant['tables'] = [t for t in tables if t['num'] != table_num]

    # Delete file
    delete_qr(slug, table_num)

    update_restaurant(slug, restaurant)
    flash(f'Table {table_num} deleted')
    return redirect(url_for('admin_tables', slug=slug))


# ==================== EXISTING API ROUTES ====================

@app.route('/signup', methods=['POST'])
def signup():
    """Public signup endpoint to create a new restaurant."""
    data = request.get_json() or {}
    slug = data.get('slug')
    if not slug:
        return jsonify({'error': 'slug required'}), 400

    if load_data().get(slug):
        return jsonify({'error': 'slug already exists'}), 400

    theme = data.get('theme') or RESTAURANT_DEFAULT_THEME
    restaurant = {
        'name': data.get('name', slug),
        'name_ur': data.get('name_ur', ''),
        'whatsapp': data.get('whatsapp', ''),
        'menu': data.get('menu', []),
        'theme': theme
    }
    success = create_restaurant(slug, restaurant, default_theme=RESTAURANT_DEFAULT_THEME)
    if not success:
        return jsonify({'error': 'creation failed'}), 500
    return jsonify({'ok': True, 'slug': slug, 'theme': theme}), 201


@app.route('/api/<slug>/theme', methods=['POST'])
@admin_required
def api_set_theme(slug):
    """Set per-restaurant theme."""
    data = request.get_json() or {}
    theme = data.get('theme')
    if theme not in (None, 'default', 'traditional'):
        return jsonify({'error': 'invalid theme'}), 400

    from data import set_restaurant_theme
    success = set_restaurant_theme(slug, theme if theme != 'default' else 'default')
    if not success:
        return jsonify({'error': 'not found'}), 404
    return jsonify({'ok': True})


@app.route("/api/<slug>/menu")
def api_get_menu(slug):
    restaurant = get_restaurant(slug)
    if not restaurant:
        return jsonify({"error": "not found"}), 404
    return jsonify(restaurant)


@app.route("/api/<slug>/item/<int:index>/update", methods=["POST"])
@admin_required
def api_update_item(slug, index):
    data = request.get_json() or {}
    allowed = {"price", "is_available", "is_chefs_special", "name", "name_ur", "image_url", "category"}
    fields = {k: v for k, v in data.items() if k in allowed}

    if "is_available" in fields:
        val = fields["is_available"]
        if isinstance(val, str):
            fields["is_available"] = val.lower() in ("1", "true", "yes")

    success = update_menu_item(slug, index, fields)
    if not success:
        return jsonify({"error": "update failed"}), 400
    return jsonify({"ok": True})


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)