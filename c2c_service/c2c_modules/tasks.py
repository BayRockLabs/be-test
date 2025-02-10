
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.events import EVENT_JOB_EXECUTED,EVENT_JOB_ERROR
from config import SCHEDULER_TIMEZONE, SCHEDULER_DAY, SCHEDULER_HOUR, SCHEDULER_MINUTE
from datetime import datetime, timedelta
from django.utils import timezone
from c2c_modules.models import SowContract, MainMilestone, Estimation, Invoices, EmployeeEntryTimesheet
from c2c_modules.serializer import InvoicesSerializer
from rest_framework.exceptions import ValidationError
from django.db.models import Sum
from c2c_modules.custom_logger import info, error

def get_weekdays_range(target_date):
    """
    Get weekdays (Monday to Friday) from the previous week.
    """
    previous_monday = target_date - timedelta(days=target_date.weekday() + 7)
    previous_friday = previous_monday + timedelta(days=4)
    weekdays = []
    current_day = previous_monday
    while current_day <= previous_friday:
        weekdays.append(current_day)
        current_day += timedelta(days=1)
    return weekdays

def identify_date_format(estimation_data):
    """Identify the date format based on the highest values in the day and month lists."""
    list1 = []
    list2 = []
    for entry in estimation_data:
        if "date" in entry:
            date_str = entry["date"]
            parts = date_str.split('/')
            if len(parts) != 3:
                raise ValueError(f"Invalid date format: {date_str}")
            list1.append(int(parts[0]))
            list2.append(int(parts[1]))
    if any(month > 12 for month in list2):
        return "%m/%d/%Y"
    elif any(day > 12 for day in list1):
        return "%d/%m/%Y"
    else:
        return "%d/%m/%Y"

def filter_daily_hours(daily_data, weekdays):
    """Filter daily hours for the given weekdays."""
    try:
        detected_format = identify_date_format(daily_data)
        hours = []
        for entry in daily_data:
            entry_date = datetime.strptime(entry['date'], detected_format).date()
            if entry_date and entry_date in weekdays:
                if entry['hours'] == "":
                    hours.append(0)
                else:
                    hours.append(entry['hours'])
        return hours
    except Exception as e:
        error(f"Error filtering daily hours: {e}")
        return 0

def calculate_weekly_invoice(resource, weekdays):
    """Calculate the weekly invoice amount for a given resource."""
    try:
        if 'Estimation_Data' not in resource or 'daily' not in resource['Estimation_Data']:
            return 0
        daily_hours = filter_daily_hours(resource['Estimation_Data']['daily'], weekdays)
        total_hours = sum(daily_hours)
        billrate = float(resource['pay_rate_info']['billrate'])
        return total_hours * billrate
    except Exception as e:
        error(f"Error calculating weekly invoice: {e}")
        return 0

def calculate_invoice_for_all_resources(estimation, target_date):
    """Calculate the invoice for all resources within the estimation data."""
    weekdays = get_weekdays_range(target_date)
    total_invoice = 0
    try:
        for resource in estimation['resource']:
            resource_invoice = calculate_weekly_invoice(resource, weekdays)
            total_invoice += resource_invoice
        return total_invoice
    except Exception as e:
        error(f"Error calculating invoice for resources: {e}")
        return 0

def get_resource_count_and_hours(estimation, target_date):
    """Calculate the invoice for all resources within the estimation data."""
    weekdays = get_weekdays_range(target_date)
    total_hours_count = 0
    resource_count = len(estimation['resource'])
    try:
        for resource in estimation['resource']:
            if 'Estimation_Data' not in resource or 'daily' not in resource['Estimation_Data']:
                total_hours_count = 0
            else:
                daily_hours = filter_daily_hours(resource['Estimation_Data']['daily'], weekdays)
                total_hours = sum(daily_hours)
                count = int(resource['num_of_resources'])
                total_hours = total_hours * count
                total_hours_count +=total_hours
                resource_count +=count
        return total_hours_count, resource_count
    except Exception as e:
        error(f"Error calculating resource count and hours: {e}")
        return 0, 0

def fetch_milestones_for_past_week(milestones, current_date):
    weekdays = get_weekdays_range(current_date)
    total_milestone_amount = 0
    try:
        for milestone in milestones:
            start_date_str = milestone['startDateValue']
            try:
                start_date = datetime.strptime(start_date_str, "%m/%d/%Y").date()
            except ValueError:
                continue
            if start_date in weekdays:
                total_milestone_amount += float(milestone.get('milestoneAmount', 0))
        return total_milestone_amount
    except Exception as e:
        error(f"Error fetching milestones for past week: {e}")
        return 0

def generate_invoice_id(contract_name, contract_id):
    """
    Generates a unique invoice ID based on contract name and past week number.
    """
    try:
        past_week_date = timezone.now() - timedelta(weeks=1)
        past_week_number = past_week_date.isocalendar()[1]
        invoice_count = Invoices.objects.filter(c2c_contract_id=contract_id).count()
        if invoice_count == 0:
            invoice_count = 1
        info(f"{contract_name}_{past_week_number}")
        return f"{contract_name}_{past_week_number}"
    except Exception as e:
        error(f"Error generating invoice ID: {e}")
        return None

def create_invoice_for_time_and_material_contracts():
    """
    Creates an invoice for time and material and milestone contracts.
    """
    try:
        current_date = timezone.now().date()
        weekdays = get_weekdays_range(current_date)
        contracts = SowContract.objects.filter(end_date__gt=min(weekdays))
        print("Total invoices count: ",len(contracts))
        for contract in contracts:
            total_invoice_amount, invoice_type, invoice_type_id, total_hours_count, resource_count = process_contract(contract, current_date)
            if total_invoice_amount > 0:
                invoice_id = generate_invoice_id(contract.contractsow_name, contract.uuid)
                save_invoice(contract, invoice_id, invoice_type, invoice_type_id, total_invoice_amount, total_hours_count, resource_count)
        formatted_weekdays = [day.strftime("%d-%m-%Y") for day in weekdays]
        return {"message": f"Invoices generated for the past week dates: {formatted_weekdays}"}
    except Exception as e:
        error(f"Error creating invoice: {e}")
        return {"message": f"Error creating invoice: {e}"}

def get_last_week_billable_hours_sum(current_date, contract_id):
    total_billable_hours = 0
    last_week_date = current_date - timedelta(weeks=1)
    last_week_number = last_week_date.isocalendar()[1]
    last_week_year = last_week_date.isocalendar()[0]
    try:
        timesheet_entries = EmployeeEntryTimesheet.objects.filter(
            week_number=last_week_number,
            year=last_week_year,
            contract_sow__uuid=contract_id
        )
        if timesheet_entries != None:
            total_billable_hours = timesheet_entries.aggregate(total_billable_hours=Sum('billable_hours'))['total_billable_hours'] or 0
            if timesheet_entries.exists():
                timesheet_object = timesheet_entries.first().timesheet_id
                if timesheet_object:
                    estimation_data = timesheet_object.resource_estimation_data
                    billrate = float(estimation_data['pay_rate_info']['billrate'])
                    total_billable_hours = billrate * total_billable_hours
        return total_billable_hours
    except Exception as e:
        error(f"Error getting last week billable hours sum: {e}")
        return 0

def process_contract(contract, current_date):
    """Process the contract to calculate total invoice amount and retrieve related details."""
    total_invoice_amount = 0
    invoice_type = ''
    invoice_type_id = None
    total_hours_count, resource_count = 0, 0
    estimation = Estimation.objects.filter(uuid=contract.estimation_id).first()
    if estimation:
        estimation_data = {'resource': estimation.resource}
        total_hours_count, resource_count = get_resource_count_and_hours(estimation_data, current_date)
    if contract.contractsow_type == 'TIME AND MATERIAL':
        invoice_type = 'Timesheets'
        invoice_type_id = estimation.uuid
        total_invoice_amount = get_last_week_billable_hours_sum(current_date, contract.uuid)
    else:
        total_invoice_amount, invoice_type, invoice_type_id = process_milestone_contract(contract, current_date)
    total_invoice_amount = round(total_invoice_amount, 2)
    return total_invoice_amount, invoice_type, invoice_type_id, total_hours_count, resource_count

def process_milestone_contract(contract, current_date):
    """Process milestone contracts to calculate total invoice amount."""
    try:
        milestones = MainMilestone.objects.filter(contract_sow_uuid=contract.uuid).first()
        if milestones != None:
            total_invoice_amount = fetch_milestones_for_past_week(milestones.milestones, current_date)
            return round(total_invoice_amount, 2), 'Milestone', milestones.uuid
        else:
            return 0, '', None
    except Exception as e:
        error(f"Error processing milestone contract: {e}")
        return 0, '', None

def save_invoice(contract, invoice_id, invoice_type, invoice_type_id, total_invoice_amount, total_hours_count, resource_count):
    """
    Save a new invoice to the database or update the `c2c_invoice_amount` of an existing one.
    """
    try:
        existing_invoice = Invoices.objects.filter(
            c2c_contract_id=contract,
            c2c_invoice_id=invoice_id
        ).first()
        if existing_invoice:
            existing_invoice.c2c_invoice_amount = total_invoice_amount
            existing_invoice.save()
            info(f"Invoice updated: {existing_invoice.c2c_invoice_id}, new amount: {existing_invoice.c2c_invoice_amount}")
        else:
            invoice_data = {
                'c2c_invoice_id': invoice_id,
                'c2c_client_id': contract.client.uuid,
                'c2c_contract_id': contract.uuid,
                'c2c_invoice_type': str(invoice_type),
                'c2c_invoice_type_id': str(invoice_type_id),
                'c2c_invoice_amount': total_invoice_amount,
                'c2c_total_hours_count': total_hours_count,
                'c2c_resource_count': resource_count,
                'c2c_invoice_generated_on': timezone.now(),
                'c2c_invoice_status': 'Active'
            }
            invoice_serializer = InvoicesSerializer(data=invoice_data)
            if invoice_serializer.is_valid():
                invoice_serializer.save()
                info(f"Invoice created: {invoice_serializer.data['c2c_invoice_id']}")
                print(f"Invoice created: {invoice_serializer.data['c2c_invoice_id']}")
            else:
                raise ValidationError(invoice_serializer.errors)
    except Exception as e:
        error(f"Error creating invoice: {e}")
        return {'message': f"Error creating invoice: {e}"}

def create_invoice_logic():
    try:
        result = create_invoice_for_time_and_material_contracts()
        return {'result': result, 'status': 'success'}
    except Exception as e:
        return {'error': str(e), 'status': 'failed'}
    
def start_invoice_scheduler():
    info("Starting the scheduler...")
    scheduler = BackgroundScheduler()
    trigger = CronTrigger(day_of_week=SCHEDULER_DAY, hour=SCHEDULER_HOUR, minute=SCHEDULER_MINUTE, timezone=SCHEDULER_TIMEZONE)
    job = scheduler.add_job(create_invoice_logic, trigger)
    info(f"Invoice Scheduler Job with ID: {job.id}")
    def job_listener(event):
        if event.exception:
            info(f"Job {event.job_id} failed: {event.exception}")
        else:
            info(f"Job {event.job_id} completed successfully at {event.scheduled_run_time}.")
    scheduler.add_listener(job_listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
    scheduler.start()
    info("Scheduler is running.")  


