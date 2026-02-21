-- SCHEMA
CREATE SCHEMA IF NOT EXISTS kalyn_db;

-- COLOR
CREATE TABLE IF NOT EXISTS kalyn_db.color
(
    id    SERIAL PRIMARY KEY,
    color VARCHAR NOT NULL UNIQUE
);

-- CATEGORY
CREATE TABLE IF NOT EXISTS kalyn_db.category
(
    id       SERIAL PRIMARY KEY,
    category VARCHAR NOT NULL UNIQUE,
    code     VARCHAR NOT NULL UNIQUE
);

-- ITEM NAME
CREATE TABLE IF NOT EXISTS kalyn_db.item_name
(
    id        SERIAL PRIMARY KEY,
    item_name VARCHAR NOT NULL UNIQUE
);

-- ITEM DETAILS
CREATE TABLE IF NOT EXISTS kalyn_db.item_details
(
    id               SERIAL PRIMARY KEY,
    item_name_id     INTEGER NOT NULL,
    category_id      INTEGER NOT NULL,
    color_id         INTEGER NOT NULL,

    harga_kain       INTEGER NOT NULL,
    ongkos_jahit     INTEGER NOT NULL,
    ongkos_transport INTEGER NOT NULL,
    ongkos_packing   INTEGER NOT NULL,

    harga_dasar      INTEGER
        GENERATED ALWAYS AS (
            harga_kain
                + ongkos_jahit
                + ongkos_transport
                + ongkos_packing
        ) STORED,

    harga_jual       INTEGER
        GENERATED ALWAYS AS (
            ROUND(
                (harga_kain + ongkos_jahit + ongkos_transport + ongkos_packing) * 1.25
            )::int
        ) STORED,

    input_at         TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_item_details_item_name
        FOREIGN KEY (item_name_id) REFERENCES kalyn_db.item_name (id),

    CONSTRAINT fk_item_details_category
        FOREIGN KEY (category_id) REFERENCES kalyn_db.category (id),

    CONSTRAINT fk_item_details_color
        FOREIGN KEY (color_id) REFERENCES kalyn_db.color (id)
);

-- ITEM STOCKS (current stock snapshot)
CREATE TABLE IF NOT EXISTS kalyn_db.item_stocks
(
    id           SERIAL PRIMARY KEY,
    item_name_id INTEGER NOT NULL,
    category_id  INTEGER NOT NULL,
    color_id     INTEGER NOT NULL,

    -- Use 'NA' for one-size items (change to 'OS'/'ALL' if you prefer)
    size         VARCHAR(10) NOT NULL DEFAULT 'OS',

    quantity     INTEGER NOT NULL DEFAULT 0,

    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_item_stocks_item_name
        FOREIGN KEY (item_name_id) REFERENCES kalyn_db.item_name (id),

    CONSTRAINT fk_item_stocks_category
        FOREIGN KEY (category_id) REFERENCES kalyn_db.category (id),

    CONSTRAINT fk_item_stocks_color
        FOREIGN KEY (color_id) REFERENCES kalyn_db.color (id),

    CONSTRAINT unique_item_stock
        UNIQUE (item_name_id, category_id, color_id, size)

    -- Optional: prevent negative stock in snapshot
    -- ,CONSTRAINT chk_stock_nonnegative CHECK (quantity >= 0)
);

-- ITEM STOCKS LOG (movement history)
CREATE TABLE IF NOT EXISTS kalyn_db.item_stocks_log
(
    id           SERIAL PRIMARY KEY,
    item_name_id INTEGER NOT NULL,
    category_id  INTEGER NOT NULL,
    color_id     INTEGER NOT NULL,

    size         VARCHAR(10) NOT NULL DEFAULT 'OS',

    -- positive = add stock, negative = subtract stock
    quantity     INTEGER NOT NULL,

    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_item_stocks_log_item_name
        FOREIGN KEY (item_name_id) REFERENCES kalyn_db.item_name (id),

    CONSTRAINT fk_item_stocks_log_category
        FOREIGN KEY (category_id) REFERENCES kalyn_db.category (id),

    CONSTRAINT fk_item_stocks_log_color
        FOREIGN KEY (color_id) REFERENCES kalyn_db.color (id)
);

-- Trigger function: every insert into item_stocks_log updates item_stocks
CREATE OR REPLACE FUNCTION kalyn_db.update_item_stocks_snapshot()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    INSERT INTO kalyn_db.item_stocks (
        item_name_id, category_id, color_id, size, quantity, updated_at
    )
    VALUES (
        NEW.item_name_id,
        NEW.category_id,
        NEW.color_id,
        NEW.size,
        NEW.quantity,
        now()
    )
    ON CONFLICT (item_name_id, category_id, color_id, size)
    DO UPDATE SET
        quantity = kalyn_db.item_stocks.quantity + EXCLUDED.quantity,
        updated_at = now();

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_update_item_stocks_snapshot
ON kalyn_db.item_stocks_log;

CREATE TRIGGER trg_update_item_stocks_snapshot
AFTER INSERT ON kalyn_db.item_stocks_log
FOR EACH ROW
EXECUTE FUNCTION kalyn_db.update_item_stocks_snapshot();
