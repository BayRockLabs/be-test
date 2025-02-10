import os
from dotenv import load_dotenv
load_dotenv()

# Define the path to the secrets directory
secrets_dir = '/mnt/secrets-store/'

# Function to read environment variables from file
def read_env_var(filename):
    try:
        with open(os.path.join(secrets_dir, filename)) as f:
            return f.read().strip()
    except FileNotFoundError:
        return None

DB_HOSTNAME= read_env_var("DB-HOSTNAME")
DEBUG=read_env_var("DEBUG")
DB_USERNAME=read_env_var("DB-USERNAME")
DB_PASSWORD=read_env_var("DB-PASSWORD")
DB_PORT=read_env_var("DB-PORT")
DB_NAME=read_env_var("DB-NAME")
MONTHLY = read_env_var("MONTHLY")
YEARLY = read_env_var("YEARLY")
BI_WEEKLY = read_env_var("BI-WEEKLY")
QUARTERLY = read_env_var("QUARTERLY")
ACTIVE = read_env_var("ACTIVE")
INACTIVE = read_env_var("INACTIVE")
POTENTIAL_LEAD = read_env_var("POTENTIAL-LEAD")
ONBOARDED = read_env_var("ONBOARDED")
US = read_env_var("US")
LATAM = read_env_var("LATAM")
IND = read_env_var("IND")
EUR = read_env_var("EUR")
USD = read_env_var("USD")
INR = read_env_var("INR")
EUR = read_env_var("EUR")
EMPLOYEE = read_env_var("EMPLOYEE")
CONTRACTOR = read_env_var("CONTRACTOR")
EMPLOYEE_HOURLY = read_env_var("EMPLOYEE-HOURLY")
SUB_CONTRACTOR = read_env_var("SUB_CONTRACTOR")
ACCOUNT_URL = read_env_var("ACCOUNT-URL")
AZURE_CONNECTION_STRING = read_env_var("AZURE-CONNECTION-STRING")
AZURE_CONTAINER_NAME = read_env_var("AZURE-CONTAINER-NAME")
AUTH_API = read_env_var("AUTH-API")
OPENAI_API = read_env_var("OPENAI-API")
PROFILE = read_env_var("PROFILE")
MPS_DOCUMENT_PARSER_API = read_env_var("MPS-DOCUMENT-PARSER-API")
SCHEDULER_DAY = read_env_var("SCHEDULER-DAY")
SCHEDULER_HOUR = read_env_var("SCHEDULER-HOUR")
SCHEDULER_MINUTE = read_env_var("SCHEDULER-MINUTE")
SCHEDULER_TIMEZONE = read_env_var("SCHEDULER-TIMEZONE")