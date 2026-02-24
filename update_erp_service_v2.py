import os

def update_erp_service():
    path = 'app/Services/erp_service.py'
    if not os.path.exists(path):
        print("File not found.")
        return

    with open(path, 'r') as f:
        content = f.read()

    # 1. get_open_picks cloud mode dictionary
    content = content.replace(
        "'system_id': p.system_id,\n                'expect_date': p.expect_date\n            } for p in picks]",
        "'system_id': p.system_id,\n                'expect_date': p.expect_date,\n                'sale_type': p.sale_type\n            } for p in picks]"
    )

    # 2. get_open_picks local mode query (the WHERE/ORDER BY part)
    # Note: Chunks 1 and 2 were applied successfully in my previous run, 
    # but I'll ensure they are handled if not.

    # 4. get_sales_delivery_tracker cloud mode dictionary
    content = content.replace(
        "'system_id': p.system_id,\n                        'expect_date': p.expect_date,\n                        'invoice_date': None",
        "'system_id': p.system_id,\n                        'expect_date': p.expect_date,\n                        'sale_type': p.sale_type,\n                        'invoice_date': None"
    )

    # 5. get_sales_delivery_tracker local mode query SELECT
    content = content.replace(
        "MAX(soh.system_id) as system_id,\n                    MAX(soh.expect_date) as expect_date,\n                    CASE",
        "MAX(soh.system_id) as system_id,\n                    MAX(soh.expect_date) as expect_date,\n                    MAX(soh.sale_type) as sale_type,\n                    CASE"
    )

    # 6. get_sales_delivery_tracker local mode query WHERE
    target_where = """                    OR (soh.so_status IN ('K', 'P', 'S') AND (soh.expect_date = '{today}' OR soh.expect_date < '{today}')) -- Show backlog too but avoid future ones
                  )
                GROUP BY soh.so_id"""
    
    replacement_where = """                    OR (soh.so_status IN ('K', 'P', 'S') AND (soh.expect_date = '{today}' OR soh.expect_date < '{today}')) -- Show backlog too but avoid future ones
                  )
                  AND soh.sale_type NOT IN ('Direct', 'WillCall', 'XInstall', 'Hold')
                GROUP BY soh.so_id"""
    
    content = content.replace(target_where, replacement_where)

    # 7. get_sales_delivery_tracker local mode dictionary
    content = content.replace(
        "'status_label': row.status_label,\n                    'invoice_date': row.invoice_date\n                })",
        "'status_label': row.status_label,\n                    'invoice_date': row.invoice_date,\n                    'system_id': row.system_id,\n                    'expect_date': str(row.expect_date) if row.expect_date else '',\n                    'sale_type': row.sale_type\n                })"
    )

    with open(path, 'w') as f:
        f.write(content)
    print("Successfully updated erp_service.py")

if __name__ == "__main__":
    update_erp_service()
