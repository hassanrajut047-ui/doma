import os
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

# Use DATABASE_URL (Postgres on Railway) if available; otherwise fall back to local SQLite file
DB_PATH = os.path.join(os.path.dirname(__file__), 'analytics.db')
DATABASE_URL = os.environ.get('DATABASE_URL')

if DATABASE_URL:
    engine = create_engine(DATABASE_URL, future=True)
else:
    engine = create_engine(f"sqlite:///{DB_PATH}", future=True, connect_args={"check_same_thread": False})

CREATE_SQL = '''
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    slug TEXT NOT NULL,
    type TEXT NOT NULL,
    item_index INTEGER,
    ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
'''


def init_db():
    """Create the events table if it does not exist."""
    try:
        with engine.begin() as conn:
            conn.execute(text(CREATE_SQL))
    except SQLAlchemyError as e:
        # In rare cases log/raise depending on logging setup; for now re-raise
        raise


def record_event(slug, etype, item_index=None):
    init_db()
    with engine.begin() as conn:
        conn.execute(
            text('INSERT INTO events (slug, type, item_index) VALUES (:slug, :type, :item_index)'),
            {'slug': slug, 'type': etype, 'item_index': item_index}
        )


def record_scan(slug):
    record_event(slug, 'scan')


def record_click(slug, item_index=None):
    record_event(slug, 'click', item_index)


def get_monthly_summary(slug, year=None, month=None):
    init_db()
    now = datetime.utcnow()
    if year is None: year = now.year
    if month is None: month = now.month
    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    with engine.connect() as conn:
        scans = conn.execute(
            text('SELECT COUNT(*) as cnt FROM events WHERE slug=:slug AND type="scan" AND ts>=:start AND ts<:end'),
            {'slug': slug, 'start': start, 'end': end}
        ).scalar() or 0

        clicks = conn.execute(
            text('SELECT COUNT(*) as cnt FROM events WHERE slug=:slug AND type="click" AND ts>=:start AND ts<:end'),
            {'slug': slug, 'start': start, 'end': end}
        ).scalar() or 0

        top_items_res = conn.execute(
            text('SELECT item_index, COUNT(*) as cnt FROM events WHERE slug=:slug AND type="click" AND ts>=:start AND ts<:end GROUP BY item_index ORDER BY cnt DESC LIMIT 10'),
            {'slug': slug, 'start': start, 'end': end}
        )
        top_items = [{ 'index': r['item_index'], 'clicks': r['cnt'] } for r in top_items_res.mappings()]

    return {'year': year, 'month': month, 'scans': int(scans), 'clicks': int(clicks), 'top_items': top_items}


def get_top_items(slug, since_days=30):
    init_db()
    since = datetime.utcnow() - timedelta(days=since_days)
    with engine.connect() as conn:
        res = conn.execute(
            text('SELECT item_index, COUNT(*) as cnt FROM events WHERE slug=:slug AND type="click" AND ts>=:since GROUP BY item_index ORDER BY cnt DESC LIMIT 20'),
            {'slug': slug, 'since': since}
        )
        return [{ 'index': r['item_index'], 'clicks': r['cnt'] } for r in res.mappings()]


if __name__ == '__main__':
    init_db()
    print('Initialized analytics DB at', DATABASE_URL if DATABASE_URL else DB_PATH)
