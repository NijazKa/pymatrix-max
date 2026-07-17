from mautrix.util.async_db import Connection, UpgradeTable

upgrade_table = UpgradeTable()


@upgrade_table.register(description="Initial schema")
async def upgrade_v1(conn: Connection) -> None:
    await conn.execute(
        '''CREATE TABLE "user" (
            mxid             TEXT PRIMARY KEY,
            max_phone        TEXT,
            max_session_file TEXT
        )'''
    )
    await conn.execute(
        '''CREATE TABLE puppet (
            max_user_id TEXT PRIMARY KEY,
            mxid        TEXT NOT NULL UNIQUE,
            name        TEXT,
            avatar_url  TEXT,
            custom_mxid TEXT UNIQUE
        )'''
    )
    await conn.execute(
        '''CREATE TABLE portal (
            chat_id   TEXT NOT NULL,
            receiver  TEXT,
            mxid      TEXT UNIQUE,
            name      TEXT,
            is_direct BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (chat_id, receiver)
        )'''
    )


@upgrade_table.register(description="Store remote MAX user ID for direct portals")
async def upgrade_v2(conn: Connection) -> None:
    await conn.execute("ALTER TABLE portal ADD COLUMN remote_user_id TEXT")


@upgrade_table.register(description="Create MAX/Matrix message mapping table")
async def upgrade_v3(conn: Connection) -> None:
    await conn.execute(
        '''CREATE TABLE message_map (
            chat_id        TEXT NOT NULL,
            receiver       TEXT NOT NULL DEFAULT '',
            max_message_id TEXT NOT NULL,
            mx_room        TEXT NOT NULL,
            mx_event       TEXT NOT NULL UNIQUE,
            is_primary     BOOLEAN NOT NULL DEFAULT FALSE,
            PRIMARY KEY (chat_id, receiver, max_message_id, mx_event)
        )'''
    )
    await conn.execute(
        "CREATE INDEX message_map_max_idx "
        "ON message_map (chat_id, receiver, max_message_id)"
    )


@upgrade_table.register(description="Create Matrix/MAX reaction mapping table")
async def upgrade_v4(conn: Connection) -> None:
    await conn.execute(
        '''CREATE TABLE reaction_map (
            mx_event        TEXT PRIMARY KEY,
            mx_room         TEXT NOT NULL,
            target_mx_event TEXT NOT NULL,
            chat_id         TEXT NOT NULL,
            receiver        TEXT NOT NULL DEFAULT '',
            max_message_id  TEXT NOT NULL,
            sender_mxid     TEXT NOT NULL,
            reaction        TEXT NOT NULL,
            origin          TEXT NOT NULL,
            active          BOOLEAN NOT NULL DEFAULT TRUE
        )'''
    )
    await conn.execute(
        "CREATE INDEX reaction_map_active_idx "
        "ON reaction_map "
        "(chat_id, receiver, max_message_id, sender_mxid, origin, active)"
    )


@upgrade_table.register(description="Persist MAX management room for auth alerts")
async def upgrade_v5(conn: Connection) -> None:
    await conn.execute('ALTER TABLE "user" ADD COLUMN management_room TEXT')


@upgrade_table.register(description="Create per-user blocked MAX chat denylist")
async def upgrade_v6(conn: Connection) -> None:
    await conn.execute(
        '''CREATE TABLE blocked_chat (
            mxid       TEXT NOT NULL,
            chat_id    TEXT NOT NULL,
            name       TEXT,
            created_at BIGINT NOT NULL,
            PRIMARY KEY (mxid, chat_id)
        )'''
    )
    await conn.execute(
        "CREATE INDEX blocked_chat_mxid_idx "
        "ON blocked_chat (mxid, created_at)"
    )


@upgrade_table.register(description="Track Matrix users of shared MAX portals")
async def upgrade_v7(conn: Connection) -> None:
    await conn.execute(
        '''CREATE TABLE portal_user (
            chat_id      TEXT NOT NULL,
            mxid         TEXT NOT NULL,
            created_at   BIGINT NOT NULL,
            last_seen_at BIGINT NOT NULL,
            PRIMARY KEY (chat_id, mxid)
        )'''
    )
    await conn.execute(
        "CREATE INDEX portal_user_mxid_idx "
        "ON portal_user (mxid, last_seen_at)"
    )


@upgrade_table.register(description="Store MAX contact phone on puppet profiles")
async def upgrade_v8(conn: Connection) -> None:
    await conn.execute("ALTER TABLE puppet ADD COLUMN phone TEXT")


@upgrade_table.register(description="Store original MAX sender metadata on message mappings")
async def upgrade_v9(conn: Connection) -> None:
    await conn.execute("ALTER TABLE message_map ADD COLUMN sender_max_id TEXT")
    await conn.execute("ALTER TABLE message_map ADD COLUMN sender_name TEXT")
    await conn.execute(
        "CREATE INDEX message_map_sender_idx "
        "ON message_map (mx_room, sender_max_id)"
    )
