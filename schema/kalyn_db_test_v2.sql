-- OPTIONAL: start completely fresh
DROP SCHEMA IF EXISTS kalyn_db_test CASCADE;

-- ============================================================================
-- SCHEMA
-- ============================================================================
CREATE SCHEMA kalyn_db_test;

-- ============================================================================
-- MASTER DATA TABLES
-- ============================================================================

CREATE TABLE kalyn_db_test.color
(
    id    SERIAL PRIMARY KEY,
    color VARCHAR NOT NULL UNIQUE
);

CREATE TABLE kalyn_db_test.category
(
    id       SERIAL PRIMARY KEY,
    category VARCHAR NOT NULL UNIQUE,
    code     VARCHAR NOT NULL UNIQUE
);

CREATE TABLE kalyn_db_test.item_name
(
    id        SERIAL PRIMARY KEY,
    item_name VARCHAR NOT NULL UNIQUE
);

CREATE TABLE kalyn_db_test.store
(
    id   SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
);

-- Seed stores
INSERT INTO kalyn_db_test.store (name)
VALUES ('banda'),
       ('karawang'),
       ('purwakarta'),
       ('gudang')
ON CONFLICT (name) DO NOTHING;

-- ============================================================================
-- ITEM MASTER (WITH SKU)
-- ============================================================================

CREATE TABLE kalyn_db_test.item
(
    id           SERIAL PRIMARY KEY,

    item_name_id INTEGER NOT NULL
        REFERENCES kalyn_db_test.item_name (id),

    category_id  INTEGER NOT NULL
        REFERENCES kalyn_db_test.category (id),

    color_id     INTEGER NOT NULL
        REFERENCES kalyn_db_test.color (id),

    created_year INTEGER NOT NULL
        DEFAULT EXTRACT(YEAR FROM now())::int,

    -- SKU: year + category_id + item_name_id + color_id (no padding)
    sku TEXT GENERATED ALWAYS AS (
        created_year::text
        || category_id::text
        || item_name_id::text
        || color_id::text
    ) STORED,

    CONSTRAINT ux_item_unique
        UNIQUE (item_name_id, category_id, color_id),

    CONSTRAINT ux_item_sku_unique
        UNIQUE (sku)
);

-- ============================================================================
-- ITEM PRICE HISTORY (TEMPORAL)
-- ============================================================================

CREATE TABLE kalyn_db_test.item_price_history
(
    id             SERIAL PRIMARY KEY,

    item_id        INTEGER NOT NULL
        REFERENCES kalyn_db.item (id),

    harga_kain       INTEGER NOT NULL,
    ongkos_jahit     INTEGER NOT NULL,
    ongkos_transport INTEGER NOT NULL,
    ongkos_packing   INTEGER NOT NULL,

    harga_dasar INTEGER GENERATED ALWAYS AS (
        harga_kain
      + ongkos_jahit
      + ongkos_transport
      + ongkos_packing
    ) STORED,

    harga_jual INTEGER GENERATED ALWAYS AS (
        ROUND(
            (harga_kain + ongkos_jahit + ongkos_transport + ongkos_packing) * 1.25
        )::int
    ) STORED,

    valid_from TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to   TIMESTAMPTZ
);

-- only one active price per item
CREATE UNIQUE INDEX uq_active_price_per_item
    ON kalyn_db.item_price_history (item_id)
    WHERE valid_to IS NULL;

CREATE INDEX ix_item_price_history_item_time
    ON kalyn_db_test.item_price_history (item_id, valid_from DESC);

CREATE OR REPLACE VIEW kalyn_db_test.item_price_current AS
SELECT *
FROM kalyn_db_test.item_price_history
WHERE valid_to IS NULL;

-- ============================================================================
-- ITEM STOCK SNAPSHOT
-- ============================================================================

CREATE TABLE kalyn_db_test.item_stock
(
    id         SERIAL PRIMARY KEY,

    item_id    INTEGER NOT NULL
        REFERENCES kalyn_db_test.item (id),

    store_id   INTEGER NOT NULL
        REFERENCES kalyn_db_test.store (id),

    size       VARCHAR(10) NOT NULL DEFAULT 'OS',

    quantity   INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT unique_item_stock
        UNIQUE (item_id, store_id, size),

    CONSTRAINT chk_item_stock_nonnegative
        CHECK (quantity >= 0)
);

-- ============================================================================
-- ITEM STOCK LOG (MOVEMENTS)
-- ============================================================================

CREATE TABLE kalyn_db_test.item_stock_log
(
    id           SERIAL PRIMARY KEY,

    item_id      INTEGER NOT NULL
        REFERENCES kalyn_db_test.item (id),

    store_id     INTEGER NOT NULL
        REFERENCES kalyn_db_test.store (id),

    size         VARCHAR(10) NOT NULL DEFAULT 'OS',

    movement_type VARCHAR(30) NOT NULL,

    quantity      INTEGER NOT NULL,

    recorded_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_movement_type
        CHECK (movement_type IN (
            'in_stock',
            'out',
            'adjustment',
            'transfer_in',
            'transfer_out'
        )),

    CONSTRAINT chk_quantity_nonzero
        CHECK (quantity <> 0)
);

CREATE INDEX ix_item_stock_log_item_store_time
    ON kalyn_db_test.item_stock_log (
        item_id,
        store_id,
        size,
        recorded_at DESC
    );

-- ============================================================================
-- TRIGGER: UPDATE SNAPSHOT FROM LOG
-- ============================================================================

CREATE OR REPLACE FUNCTION kalyn_db_test.update_item_stock_snapshot()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_qty INTEGER;
BEGIN
    SELECT quantity
    INTO v_current_qty
    FROM kalyn_db_test.item_stock
    WHERE item_id  = NEW.item_id
      AND store_id = NEW.store_id
      AND size     = NEW.size
    FOR UPDATE;

    IF NOT FOUND THEN
        IF NEW.quantity < 0 THEN
            RAISE EXCEPTION
                'Cannot start stock below zero. item_id=%, store_id=%, size=%',
                NEW.item_id, NEW.store_id, NEW.size;
        END IF;

        INSERT INTO kalyn_db_test.item_stock (
            item_id, store_id, size, quantity
        )
        VALUES (
            NEW.item_id, NEW.store_id, NEW.size, NEW.quantity
        );
    ELSE
        IF v_current_qty + NEW.quantity < 0 THEN
            RAISE EXCEPTION
                'Stock would go negative (current=%, change=%)',
                v_current_qty, NEW.quantity;
        END IF;

        UPDATE kalyn_db_test.item_stock
        SET quantity   = v_current_qty + NEW.quantity,
            updated_at = now()
        WHERE item_id  = NEW.item_id
          AND store_id = NEW.store_id
          AND size     = NEW.size;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_update_item_stock_snapshot
    ON kalyn_db_test.item_stock_log;

CREATE TRIGGER trg_update_item_stock_snapshot
AFTER INSERT ON kalyn_db_test.item_stock_log
FOR EACH ROW
EXECUTE FUNCTION kalyn_db_test.update_item_stock_snapshot();

-- ============================================================================
-- TRANSFER FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION kalyn_db_test.transfer_stock(
    p_item_id    INTEGER,
    p_size       VARCHAR,
    p_from_store INTEGER,
    p_to_store   INTEGER,
    p_quantity   INTEGER
)
RETURNS VOID
LANGUAGE plpgsql
AS $$
BEGIN
    IF p_quantity <= 0 THEN
        RAISE EXCEPTION 'p_quantity must be positive';
    END IF;

    INSERT INTO kalyn_db_test.item_stock_log (
        item_id, store_id, size, movement_type, quantity
    )
    VALUES (
        p_item_id, p_from_store, p_size, 'transfer_out', -ABS(p_quantity)
    );

    INSERT INTO kalyn_db_test.item_stock_log (
        item_id, store_id, size, movement_type, quantity
    )
    VALUES (
        p_item_id, p_to_store, p_size, 'transfer_in', ABS(p_quantity)
    );
END;
$$;