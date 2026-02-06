import json
import os
import re
import threading
import tempfile
import shutil
from copy import deepcopy

DATA_FILE = os.path.join(os.path.dirname(__file__), "data.json")
VALID_SLUG_PATTERN = re.compile(r'^[a-z0-9-]+$')
VALID_ITEM_FIELDS = {'name', 'name_ur', 'price', 'image_url', 'category',
                     'is_available', 'is_chefs_special'}
VALID_THEMES = {'default', 'traditional'}
_save_lock = threading.Lock()


def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        # Backup corrupt file and start fresh
        backup = DATA_FILE + '.corrupt.' + str(int(os.time()))
        shutil.move(DATA_FILE, backup)
        return {}


def save_data(data):
    """Atomic save with locking"""
    with _save_lock:
        fd, temp_path = tempfile.mkstemp(dir=os.path.dirname(DATA_FILE))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            shutil.move(temp_path, DATA_FILE)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise


def get_restaurants():
    return load_data()


def get_restaurant(slug):
    """Returns a copy to prevent accidental mutations"""
    return deepcopy(load_data().get(slug))


def update_restaurant(slug, new_restaurant):
    if not VALID_SLUG_PATTERN.match(slug):
        return False
    data = load_data()
    data[slug] = new_restaurant
    save_data(data)
    return True


def update_menu_item(slug, index, fields):
    """Update specific fields of a menu item with validation"""
    # Validate fields
    valid_fields = {}
    for k, v in fields.items():
        if k not in VALID_ITEM_FIELDS:
            continue

        if k == 'price':
            try:
                price = float(v)
                if price < 0 or price > 999999:  # Sanity check
                    return False
                valid_fields[k] = round(price, 2)
            except (ValueError, TypeError):
                return False
        elif k in ('is_available', 'is_chefs_special'):
            valid_fields[k] = bool(v)
        elif k == 'category':
            # Normalize category
            valid_fields[k] = str(v).strip().title()
        else:
            valid_fields[k] = str(v).strip() if v else ''

    if not valid_fields:
        return False

    data = load_data()
    rest = data.get(slug)
    if not rest or 'menu' not in rest:
        return False

    try:
        idx = int(index)
        if idx < 0 or idx >= len(rest['menu']):
            return False
        rest['menu'][idx].update(valid_fields)
        save_data(data)
        return True
    except (ValueError, TypeError):
        return False


def set_restaurant_theme(slug, theme):
    """Set theme with validation"""
    if theme not in VALID_THEMES:
        return False

    data = load_data()
    rest = data.get(slug)
    if not rest:
        return False

    rest['theme'] = theme
    save_data(data)
    return True


def create_restaurant(slug, restaurant, default_theme='default'):
    """Create with validation and defaults"""
    if not VALID_SLUG_PATTERN.match(slug):
        return False

    if default_theme not in VALID_THEMES:
        default_theme = 'default'

    data = load_data()
    if slug in data:
        return False

    # Sanitize input
    rest = {
        'name': str(restaurant.get('name', slug)).strip() or slug,
        'name_ur': str(restaurant.get('name_ur', '')).strip(),
        'whatsapp': str(restaurant.get('whatsapp', '')).strip(),
        'menu': [],
        'theme': default_theme,
        'created_at': __import__('time').time()
    }

    # Validate and add menu items
    for item in restaurant.get('menu', []):
        if isinstance(item, dict) and 'name' in item:
            rest['menu'].append({
                'name': str(item.get('name', '')).strip(),
                'name_ur': str(item.get('name_ur', '')).strip(),
                'price': float(item.get('price', 0)),
                'image_url': str(item.get('image_url', '')).strip(),
                'category': str(item.get('category', 'Main Course')).strip().title() or 'Main Course',
                'is_available': bool(item.get('is_available', True)),
                'is_chefs_special': bool(item.get('is_chefs_special', False))
            })

    data[slug] = rest
    save_data(data)
    return True


def delete_restaurant(slug):
    """Delete a restaurant"""
    data = load_data()
    if slug not in data:
        return False
    del data[slug]
    save_data(data)
    return True


def get_analytics(slug):
    """Get click analytics for a restaurant"""
    data = load_data()
    rest = data.get(slug, {})
    return {
        'total_clicks': rest.get('total_clicks', 0),
        'item_clicks': rest.get('item_clicks', {})
    }


def track_click(slug, item_index=None):
    """Track a click (general or specific item)"""
    data = load_data()
    rest = data.get(slug)
    if not rest:
        return False

    if 'analytics' not in rest:
        rest['analytics'] = {'total': 0, 'items': {}}

    rest['analytics']['total'] += 1

    if item_index is not None:
        idx = str(item_index)
        rest['analytics']['items'][idx] = rest['analytics']['items'].get(idx, 0) + 1

    save_data(data)
    return True