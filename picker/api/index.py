from app import create_app

app = create_app()

# Vercel needs this to be exposed as 'app' or 'handler', but for WSGI, 'app' is standard.
# This file explicitly tells Vercel where the app is initialized.
