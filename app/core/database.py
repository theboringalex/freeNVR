import aiosqlite
from pathlib import Path
from app.config import settings

DB = settings.DB_PATH


async def init_db():
    Path(DB).parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS cameras (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                rtsp_url TEXT NOT NULL,
                substream_url TEXT,
                recording_mode TEXT NOT NULL DEFAULT 'continuous',
                enabled INTEGER NOT NULL DEFAULT 1,
                username TEXT,
                password TEXT,
                status TEXT NOT NULL DEFAULT 'stopped',
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS recordings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id INTEGER NOT NULL,
                file_path TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT,
                size_bytes INTEGER NOT NULL DEFAULT 0,
                has_motion INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                thumbnail_path TEXT,
                recording_id INTEGER,
                FOREIGN KEY (camera_id) REFERENCES cameras(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_recordings_camera_id ON recordings(camera_id);
            CREATE INDEX IF NOT EXISTS idx_recordings_start_time ON recordings(start_time);
            CREATE INDEX IF NOT EXISTS idx_events_camera_id ON events(camera_id);
            CREATE INDEX IF NOT EXISTS idx_events_timestamp ON events(timestamp);
        """)
        await db.commit()


async def get_db():
    async with aiosqlite.connect(DB) as db:
        db.row_factory = aiosqlite.Row
        yield db
