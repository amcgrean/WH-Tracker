from app import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=False)  # `debug=True` is optional and for development purposes
