# Homzho Flask ERP System
# Homzho Flask ERP System

A lightweight, modular, and mobile-responsive ERP system built with Flask, designed specifically for a water purifier rental business.

## Features
- **Dashboard**: Financial overview, KPI metrics, overdue reminders, and dynamic charts (Chart.js).
- **Customers**: Full CRUD, dynamic search, automated billing reminders, assignment history.
- **Machines**: Inventory tracking, status management, maintenance history, assignment.
- **Payments**: Invoice generation (auto-incrementing), PDF/Print ready, partial payment tracking.
- **Maintenance**: Technician tracking, scheduled service reminders, part replacements.
- **Expenses**: Category tracking, monthly expense breakdown.
- **Uploads**: Secure document and image uploads, grouped by customer, automated resizing.
- **Reports**: Revenue vs Expenses, Data export via CSV.
- **Role-Based Access Control (RBAC)**: Admin, Operator, Technician permissions.
- **Deployment**: Production-ready configuration compatible with PythonAnywhere and VPS environments.

## Local Setup

### 1. Prerequisites
- Python 3.11+
- Virtual Environment

### 2. Installation
```bash
git clone <repository_url>
cd web_app_anti
python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

pip install -r requirements.txt
```

### 3. Environment Variables
Copy the template and fill in the values:
```bash
cp .env.template .env
```
Ensure you set a strong `SECRET_KEY` and define your admin credentials.

**Meta Conversion API Configuration**
To enable server-side tracking when leads convert to customers, add these to your `.env` file:
```env
META_PIXEL_ID=your_pixel_id_here
META_ACCESS_TOKEN=your_conversions_api_access_token
```
*Note: If these keys are not provided, the ERP will continue to function normally and silently skip sending the Meta events.*

### 4. Database Setup
The application uses Flask-Migrate for database schema management. Run the following commands to initialize and set up the SQLite database:

```bash
# Set Flask app
export FLASK_APP=app.py  # (Windows CMD: set FLASK_APP=app.py | PowerShell: $env:FLASK_APP="app.py")

# Initialize migrations folder (only once)
flask db init

# Create the initial migration script based on models
flask db migrate -m "Initial migration"

# Apply the migration to create tables in the database
flask db upgrade

# Create the initial Admin user
flask create-admin
```

### 5. Running the Application
```bash
# Start the development server
flask run --debug
```

Visit `http://localhost:5000` and log in with your admin credentials.

## PythonAnywhere Deployment Guide
1. Push code to GitHub/GitLab.
2. On PythonAnywhere, create a new Web App -> Manual configuration -> Python 3.11.
3. Open a Bash console and clone your repo: `git clone <your_repo> mysite`.
4. Create virtualenv: `mkvirtualenv --python=/usr/bin/python3.11 myvenv`.
5. Install packages: `pip install -r mysite/requirements.txt`.
6. Configure `.env` using PA's environment variables via the web interface or inside `mysite/.env`.
7. Modify the WSGI file as per `wsgi.py`.
8. Run database migrations in PA console:
   ```bash
   cd mysite
   export FLASK_APP=app.py
   flask db init
   flask db migrate -m "init"
   flask db upgrade
   flask create-admin
   ```
9. Map the `static` folder in the Web App section to `/home/username/mysite/static`.
10. Reload the web app.
