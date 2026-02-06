import qrcode
import os

# Get the directory where THIS file is located
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_URL = os.environ.get('BASE_URL', "http://localhost:5000").strip().rstrip('/')

# QR codes go in static/qr folder
QR_DIR = os.path.join(BASE_DIR, "static", "qr")


def generate_qr(slug, table=None):
    """Generate QR code. Returns path like 'qr/slug.png'"""

    # Create directory if not exists
    os.makedirs(QR_DIR, exist_ok=True)

    # Build URL
    if table:
        url = f"{BASE_URL}/{slug}?table={table}"
        filename = f"{slug}-table-{table}.png"
    else:
        url = f"{BASE_URL}/{slug}"
        filename = f"{slug}.png"

    # Generate QR
    img = qrcode.make(url, box_size=10, border=2)

    # Save to absolute path
    filepath = os.path.join(QR_DIR, filename)
    img.save(filepath)

    print(f"✅ QR saved: {filepath}")
    return f"qr/{filename}"


def delete_qr(slug, table=None):
    """Delete QR code file."""
    filename = f"{slug}-table-{table}.png" if table else f"{slug}.png"
    filepath = os.path.join(QR_DIR, filename)
    try:
        os.remove(filepath)
        print(f"🗑️ QR deleted: {filepath}")
    except FileNotFoundError:
        pass