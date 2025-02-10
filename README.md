# budgeto.ai (C2C) Microservice

#### TechStack Used..
1. Python (Programming Language)
2. Django (Web Framework)
3. PostgreSQL (Database)
4. Swagger (API documentation)


#### Setting up and Running Project Locally

##### Running locally using virtual env
1. Clone the Repository.
2. [Create and Activate python virtual environment](https://docs.python.org/3/library/venv.html#creating-virtual-environments)
3. Go to auth-service directory
    `$ cd c2c_service`
4. Install the requirements
    `pip install -r requirements.txt`
5. Make Migrations
    `$ python manage.py makemigrations`
6. Migrate to create tables in DB (Public management Schema)
    `$ python manage.py migrate`
7. Run the django server
    `$ python manage.py runserver`
9. Access django **swagger dashboard** at http://localhost:8000/swagger
