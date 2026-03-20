-- ============================================================
-- GetARDetail_updated.sql
-- Last updated: 2026-03-16  |  Author: amcgrean
--
-- PURPOSE:
--   Pulls all open (and recently paid) AR transactions from Agility
--   that have been invoiced through the ToolBx relay email, formats
--   them into the header+detail row structure expected by the ToolBx
--   bulk-upload AR endpoint, and returns them ordered by customer /
--   invoice / line sequence.
--
--   This script is the standalone version used for validation.
--   The live stored procedure is GetARDetail in AgilitySQL.
--   To apply changes: ALTER PROCEDURE GetARDetail AS BEGIN ... END
--
-- OUTPUT FORMAT:
--   Each invoice produces ONE header row (Account Number, Document
--   Number, amounts, dates, etc.) followed by ZERO OR MORE detail
--   rows (SKU, qty, price).  Header rows have blank SKU/Quantity/
--   Total Price fields; detail rows have blank Account Number /
--   Document Number fields.  ToolBx groups them by position --
--   detail rows always belong to the most recent header row above.
--
-- CHANGE LOG:
--   2026-03-16  amcgrean  - Moved customer exclusion list out of the
--                           inner EXISTS block into the main WHERE clause.
--                           Functionally identical but cleaner and safer
--                           to maintain.
--                         - Removed two dead columns from base CTE:
--                           ardet.ref_num_seq and sd.uom (neither was
--                           referenced by any downstream CTE or output).
--
-- KNOWN BEHAVIOURS / GOTCHAS:
--   * REPLICATION LAG: print_transaction and print_transaction_detail
--     are read from the SQL replication server, which can run up to
--     ~24 hours behind the live Agility database.  Invoices emailed to
--     beissertoolbx@gmail.com since the last replication sync will not
--     appear until the next cycle completes.
--
--   * 5-DAY PAID WINDOW: Paid invoices are included for 5 days after
--     payment so ToolBx can mark them as cleared.  If an ingest run is
--     missed over a long weekend or holiday those invoices can fall
--     outside the window and ToolBx will never receive the paid signal.
--     The holiday list in config.json should be kept current to avoid
--     scheduling gaps.
--
--   * ZERO-PRICE LINE SUPPRESSION: Line items where qty = 0 or
--     total_price = 0 are intentionally excluded from the detail rows
--     (see detail_rows CTE).  Free/no-charge items will not appear in
--     ToolBx line detail.  The invoice header amount will still be
--     correct because it comes directly from aropen.amount, not from
--     summing the detail lines.
--
--   * EXCLUDED CUSTOMERS: The five customer codes in the NOT IN list
--     below are internal / intercompany accounts that should never be
--     pushed to ToolBx.  Add new codes here if additional accounts
--     need to be suppressed.
-- ============================================================


-- ============================================================
-- CTE 1: base
-- Joins the core AR tables together and applies all eligibility
-- filters.  Every row here is one line item on one invoice.
-- Non-shipment transactions (finance charges, adjustments) will
-- have NULL values for the sd.* and item.* columns -- that is
-- expected and handled downstream.
-- ============================================================
WITH base AS (
  SELECT
    -- AR header fields (one logical value per invoice)
    ar.ref_num,           -- Invoice / CM / FC number  e.g. 0001462253-001
    c.cust_code,          -- Agility customer code      e.g. SCRE1100
    ar.ref_date,          -- Invoice date
    ar.update_date,       -- Date of last change in Agility
    ar.amount,            -- Original invoice amount
    ar.open_amt,          -- Current outstanding balance
    ar.ref_type,          -- Transaction type code: IN, CM, AD, CA, FC, etc.
    ar.shipto_seq,        -- Ship-to sequence number -- maps to ToolBx Job Reference
    ar.statement_id,      -- Statement number the invoice appears on
    ar.discount_amt,      -- Early-pay discount available
    ar.discount_taken,    -- Discount already applied
    ar.ref_num_sysid,     -- Branch code  e.g. 20GR
    ar.paid_in_full_date, -- Date paid (NULL if still open)

    -- AR detail / source sales order
    ardet.due_date,       -- Payment due date from aropendt
    ardet.tran_id,        -- Source SO/transaction ID -- used to join to shipments

    -- Shipment line fields (NULL for non-shipment transactions)
    sd.item_ptr,          -- Internal item key -- used to look up item master
    sd.sequence AS sd_sequence, -- Line sequence number on the shipment
    -- NOTE: sd.uom is intentionally omitted -- output uses stocking_uom from
    --       the item master instead, which is the canonical unit for ToolBx.

    -- Numeric conversions (stored as varchar in Agility, cast here once)
    TRY_CONVERT(DECIMAL(18,6), sd.qty)                       AS qty_num,
    TRY_CONVERT(DECIMAL(18,6), sd.price)                     AS price_num,
    -- conv_factor_from_stocking converts the sell UOM price back to the
    -- stocking UOM price so all line amounts are in a consistent unit
    TRY_CONVERT(DECIMAL(18,6), u.conv_factor_from_stocking)  AS conv_num,

    -- Item master fields
    i.item,               -- Item / SKU code
    i.description,        -- Item description
    i.stocking_uom        -- Canonical stocking unit of measure

  FROM aropen ar
  LEFT JOIN cust c
    ON c.cust_key = ar.cust_key

  -- aropendt holds the due date and links each AR record to its
  -- source sales order / transaction.  One row per AR entry.
  LEFT JOIN aropendt ardet
    ON ardet.ref_num = ar.ref_num

  -- shipments_detail holds the individual line items on the shipment
  -- associated with this AR entry.  NULL for non-shipment transactions.
  LEFT JOIN shipments_detail sd
    ON sd.so_id = ardet.tran_id

  -- Item master lookup for SKU code and description
  LEFT JOIN item i
    ON i.item_ptr = sd.item_ptr

  -- UOM conversion: maps the line's sell price UOM to the stocking UOM.
  -- If no conversion exists (e.g. already in stocking UOM), conv_num
  -- will be NULL and the price fallback in detail_calc handles it.
  LEFT JOIN item_uomconv u
    ON u.item_ptr = sd.item_ptr
   AND u.uom_ptr  = sd.price_uom_ptr

  WHERE
    -- Include invoices that are still open OR were paid in the last 5 days.
    -- The 5-day window gives ToolBx time to receive the "paid" signal after
    -- payment is posted.  Extend this window if ingest runs might be skipped
    -- over long weekends or holidays.
    (   ar.open_flag = 1
     OR ar.paid_in_full_date >= DATEADD(DAY, -5, GETDATE())
    )

    -- Exclude internal / intercompany customer accounts that should never
    -- appear in ToolBx.  Add additional codes here as needed.
    -- NOTE: previously this exclusion was inside the print_transaction EXISTS
    --       block below, which worked but was confusing to read and easy to
    --       accidentally remove.  It lives here now for clarity.
    AND c.cust_code NOT IN (
      'SJMC1000',   -- [internal account]
      'OBRI1000',   -- [internal account]
      'MIDS1000',   -- [internal account]
      'HUBB1200',   -- [internal account]
      'AJCO1000'    -- [internal account]
    )

    -- Gate 1: the transaction must have been formally processed as an Invoice,
    -- Credit Memo, or Finance Charge through Agility's print system.
    -- This excludes pick tickets, delivery tickets, and other non-billing
    -- document types from entering the AR feed.
    AND EXISTS (
      SELECT 1
      FROM print_transaction pt
      WHERE pt.tran_id  = ar.ref_num
        AND pt.tran_type IN (
          'Invoice',
          'Credit Memo',
          'Finance Charge Invoice'
        )
    )

    -- Gate 2: the invoice must have been emailed to the ToolBx Gmail relay
    -- (beissertoolbx@gmail.com) via Agility's print/email system.
    -- This ensures only invoices that went through the standard ToolBx
    -- workflow are included.
    --
    -- IMPORTANT: this check reads from print_transaction_detail on the
    -- replication server.  If an invoice is manually forwarded to
    -- beissertoolbx@gmail.com outside of Agility (e.g. from Outlook),
    -- NO record will be written here and the invoice will be excluded
    -- even though the PDF was received.  Always re-send from within
    -- Agility to create the required record.
    --
    -- Invoices emailed since the last replication sync (~24 hrs) will
    -- also be absent until the next replication cycle completes.
    AND EXISTS (
      SELECT 1
      FROM print_transaction_detail ptd
      WHERE ptd.tran_id             = ar.ref_num
        AND ptd.printer_id          = 'E-Mail'
        AND ptd.printer_destination = 'beissertoolbx@gmail.com'
    )
),


-- ============================================================
-- CTE 2: detail_calc
-- Computes and rounds the per-line financial figures.
-- Converts raw varchar price/qty from shipments_detail into
-- clean DECIMAL values in the stocking unit of measure.
-- ============================================================
detail_calc AS (
  SELECT
    -- Pass-through header fields needed for grouping / output
    b.ref_num,
    b.cust_code,
    b.ref_date,
    b.update_date,
    b.amount,
    b.open_amt,
    b.ref_type,
    b.shipto_seq,
    b.statement_id,
    b.discount_amt,
    b.discount_taken,
    b.ref_num_sysid,
    b.due_date,

    b.item AS sku,

    -- Quantity rounded to 2 decimal places
    CAST(ROUND(b.qty_num, 2) AS DECIMAL(18,2))  AS qty_2,

    -- Unit of measure from item master (stocking UOM, not sell UOM)
    b.stocking_uom  AS uom_display,

    -- Extended line price: (sell price / conv factor) * qty
    -- NULLIF guards against divide-by-zero if conv_factor = 0
    CAST(ROUND(
      (b.price_num / NULLIF(b.conv_num, 0)) * b.qty_num
    , 2) AS DECIMAL(18,2))  AS total_price_2,

    b.description,

    -- Unit price in stocking UOM: sell price / conv factor
    -- Falls back to raw sell price if no conversion exists
    CAST(ROUND(
      CASE
        WHEN NULLIF(b.conv_num, 0) IS NOT NULL
          THEN b.price_num / b.conv_num
        ELSE b.price_num
      END
    , 2) AS DECIMAL(18,2))  AS unit_price_2,

    -- sd_sequence is the explicit line order from the shipment.
    -- If it cannot be converted to INT (or is NULL for non-shipment
    -- transactions), default to 0 and let numbered_details assign order.
    COALESCE(TRY_CONVERT(INT, b.sd_sequence), 0)  AS line_nbr

  FROM base b
),


-- ============================================================
-- CTE 3: numbered_details
-- Assigns a final sort sequence (line_seq) to every detail row.
-- Uses the explicit shipment line number where available; falls
-- back to alphabetical order by SKU + description for transactions
-- that have no shipment sequence (e.g. finance charges, adjustments).
-- ============================================================
numbered_details AS (
  SELECT
    d.*,
    CASE
      WHEN d.line_nbr = 0
        -- No explicit sequence: assign one alphabetically within the invoice
        THEN ROW_NUMBER() OVER (PARTITION BY d.ref_num ORDER BY d.sku, d.description)
      ELSE
        -- Use the sequence from the shipment record as-is
        d.line_nbr
    END AS line_seq
  FROM detail_calc d
),


-- ============================================================
-- CTE 4: header_rows
-- Produces ONE summary row per invoice for the ToolBx upload.
-- All line-level columns are blanked out here (SKU, Qty, etc.).
-- The GROUP BY collapses the fan-out from the line-item joins
-- so the invoice header appears exactly once.
-- sort_seq = 0 ensures header rows sort before their detail rows.
-- ============================================================
header_rows AS (
  SELECT
    CAST(d.cust_code      AS NVARCHAR(100))   AS [Account Number],
    CAST(d.ref_num        AS NVARCHAR(100))   AS [Document Number],
    CONVERT(NVARCHAR(10), d.ref_date,    23)  AS [Document Date],  -- YYYY-MM-DD
    CONVERT(NVARCHAR(10), d.due_date,    23)  AS [Due Date],       -- YYYY-MM-DD
    CONVERT(NVARCHAR(10), d.update_date, 23)  AS [Update],         -- YYYY-MM-DD

    CAST(d.amount         AS NVARCHAR(100))   AS [Original Amount],
    CAST(d.open_amt       AS NVARCHAR(100))   AS [Outstanding Amount],

    -- Map Agility internal ref_type codes to the human-readable labels
    -- expected by the ToolBx API.  Any unmapped code falls through as-is
    -- so new types don't silently disappear -- they will appear with their
    -- raw code and can be handled in the next maintenance cycle.
    CAST(
      CASE d.ref_type
        WHEN 'IN' THEN 'Invoice'          -- Standard invoice
        WHEN 'DM' THEN 'Invoice'          -- Debit memo (treated as invoice)
        WHEN 'DP' THEN 'Invoice'          -- Deposit (treated as invoice)
        WHEN 'CM' THEN 'Credit Note'      -- Credit memo
        WHEN 'AD' THEN 'Credit Note'      -- AR adjustment credit
        WHEN 'CA' THEN 'Credit Note'      -- Credit adjustment
        WHEN 'FC' THEN 'Finance Charge'   -- Finance charge
        ELSE d.ref_type                   -- Unknown -- pass raw code through
      END AS NVARCHAR(100)
    )                                         AS [Type],

    -- shipto_seq is Agility's ship-to location sequence number.
    -- ToolBx treats this as the Job Reference (project/job number).
    CAST(d.shipto_seq     AS NVARCHAR(100))   AS [Job Reference],

    CAST(d.statement_id   AS NVARCHAR(100))   AS [Statement Number],
    CAST(d.discount_amt   AS NVARCHAR(100))   AS [Original Discounted Amount],
    CAST(d.discount_taken AS NVARCHAR(100))   AS [Outstanding Discounted Amount],

    -- These fields are not populated from Agility -- left blank for ToolBx
    CAST('' AS NVARCHAR(100))                 AS [Discount Pay By Date],
    CAST('' AS NVARCHAR(100))                 AS [File URL],

    -- ref_num_sysid is the Agility branch code  e.g. 20GR
    CAST(d.ref_num_sysid  AS NVARCHAR(100))   AS [Branch],

    -- Line-item columns are blank on header rows
    CAST('' AS NVARCHAR(100))                 AS [SKU],
    CAST(NULL AS DECIMAL(18,2))               AS [Quantity],
    CAST('' AS NVARCHAR(100))                 AS [Unit of Measure],
    CAST(NULL AS DECIMAL(18,2))               AS [Total Price],
    CAST('' AS NVARCHAR(4000))                AS [Description],
    CAST(NULL AS DECIMAL(18,2))               AS [Unit Price],

    -- Hidden sort columns (not returned to caller)
    d.ref_num                                 AS sort_ref,
    0                                         AS sort_seq,   -- 0 = header, always first
    CAST(d.cust_code AS NVARCHAR(100))        AS sort_cust

  FROM numbered_details d

  -- GROUP BY collapses duplicate rows produced by the line-item joins.
  -- Only header-level fields are listed here; line-level fields are
  -- intentionally excluded because they differ per line.
  GROUP BY
    d.cust_code, d.ref_num, d.ref_date, d.due_date, d.update_date,
    d.amount, d.open_amt, d.ref_type,
    d.shipto_seq, d.statement_id, d.discount_amt, d.discount_taken,
    d.ref_num_sysid
),


-- ============================================================
-- CTE 5: detail_rows
-- Produces one row per qualifying line item.
-- All invoice header columns are blanked out here; ToolBx links
-- each detail row to the header above it by position in the file.
--
-- Zero-qty and zero-price lines are excluded.  This intentionally
-- suppresses free / no-charge items from the ToolBx line detail.
-- Invoice header amounts are NOT affected (they come from aropen
-- directly) so totals will still be correct even with lines hidden.
-- ============================================================
detail_rows AS (
  SELECT
    -- Header columns are blank on detail rows
    CAST('' AS NVARCHAR(100))                 AS [Account Number],
    CAST('' AS NVARCHAR(100))                 AS [Document Number],
    CAST('' AS NVARCHAR(100))                 AS [Document Date],
    CAST('' AS NVARCHAR(100))                 AS [Due Date],
    CAST('' AS NVARCHAR(100))                 AS [Update],
    CAST('' AS NVARCHAR(100))                 AS [Original Amount],
    CAST('' AS NVARCHAR(100))                 AS [Outstanding Amount],
    CAST('' AS NVARCHAR(100))                 AS [Type],
    CAST('' AS NVARCHAR(100))                 AS [Job Reference],
    CAST('' AS NVARCHAR(100))                 AS [Statement Number],
    CAST('' AS NVARCHAR(100))                 AS [Original Discounted Amount],
    CAST('' AS NVARCHAR(100))                 AS [Outstanding Discounted Amount],
    CAST('' AS NVARCHAR(100))                 AS [Discount Pay By Date],
    CAST('' AS NVARCHAR(100))                 AS [File URL],
    CAST('' AS NVARCHAR(100))                 AS [Branch],

    -- Line-item detail columns
    CAST(d.sku          AS NVARCHAR(100))     AS [SKU],
    d.qty_2                                   AS [Quantity],
    CAST(d.uom_display  AS NVARCHAR(100))     AS [Unit of Measure],
    d.total_price_2                           AS [Total Price],
    CAST(d.description  AS NVARCHAR(4000))    AS [Description],
    d.unit_price_2                            AS [Unit Price],

    -- Hidden sort columns (not returned to caller)
    d.ref_num                                 AS sort_ref,
    d.line_seq                                AS sort_seq,  -- > 0, sorts after header
    CAST(d.cust_code AS NVARCHAR(100))        AS sort_cust

  FROM numbered_details d

  -- Suppress zero-qty and zero-price lines.
  -- These are typically no-charge / informational lines that ToolBx
  -- does not need.  If a line has qty but no price (or vice versa)
  -- it is also excluded to avoid confusing $0.00 detail rows.
  WHERE
    ISNULL(d.qty_2,         0) <> 0
    AND ISNULL(d.total_price_2, 0) <> 0
)


-- ============================================================
-- FINAL SELECT
-- Combines header and detail rows via UNION ALL, then sorts so
-- each invoice's header row comes first, followed by its detail
-- lines in sequence order.  The three sort_ columns are hidden
-- from the output but drive the ORDER BY.
-- COALESCE converts NULL Quantity/Price to empty string so the
-- CSV has no bare NULL cells (ToolBx expects empty string, not NULL).
-- ============================================================
SELECT
  x.[Account Number],
  x.[Document Number],
  x.[Document Date],
  x.[Due Date],
  x.[Update],
  x.[Original Amount],
  x.[Outstanding Amount],
  x.[Type],
  x.[Job Reference],
  x.[Statement Number],
  x.[Original Discounted Amount],
  x.[Outstanding Discounted Amount],
  x.[Discount Pay By Date],
  x.[File URL],
  x.[Branch],
  x.[SKU],
  COALESCE(CAST(x.[Quantity]    AS NVARCHAR(50)), '') AS [Quantity],
  x.[Unit of Measure],
  COALESCE(CAST(x.[Total Price] AS NVARCHAR(50)), '') AS [Total Price],
  x.[Description],
  COALESCE(CAST(x.[Unit Price]  AS NVARCHAR(50)), '') AS [Unit Price]

FROM (
  SELECT * FROM header_rows
  UNION ALL
  SELECT * FROM detail_rows
) x

ORDER BY
  x.sort_cust,   -- Group by customer
  x.sort_ref,    -- Then by invoice number
  x.sort_seq;    -- Header (0) always before detail lines (1, 2, 3...)
