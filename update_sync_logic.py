import os

def update_sync_and_routes():
    # Update sync_erp.py
    sync_path = 'sync_erp.py'
    if os.path.exists(sync_path):
        with open(sync_path, 'r') as f:
            content = f.read()
        
        # Add to mappings in push_to_cloud
        content = content.replace(
            "'expect_date': p.get('expect_date'),",
            "'expect_date': p.get('expect_date'),\n                        'sale_type': p.get('sale_type'),"
        )
        
        with open(sync_path, 'w') as f:
            f.write(content)
        print("Updated sync_erp.py")

    # Update routes.py
    routes_path = 'app/Routes/routes.py'
    if os.path.exists(routes_path):
        with open(routes_path, 'r') as f:
            content = f.read()

        # Add to ERPMirrorPick creation in erp_cloud_sync route
        content = content.replace(
            "expect_date=p.get('expect_date')",
            "expect_date=p.get('expect_date'),\n                    sale_type=p.get('sale_type')"
        )

        with open(routes_path, 'w') as f:
            f.write(content)
        print("Updated routes.py")

if __name__ == "__main__":
    update_sync_and_routes()
