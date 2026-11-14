# Create and activate virtual environment
python -m venv venv
source venv/bin/activate        # macOS / Linux
# venv\Scripts\activate         # Windows (Command Prompt)

# Install dependencies
pip install -r requirements.txt

# Run guicorn locally
gunicorn --bind 127.0.0.1:8000 app:app

