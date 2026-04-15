#!/usr/bin/env python3
"""Reset local SQLite database — recreates all tables from models."""
import os
db_path = 'instance/crm.db'
if os.path.exists(db_path):
    os.remove(db_path)
    print(f'Deleted {db_path}')
from app import create_app
app = create_app()
print('Database recreated with all columns and seed data.')
print('Admin user and Evore company created by init_db().')
