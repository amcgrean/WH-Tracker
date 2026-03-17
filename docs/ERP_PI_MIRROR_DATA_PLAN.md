# ERP Pi Mirror Data Plan

Last updated: 2026-03-16

## Purpose

This document defines what ERP SQL data the Raspberry Pi sync service should mirror for `tracker`.

The goal is not to build one giant flat export. The goal is to mirror Agility in a normalized way so:

- current tracker features keep working in cloud mode
- dispatch, sales, AR, and work order features can all share the same mirrored source
- we can add more ERP-backed features without redesigning the sync every time
- the mirror can grow to dozens of tables safely

## Key Direction

The Pi worker should mirror the ERP in table groups:

- sales order headers
- sales order lines
- shipment headers
- shipment lines
- customer master
- customer ship-to
- item master
- item branch attributes
- item UOM conversions
- AR headers
- AR detail / due date source rows
- print/email audit rows
- work orders
- pick ticket headers
- pick ticket details

`tracker` should read from these mirrored tables in cloud mode instead of depending on one denormalized catch-all table forever.

## Why The AR Script Matters

The file [customer ar detail.sql](C:\Users\amcgrean\python\tracker\customer ar detail.sql) is a very useful pattern reference.

It shows that the right ERP shape is:

- one header source table
- one detail source table
- a few master tables for labels and attributes
- clear eligibility rules
- business-specific gate tables like print/email audit

That is exactly how we should design the Pi sync mirror too.

## Current Tracker Features And Source Tables

These are the tables the current ERP service already depends on directly or indirectly.

### Sales / Pick / Dispatch

- `so_header`
- `so_detail`
- `shipments_header`
- `shipments_detail`
- `cust`
- `cust_shipto`
- `item`
- `item_branch`
- `pick_header`
- `pick_detail`

### Work Orders

- `wo_header`
- `so_detail`
- `so_header`
- `item`
- `cust`

### AR / Sales History / ToolBx

- `aropen`
- `aropendt`
- `cust`
- `shipments_detail`
- `item`
- `item_uomconv`
- `print_transaction`
- `print_transaction_detail`

## Recommended Mirror Table Groups

These should be mirrored as separate tables, not collapsed into one all-purpose table.

### 1. Sales Order Header Mirror

Recommended table: `erp_mirror_so_header`

Purpose:

- sales dashboards
- delivery board
- dispatch stops
- customer history
- order lookup

Minimum columns:

- `system_id`
- `so_id`
- `so_status`
- `sale_type`
- `cust_key`
- `shipto_seq_num`
- `reference`
- `expect_date`
- `created_date`
- `invoice_date` if present on header
- `updated_at` or best available change marker

Likely additional columns to validate:

- `ship_date`
- `promise_date`
- `ship_via`
- `freight_code`
- `terms`
- `salesperson`
- `po_number`

Key:

- `(system_id, so_id)`

### 2. Sales Order Line Mirror

Recommended table: `erp_mirror_so_detail`

Purpose:

- order detail views
- pick board
- handling code grouping
- product and demand reporting

Minimum columns:

- `system_id`
- `so_id`
- `sequence`
- `item_ptr`
- `qty_ordered`
- `qty_shipped` if available
- `bo`
- `date_required` if available
- `updated_at` or change marker

Key:

- `(system_id, so_id, sequence)`

### 3. Shipment Header Mirror

Recommended table: `erp_mirror_shipments_header`

Purpose:

- dispatch board
- delivery tracker
- route, driver, stage, and delivery status
- KPI calculations

Minimum columns:

- `system_id`
- `so_id`
- `shipment_num` if available
- `status_flag`
- `status_flag_delivery`
- `invoice_date`
- `ship_date`
- `loaded_date`
- `loaded_time`
- `route_id_char`
- `ship_via`
- `driver`
- `updated_at` or change marker

Key:

- ideally `(system_id, so_id, shipment_num)`
- if no stable shipment number, document the true natural key

### 4. Shipment Line Mirror

Recommended table: `erp_mirror_shipments_detail`

Purpose:

- dispatch manifest details
- line-level delivery detail
- AR line mapping

Minimum columns:

- `system_id`
- `so_id`
- `shipment_num` if available
- `line_no` or `sequence`
- `item_ptr`
- `qty`
- `qty_ordered`
- `qty_shipped`
- `price`
- `price_uom_ptr`
- `weight`
- `updated_at` or change marker

Key:

- validate natural key from ERP
- likely `(system_id, so_id, shipment_num, line_no)`

### 5. Customer Master Mirror

Recommended table: `erp_mirror_cust`

Purpose:

- customer profile
- AR reporting
- sales intelligence
- customer search

Minimum columns:

- `cust_key`
- `cust_code`
- `cust_name`
- `phone`
- `email`
- `balance` if useful
- `credit_limit` if useful
- `updated_at` or change marker

Key:

- `cust_key`

### 6. Customer Ship-To Mirror

Recommended table: `erp_mirror_cust_shipto`

Purpose:

- dispatch stop addresses
- GPS/geocode mapping
- job reference mapping
- customer delivery history

Minimum columns:

- `cust_key`
- `seq_num`
- `address_1`
- `address_2`
- `city`
- `state`
- `zip`
- `attention`
- `phone`
- `updated_at` or change marker

Key:

- `(cust_key, seq_num)`

### 7. Item Master Mirror

Recommended table: `erp_mirror_item`

Purpose:

- order detail labels
- AR detail labels
- sales catalog
- product intelligence

Minimum columns:

- `item_ptr`
- `item`
- `description`
- `stocking_uom`
- `item_group` if available
- `product_line` if available
- `updated_at` or change marker

Key:

- `item_ptr`

### 8. Item Branch Mirror

Recommended table: `erp_mirror_item_branch`

Purpose:

- handling code grouping
- branch-specific inventory/attributes

Minimum columns:

- `system_id`
- `item_ptr`
- `handling_code`
- inventory status fields if needed later
- `updated_at` or change marker

Key:

- `(system_id, item_ptr)`

### 9. Item UOM Conversion Mirror

Recommended table: `erp_mirror_item_uomconv`

Purpose:

- AR detail unit normalization
- pricing/unit conversions

Minimum columns:

- `item_ptr`
- `uom_ptr`
- `conv_factor_from_stocking`
- `updated_at` or change marker

Key:

- `(item_ptr, uom_ptr)`

### 10. Work Order Header Mirror

Recommended table: `erp_mirror_wo_header`

Purpose:

- work order tracker
- manufacturing / door flow
- order-to-work-order drilldown

Minimum columns:

- `wo_id`
- `source`
- `source_id`
- `source_seq`
- `wo_status`
- `wo_rule`
- `item_ptr` or related item join key
- `qty`
- `department`
- `updated_at` or change marker

Key:

- `wo_id`

### 11. Pick Ticket Mirror

Recommended tables:

- `erp_mirror_pick_header`
- `erp_mirror_pick_detail`

Purpose:

- printed/staged tracking
- local pick state enrichment
- future reconciliation between ERP and tracker local activity

Minimum header columns:

- `pick_id`
- `system_id`
- `created_date`
- `created_time`
- `print_status`
- `updated_at` or change marker

Minimum detail columns:

- `pick_id`
- `system_id`
- `tran_type`
- `tran_id`
- `sequence` if available
- `updated_at` or change marker

### 12. AR Open Header Mirror

Recommended table: `erp_mirror_aropen`

Purpose:

- AR aging
- customer sales/AR history
- ToolBx export support

Minimum columns:

- `ref_num`
- `cust_key`
- `ref_date`
- `update_date`
- `amount`
- `open_amt`
- `ref_type`
- `shipto_seq`
- `statement_id`
- `discount_amt`
- `discount_taken`
- `ref_num_sysid`
- `paid_in_full_date`
- `open_flag`
- `updated_at` or change marker

Key:

- `ref_num`

### 13. AR Detail / Due Date Mirror

Recommended table: `erp_mirror_aropendt`

Purpose:

- due dates
- linkage from AR invoice to shipment / sales transaction

Minimum columns:

- `ref_num`
- `tran_id`
- `due_date`
- any true line identifier if present
- `updated_at` or change marker

### 14. Print / Email Audit Mirror

Recommended tables:

- `erp_mirror_print_transaction`
- `erp_mirror_print_transaction_detail`

Purpose:

- ToolBx invoice eligibility
- proof that invoice went through Agility email path
- future outbound document auditing

Minimum print transaction columns:

- `tran_id`
- `tran_type`
- `system_id` if present
- `created_at` or change marker

Minimum print detail columns:

- `tran_id`
- `printer_id`
- `printer_destination`
- `created_at` or change marker

## Immediate Feature Coverage

If we want the Pi mirror to support the current app without direct SQL, these source groups are the first priority:

1. `so_header`
2. `so_detail`
3. `shipments_header`
4. `shipments_detail`
5. `cust`
6. `cust_shipto`
7. `item`
8. `item_branch`
9. `wo_header`
10. `pick_header`
11. `pick_detail`
12. `aropen`
13. `aropendt`
14. `print_transaction`
15. `print_transaction_detail`
16. `item_uomconv`

That set covers:

- dispatch
- delivery tracking
- pick tracker context
- work orders
- customer history
- AR / ToolBx invoice history

## Column Validation Needed

These areas still need confirmation against live ERP schemas before we lock the Pi sync:

- the true natural key for `shipments_header`
- the true natural key for `shipments_detail`
- whether `so_header` already carries enough delivery fields to reduce joins
- whether `wo_header` has its own quantity/item fields or always needs `so_detail`
- whether the best change token is:
  - `update_date`
  - `last_modified`
  - SQL rowversion/timestamp
  - or a composite watermark
- whether print/email tables have a usable created timestamp for incremental sync

## Recommended Mirror Design Rules

### Rule 1: Mirror Raw ERP Tables First

Do not make the Pi worker produce app-specific flattened rows as the main source of truth.

Instead:

- mirror ERP tables close to source shape
- then create app-specific views or materialized rollups in tracker as needed

### Rule 2: Keep App State Separate From ERP State

Examples:

- local picker progress
- user notes
- manual dispatch overrides
- assignment choices

Those should stay in tracker-owned tables, not in ERP mirror tables.

### Rule 3: Every Mirror Table Needs Sync Metadata

Each mirrored table should eventually have:

- natural key columns
- `source_updated_at` if available
- `synced_at`
- `sync_batch_id`
- optional `source_hash`
- optional soft-delete or active flag if ERP deletions matter

### Rule 4: Prefer Incremental Sync, But Start Safe

Best path:

- use source update timestamps or rowversion columns if available
- fall back to rolling-window re-reads where not available
- for tricky tables, full refresh into staging + merge is acceptable at first

### Rule 5: Use Table-Specific Strategies

Examples:

- master tables like `cust` and `item` can sync less often
- operational tables like `so_header`, `shipments_header`, `pick_header` should sync every 3-5 seconds or near-real-time
- historical AR tables can use a larger rolling window plus payment-state checks

## Suggested Sync Phases

### Phase 1: Keep Current Tracker Features Alive

Mirror:

- sales order header/detail
- shipment header/detail
- customer + ship-to
- item + item_branch
- work orders
- pick headers/details

### Phase 2: Add Sales History / AR

Mirror:

- `aropen`
- `aropendt`
- `print_transaction`
- `print_transaction_detail`
- `item_uomconv`

### Phase 3: Expand For Sales Hub And Reporting

Mirror:

- inventory tables
- pricing tables
- salesperson tables
- customer contact tables
- invoice history and payment history tables

## Proposed Tracker Mirror Targets

Long term, `tracker` should move away from using only `ERPMirrorPick` and `ERPMirrorWorkOrder`.

Recommended replacement family:

- `ERPMirrorSalesOrderHeader`
- `ERPMirrorSalesOrderLine`
- `ERPMirrorShipmentHeader`
- `ERPMirrorShipmentLine`
- `ERPMirrorCustomer`
- `ERPMirrorCustomerShipTo`
- `ERPMirrorItem`
- `ERPMirrorItemBranch`
- `ERPMirrorItemUomConv`
- `ERPMirrorArOpen`
- `ERPMirrorArOpenDetail`
- `ERPMirrorPrintTransaction`
- `ERPMirrorPrintTransactionDetail`
- `ERPMirrorWorkOrder`
- `ERPMirrorPickHeader`
- `ERPMirrorPickDetail`

`ERPMirrorPick` can remain as a temporary convenience table or materialized rollup for cloud mode, but it should stop being the only mirrored ERP representation.

## Open Questions For Column Review

These are the column sets I expect we will need help validating against live ERP:

- `so_header`: promised date, ship date, freight code, sales rep, terms
- `so_detail`: committed/shipped/backorder fields beyond `qty_ordered` and `bo`
- `shipments_header`: exact route/driver/load key fields
- `shipments_detail`: exact shipment line key and quantity fields
- `wo_header`: quantity, item, and department fields
- AR tables: any additional fields needed for aging buckets and payment status

## Recommended Next Step

Build the Pi sync around source-table mirrors first, then create tracker-side service queries and rollups from those mirrors.

That keeps us aligned with how the ERP is really structured and gives us room to add many more tables and features without rewriting the sync architecture.
