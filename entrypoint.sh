#!/bin/bash
creating tenant
export DB_NAME=c2c_service
python manage.py create_sample_tenant --admin_username="c2cadmin" --admin_email="a@a.com" --admin_password="Postgres@staging" --schema_name="t1" --tenant_name="Tenant 1" --domain_name="c2c-dev-psqlflexibleserver.postgres.database.azure.com"
Automatically approve makemigrations
echo "Auto-migrating"
python manage.py makemigrations --no-input
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
