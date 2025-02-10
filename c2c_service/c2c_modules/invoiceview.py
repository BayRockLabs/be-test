from datetime import datetime, timedelta
from django.utils import timezone
from c2c_modules.models import SowContract, MainMilestone, Estimation, Invoices, EmployeeEntryTimesheet, Timesheet, Allocation
from c2c_modules.serializer import InvoicesSerializer, InvoicesClientSerializer
from rest_framework.exceptions import ValidationError
from django.http import JsonResponse
from rest_framework.views import APIView
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from drf_yasg.utils import swagger_auto_schema
from c2c_modules.utils import has_permission
from rest_framework.response import Response
from rest_framework import status
from django.core.mail import EmailMessage
from django.conf import settings
from django.core.mail import BadHeaderError
from django.shortcuts import get_object_or_404
from django.db.models import Sum
from c2c_modules.custom_logger import info, error

class Pagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000

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
        print("filter_daily_hours")
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
                print(f"total_hours: {total_hours}, count: {count}")
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
    print(last_week_date,last_week_number,last_week_year)
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
    # print(contract.contractsow_name)
    print(contract.contractsow_type)
    print(estimation.uuid)
    # try:
    if estimation:
        estimation_data = {'resource': estimation.resource}
        total_hours_count, resource_count = get_resource_count_and_hours(estimation_data, current_date)
        print(total_hours_count, resource_count,"total_hours_count")
    if contract.contractsow_type == 'TIME AND MATERIAL':
        invoice_type = 'Timesheets'
        invoice_type_id = estimation.uuid
        # allocation_exists = Allocation.objects.filter(estimation=estimation).exists()
        # if allocation_exists:
        total_invoice_amount = get_last_week_billable_hours_sum(current_date, contract.uuid)
        print("get_last_week_billable_hours_sum", total_invoice_amount)
    else:
        total_invoice_amount, invoice_type, invoice_type_id = process_milestone_contract(contract, current_date)
    total_invoice_amount = round(total_invoice_amount, 2)
    print(total_invoice_amount, invoice_type, invoice_type_id, total_hours_count, resource_count)
    return total_invoice_amount, invoice_type, invoice_type_id, total_hours_count, resource_count
    # except Exception as e:
    #     error(f"Error processing contract: {e}")
    #     return 0, '', None, 0, 0

def process_milestone_contract(contract, current_date):
    """Process milestone contracts to calculate total invoice amount."""
    try:
        milestones = MainMilestone.objects.filter(contract_sow_uuid=contract.uuid).first()
        print(milestones)
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

@csrf_exempt
@require_POST
def create_invoice_view(request):
    result = create_invoice_logic()
    status_code = 200 if result.get('status') == 'success' else 500
    return JsonResponse(result, status=status_code)

class InvoicesByClientView(generics.ListAPIView):
    serializer_class = InvoicesClientSerializer
    pagination_class = Pagination


    def get_queryset(self):
        client_id = self.kwargs['client_id']
        return Invoices.objects.filter(c2c_client_id=client_id).order_by('c2c_invoice_status')

    @swagger_auto_schema(tags=["Invoices"])
    def get(self, request, client_id, *args, **kwargs):
        required_roles = ["c2c_invoice_admin","c2c_invoice_viewer","c2c_viewer","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"roles_response": result})
            return response
        else:
            return JsonResponse({"roles_response": result})


class UpdateInvoiceView(APIView):

    @swagger_auto_schema(tags=["Invoices"])
    def patch(self, request, *args, **kwargs):
        required_roles = ["c2c_invoice_admin","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            client_id = request.data.get('client_id')
            invoice_id = request.data.get('invoice_id')
            invoice_status = request.data.get('invoice_status')
            if not client_id or not invoice_id:
                return Response({"error": "client_id and invoice_id are mandatory."}, status=status.HTTP_400_BAD_REQUEST)

            try:
                invoice = Invoices.objects.get(c2c_invoice_id=invoice_id, c2c_client_id=client_id)
            except Invoices.DoesNotExist:
                return Response({"error": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)
            if invoice_status is not None:
                invoice.c2c_invoice_status = invoice_status
            invoice.save()
            serializer = InvoicesClientSerializer(invoice)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return JsonResponse({"roles_response": result})

class SendInvoiceView(APIView):
    def post(self, request, *args, **kwargs):
        required_roles = ["c2c_invoice_admin","c2c_super_admin"]
        result = has_permission(request, required_roles)

        if result["status"] == 200:
            client_id = request.data.get('client_id')
            invoice_id = request.data.get('invoice_id')
            to_email = request.data.get('to_email')
            email_subject = request.data.get('email_subject')
            email_body = request.data.get('email_body')
            invoice_pdf = request.FILES.get('invoice_pdf')
            if not (client_id and invoice_id and to_email and email_subject and email_body and invoice_pdf):
                return Response({"error": "All fields are mandatory."}, status=status.HTTP_400_BAD_REQUEST)
            try:
                invoice = Invoices.objects.get(c2c_invoice_id=invoice_id, c2c_client_id=client_id)
            except Invoices.DoesNotExist:
                return Response({"error": "Invoice not found."}, status=status.HTTP_404_NOT_FOUND)

            if isinstance(to_email, str):
                to_email = [to_email]
            try:
                email = EmailMessage(
                    subject=email_subject,
                    body=email_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=to_email
                )
                email.attach(invoice_pdf.name, invoice_pdf.read(), invoice_pdf.content_type)
                email.send()
                invoice.c2c_invoice_status = "Email Sent"
                invoice.save()
                return Response({"message": "Invoice sent to customer successfully."}, status=status.HTTP_200_OK)
            except BadHeaderError:
                return Response({"error": "Invalid header found."}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                return Response({"error": f"Failed to send email: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response({"roles_response": result}, status=status.HTTP_403_FORBIDDEN)

class InvoiceRegenerateAPIView(APIView):
    def post(self, request, invoice_id):
        invoice = get_object_or_404(Invoices, c2c_invoice_id=invoice_id)
        regenerate = request.data.get('regenerate', None)
        if regenerate is None:
            return Response({"error": "'regenerate' field is required."}, status=status.HTTP_400_BAD_REQUEST)
        if regenerate:
            invoice_type_id = invoice.c2c_invoice_type_id
            invoice_type = invoice.c2c_invoice_type
            invoice_generated_on = invoice.c2c_invoice_generated_on.date()
            if invoice_type == "Timesheets":
                contract = SowContract.objects.filter(estimation=invoice_type_id).first()
                total_invoice_amount = get_last_week_billable_hours_sum(invoice_generated_on,contract.uuid)
                total_invoice_amount = round(total_invoice_amount, 2)
            else:
                milestones = MainMilestone.objects.filter(uuid=invoice_type_id).first()
                total_invoice_amount = fetch_milestones_for_past_week(milestones.milestones, invoice_generated_on)
                total_invoice_amount = round(total_invoice_amount, 2)
        else:
            amount = request.data.get('invoice_amount', None)
            if amount is None:
                return Response({"error": "'invoice_amount' field is required when regenerate is false."}, status=status.HTTP_400_BAD_REQUEST)
            total_invoice_amount = amount

        old_invoice_amount = invoice.c2c_invoice_amount
        invoice.c2c_old_invoice_amount = old_invoice_amount
        invoice.c2c_invoice_amount = total_invoice_amount
        invoice.save()
        return Response({
            "message": "Invoice regenerated." if regenerate else "Invoice manually updated.",
            "c2c_invoice_type_id": invoice.c2c_invoice_type_id,
            "c2c_invoice_type": invoice.c2c_invoice_type,
            "c2c_old_invoice_amount": old_invoice_amount,
            "c2c_invoice_amount": total_invoice_amount
        }, status=status.HTTP_200_OK)

