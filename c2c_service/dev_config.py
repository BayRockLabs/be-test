import os
from dotenv import load_dotenv
load_dotenv()

DB_HOSTNAME= os.getenv("DB_HOSTNAME")
DEBUG=os.getenv("DEBUG")
DB_USERNAME=os.getenv("DB_USERNAME")
DB_PASSWORD=os.getenv("DB_PASSWORD")
DB_PORT=os.getenv("DB_PORT")
DB_NAME=os.getenv("DB_NAME")
MONTHLY = os.getenv("MONTHLY")
YEARLY = os.getenv("YEARLY")
BI_WEEKLY = os.getenv("BI_WEEKLY")
QUARTERLY = os.getenv("QUARTERLY")
ACTIVE = os.getenv("ACTIVE")
INACTIVE = os.getenv("INACTIVE")
POTENTIAL_LEAD = os.getenv("POTENTIAL_LEAD")
ONBOARDED = os.getenv("ONBOARDED")
US = os.getenv("US")
LATAM = os.getenv("LATAM")
IND = os.getenv("IND")
EUR = os.getenv("EUR")
USD = os.getenv("USD")
INR = os.getenv("INR")
EUR = os.getenv("EUR")
EMPLOYEE = os.getenv("EMPLOYEE")
CONTRACTOR = os.getenv("CONTRACTOR")
EMPLOYEE_HOURLY = os.getenv("EMPLOYEE_HOURLY")
SUB_CONTRACTOR = os.getenv("SUB_CONTRACTOR")
ACCOUNT_URL = os.getenv("ACCOUNT_URL")
AZURE_CONNECTION_STRING = os.getenv("AZURE_CONNECTION_STRING")
AZURE_CONTAINER_NAME = os.getenv("AZURE_CONTAINER_NAME")
AUTH_API = os.getenv("AUTH_API")
OPENAI_API = os.getenv("OPENAI_API")
PROFILE= os.getenv("PROFILE")
MPS_DOCUMENT_PARSER_API = os.getenv("MPS_DOCUMENT_PARSER_API")
SCHEDULER_DAY = os.getenv("SCHEDULER_DAY")
SCHEDULER_HOUR = os.getenv("SCHEDULER_HOUR")
SCHEDULER_MINUTE = os.getenv("SCHEDULER_MINUTE")
SCHEDULER_TIMEZONE = os.getenv("SCHEDULER_TIMEZONE")
