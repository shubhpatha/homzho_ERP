import os
import sys
from dotenv import load_dotenv

# Add your project directory to the sys.path
project_home = '/home/yourusername/mysite'
if project_home not in sys.path:
    sys.path = [project_home] + sys.path

# Load environment variables from .env file
load_dotenv(os.path.join(project_home, '.env'))

# Import your application factory
from app import create_app

# The application object is used by any WSGI server configured to use this file.
application = create_app()
