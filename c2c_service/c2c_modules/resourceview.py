from drf_yasg.utils import swagger_auto_schema
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from c2c_modules.models import Employee, Timesheet, EmployeeEntryTimesheet, Client, SowContract, GuestUser
from c2c_modules.serializer import TimesheetSerializer, TimesheetOverviewSerializer, EmployeeEntryTimesheetSerializer, TimesheetEstimationSerializer
from c2c_modules.utils import has_permission, check_role
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.utils.timezone import now
from django.db.models import Q
from datetime import datetime
from django.db.models import Sum
import re
from django.utils import timezone
from django.core.exceptions import ObjectDoesNotExist
from c2c_modules.custom_logger import info, error, warning
from config import PROFILE



RESOURCE_NOT_FOUND = "Resource not found"
EMPLOYEE_ERROR_MESSAGE  = "Either employee_id or employee_email must be provided."
EMPLOYEE_NOT_FOUND = "Employee does not exist."
DATE_FORMAT = "%Y-%m-%d"
class Pagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 1000


def parse_dates(resource_data):
    try:
        start_date_str = resource_data.get('start_date')
        end_date_str = resource_data.get('end_date')

        # Check if either key is missing or has a None value
        if not start_date_str or not end_date_str:
            raise ValueError("Missing start_date or end_date in resource_estimation_data.")

        start_date_str = resource_data['start_date'].split('T')[0]
        end_date_str = resource_data['end_date'].split('T')[0]
        start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
        end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
    except KeyError:
        raise ValueError("Missing start_date or end_date in resource_estimation_data.")
    except Exception as e:
        raise ValueError(f"Error parsing dates: {str(e)}")
    return start_date, end_date

def classify_projects(timesheets, current_date):
    ongoing_projects, completed_projects, future_projects, incomplete_projects = [], [], [], []
    for timesheet in timesheets:
        try:
            start_date, end_date = parse_dates(timesheet.resource_estimation_data)
            if start_date > current_date:
                future_projects.append(timesheet)
            elif end_date < current_date:
                completed_projects.append(timesheet)
            else:
                ongoing_projects.append(timesheet)
        except (ValueError, KeyError) as e:
            # Handle missing or invalid data
            print(f"Error processing timesheet: {e}")
            incomplete_projects.append(timesheet)

    return ongoing_projects, completed_projects, future_projects, incomplete_projects

class ResourceTimesheetsView(APIView):
    @swagger_auto_schema(tags=["Resource Timesheets"])
    def get(self, request, resource_id):
        required_roles = ["c2c_super_admin","c2c_timesheet_manager","c2c_timesheet_employee","c2c_guest_employee"]
        result = has_permission(request, required_roles)

        if result["status"] == 200:
            current_date = now().date()
            try:
                resource = Employee.objects.get(employee_source_id=resource_id)
                timesheets = Timesheet.objects.filter(
                resource=resource
                            ).exclude(
                                Q(client__isnull=True) | Q(contract_sow__isnull=True)
                            ).select_related('client', 'contract_sow')
                
                timesheet_ids = timesheets.values_list('id', flat=True)
                entry_timesheets = EmployeeEntryTimesheet.objects.filter(timesheet_id__in=timesheet_ids)
                total_planned_hours = entry_timesheets.aggregate(Sum('billable_hours'))['billable_hours__sum'] or 0
                ongoing_projects, completed_projects, future_projects, incomplete_projects = classify_projects(timesheets, current_date)

                data = {
                    'employee_full_name': resource.employee_full_name,
                    'employee_number': resource.employee_source_id,
                    'resource_role': timesheets.first().resource_role if timesheets.exists() else None,
                    'total_planned_hours': total_planned_hours,
                    'ongoing_projects': TimesheetSerializer(ongoing_projects, many=True,context={'employee': resource}).data,
                    'future_projects': TimesheetSerializer(future_projects, many=True,context={'employee': resource}).data,
                    'completed_projects': TimesheetSerializer(completed_projects, many=True,context={'employee': resource}).data,
                    'incomplete_projects': TimesheetSerializer(incomplete_projects, many=True,context={'employee': resource}).data
                }

                return Response(data, status=status.HTTP_200_OK)
            except Employee.DoesNotExist:
                return Response({'error': RESOURCE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({"result": result})

class TimesheetOverviewView(APIView):

    def get_approver_id_by_email(self,approver_email):
        try:
            guest_user = GuestUser.objects.get(guest_user_email_id=approver_email)
            return {"id": guest_user.guest_user_id, "source": "Guest"}
        except GuestUser.DoesNotExist:
            pass
        try:
            employee = Employee.objects.get(employee_email=approver_email)
            return {"id": employee.employee_source_id, "source": "Employee"}
        except Employee.DoesNotExist:
            pass
        return {"id": None, "source": "NotFound"}

    def get_distinct_resources_by_approver(self,approver_id):
        filtered_timesheets = Timesheet.objects.filter(
            Q(approver__contains=[{"approver_id": approver_id}])
        )
        distinct_resource_ids = (
            filtered_timesheets
            .select_related('resource')
            .values_list('resource', flat=True)
            .distinct()
        )
        return list(distinct_resource_ids)

    @swagger_auto_schema(tags=["Timesheet Overview"])
    def get(self, request, *args, **kwargs):
        required_roles = ["c2c_timesheet_manager","c2c_super_admin","c2c_timesheet_employee", "c2c_guest_employee", "c2c_hr_manager", "c2c_timesheet_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            current_date = now().date()
            overview_data = []
            approver_email = result['user_email']
            approver_info = self.get_approver_id_by_email(approver_email)
            if approver_info["source"] == "Employee" and check_role("c2c_timesheet_admin") in result["user_roles"]:
                resource_ids = Employee.objects.values_list('employee_source_id', flat=True)
            elif approver_info["source"] == "Employee" and check_role("c2c_super_admin") in result["user_roles"]:
                resource_ids = Employee.objects.values_list('employee_source_id', flat=True)
            elif approver_info["source"] == "Employee" and check_role("c2c_hr_manager") in result["user_roles"] and check_role("c2c_timesheet_manager") in result["user_roles"]:
                resource_ids = Employee.objects.values_list('employee_source_id', flat=True)
            elif approver_info["source"] == "Employee" and check_role("c2c_timesheet_manager") in result["user_roles"]:
                resource_ids = self.get_distinct_resources_by_approver(approver_info['id'])
            elif approver_info["source"] == "Employee" and check_role("c2c_hr_manager") in result["user_roles"]:
                resource_ids = Employee.objects.values_list('employee_source_id', flat=True)
            elif approver_info["source"] == "Guest" and check_role("c2c_guest_employee") in result["user_roles"]:
                resource_ids = self.get_distinct_resources_by_approver(approver_info['id'])
            else:
                resource_ids = []
                info("No approver found for the given email.")
            for resource_id in resource_ids:
                resource = Employee.objects.get(pk=resource_id)
                timesheets = Timesheet.objects.filter(resource=resource).select_related('contract_sow')
                total_planned_hours = timesheets.aggregate(Sum('billable_hours'))['billable_hours__sum'] or 0
                ongoing_projects, completed_projects, future_projects, incomplete_projects = classify_projects(timesheets, current_date)
                resource_role = timesheets.first().resource_role if timesheets.exists() else None

                overview_data.append({
                    'employee_full_name': resource.employee_full_name,
                    'employee_number': resource.employee_source_id,
                    'resource_role': resource_role,
                    'resource_id': resource_id,
                    'ongoing_projects': len(ongoing_projects),
                    'completed_projects': len(completed_projects),
                    'future_projects': len(future_projects),
                    'incomplete_projects': len(incomplete_projects),
                    'total_planned_hours': total_planned_hours
                })

            paginator = Pagination()
            paginated_data = paginator.paginate_queryset(overview_data, request)
            if paginated_data is not None:
                return paginator.get_paginated_response(paginated_data)

            serializer = TimesheetOverviewSerializer(overview_data, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response({"result": result})

class ResourceTimesheetsByNameView(APIView):

    @swagger_auto_schema(tags=["Resource Timesheets by Name"])
    def get(self, request, resource_name):
        required_roles = ["c2c_super_admin","c2c_timesheet_manager","c2c_timesheet_employee","c2c_guest_employee"]
        result = has_permission(request, required_roles)

        if result["status"] == 200:
            current_date = now().date()
            try:
                # Use filter to account for multiple employees with similar names
                resources = Employee.objects.filter(employee_full_name__icontains=resource_name)

                if not resources.exists():
                    return Response({'error': RESOURCE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

                response_data = []

                # Loop through all matched employees
                for resource in resources:
                    timesheets = Timesheet.objects.filter(resource=resource)

                    # Reuse the construct_response_data to format the response for each employee
                    data = self.construct_response_data(resource, timesheets, current_date)
                    response_data.append(data)

                return Response(response_data, status=status.HTTP_200_OK)

            except Employee.DoesNotExist:
                return Response({'error': RESOURCE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)
        else:
            return Response({"result": result})

    def construct_response_data(self, resource, timesheets, current_date):
        if not timesheets.exists():
            return self.build_empty_timesheet_response(resource)
        total_planned_hours = timesheets.aggregate(Sum('billable_hours'))['billable_hours__sum'] or 0
        ongoing_projects, completed_projects, future_projects, incomplete_projects = classify_projects(timesheets, current_date)
        return self.build_timesheet_response(resource, total_planned_hours, timesheets, ongoing_projects, future_projects, completed_projects, incomplete_projects)

    def build_empty_timesheet_response(self, resource):
        # Build response when no timesheets exist
        return {
            'employee_full_name': resource.employee_full_name,
            'employee_number': resource.employee_source_id,
            'resource_role': None,
            'total_planned_hours': 0,
            'ongoing_projects': [],
            'future_projects': [],
            'completed_projects': [],
            'incomplete_projects': []
        }

    def build_timesheet_response(self, resource, total_planned_hours, timesheets, ongoing_projects, future_projects, completed_projects, incomplete_projects):
        # Build response with timesheet data
        return {
            'employee_full_name': resource.employee_full_name,
            'employee_number': resource.employee_source_id,
            'resource_role': timesheets.first().resource_role,
            'total_planned_hours': total_planned_hours,
            'ongoing_projects': TimesheetSerializer(ongoing_projects, many=True).data,
            'future_projects': TimesheetSerializer(future_projects, many=True).data,
            'completed_projects': TimesheetSerializer(completed_projects, many=True).data,
            'incomplete_projects': TimesheetSerializer(incomplete_projects, many=True).data
        }


class TimesheetSubmissionAPIView(APIView):
    
    def check_permissions(self, request):
        required_roles = ["c2c_timesheet_manager", "c2c_super_admin", "c2c_timesheet_employee","c2c_guest_employee"]
        return has_permission(request, required_roles)

    def get_employee(self, employee_id=None, employee_email=None):
        try:
            if employee_id:
                return Employee.objects.get(employee_source_id=employee_id)
            else:
                return Employee.objects.get(employee_email=employee_email)
        except Employee.DoesNotExist:
            raise ValueError("Employee not found.")

    def validate_timesheet_data(self, timesheet_data):
        total_hours = 0
        for entry in timesheet_data:
            billable_hours = entry.get('billable_hours', 0)
            non_billable_hours = entry.get('non_billable_hours', 0)
            unplanned_hours = entry.get('unplanned_hours', 0)
            total_hours += billable_hours + non_billable_hours + unplanned_hours
        
        if total_hours > 40:
            raise ValueError("Total hours cannot exceed 40 in a week.")
        return total_hours

    def process_timesheet_entries(self, timesheet_data, employee, year, week_number):
        for entry in timesheet_data:
            client_name = entry.get('client_name')
            contract_name = entry.get('contract_name')
            billable_hours = entry.get('billable_hours', 0)
            non_billable_hours = entry.get('non_billable_hours', 0)
            unplanned_hours = entry.get('unplanned_hours', 0)

            client = self.get_client(client_name)
            contract_sow = self.get_contract(contract_name)

            EmployeeEntryTimesheet.objects.update_or_create(
                employee_id=employee,
                year=year,
                week_number=week_number,
                client=client,
                contract_sow=contract_sow,
                defaults={
                    'billable_hours': billable_hours,
                    'non_billable_hours': non_billable_hours,
                    'unplanned_hours': unplanned_hours,
                    'total_hours': billable_hours + non_billable_hours + unplanned_hours
                }
            )

    def get_client(self, client_name):
        try:
            return Client.objects.get(name=client_name)
        except Client.DoesNotExist:
            raise ValueError(f"Client {client_name} does not exist.")

    def get_contract(self, contract_name):
        try:
            return SowContract.objects.get(contractsow_name=contract_name)
        except SowContract.DoesNotExist:
            raise ValueError(f"Contract {contract_name} does not exist.")

    def post(self, request, *args, **kwargs):
        permission_result = self.check_permissions(request)
        if permission_result["status"] != 200:
            return Response(permission_result, status=status.HTTP_403_FORBIDDEN)

        employee_id = request.data.get('employee_id')
        employee_email = request.data.get('employee_email')
        year = request.data.get('year')
        week_number = request.data.get('week_number')
        timesheet_data = request.data.get('timesheet')

        if not employee_id and not employee_email:
            return Response({"error": EMPLOYEE_ERROR_MESSAGE}, status=status.HTTP_400_BAD_REQUEST)

        try:
            employee = self.get_employee(employee_id, employee_email)
            if not timesheet_data:
                return Response({"error": "No timesheet data provided."}, status=status.HTTP_400_BAD_REQUEST)

            total_hours = self.validate_timesheet_data(timesheet_data)
            self.process_timesheet_entries(timesheet_data, employee, year, week_number)

            return Response({"message": f"Timesheet submitted successfully.{total_hours}"}, status=status.HTTP_201_CREATED)

        except ValueError as ve:
            return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class TimesheetSubmissionAPIView(APIView):
    
    def check_permissions(self, request):
        required_roles = ["c2c_timesheet_manager", "c2c_super_admin", "c2c_timesheet_employee","c2c_guest_employee"]
        return has_permission(request, required_roles)

    def get_employee(self, employee_id=None, employee_email=None):
        try:
            if employee_id:
                return Employee.objects.get(employee_source_id=employee_id)
            else:
                return Employee.objects.get(employee_email=employee_email)
        except Employee.DoesNotExist:
            raise ValueError(EMPLOYEE_NOT_FOUND)

    def validate_total_hours(self, timesheet_data):
        total_hours = 0
        for entry in timesheet_data:
            billable_hours = entry.get('billable_hours', 0)
            non_billable_hours = entry.get('non_billable_hours', 0)
            unplanned_hours = entry.get('unplanned_hours', 0)
            total_hours += billable_hours + non_billable_hours + unplanned_hours

        if total_hours > 40:
            raise ValueError("Total hours cannot exceed 40 in a week.")
        
        return total_hours

    def process_timesheet_entries(self, employee, year, week_number, timesheet_data):
        for entry in timesheet_data:
            client_name = entry.get('client_name')
            contract_name = entry.get('contract_name')
            billable_hours = entry.get('billable_hours', 0)
            non_billable_hours = entry.get('non_billable_hours', 0)
            unplanned_hours = entry.get('unplanned_hours', 0)

            try:
                client = Client.objects.get(name=client_name)
                contract_sow = SowContract.objects.get(contractsow_name=contract_name)
                EmployeeEntryTimesheet.objects.update_or_create(
                    employee_id=employee,
                    year=year,
                    week_number=week_number,
                    client=client,
                    contract_sow=contract_sow,
                    defaults={
                        'billable_hours': billable_hours,
                        'non_billable_hours': non_billable_hours,
                        'unplanned_hours': unplanned_hours,
                        'total_hours': billable_hours + non_billable_hours + unplanned_hours
                    }
                )
            except Client.DoesNotExist:
                raise ValueError(f"Client {client_name} does not exist.")
            except SowContract.DoesNotExist:
                raise ValueError(f"Contract {contract_name} does not exist.")

    def post(self, request, *args, **kwargs):
        permission_result = self.check_permissions(request)
        if permission_result["status"] != 200:
            return Response(permission_result, status=status.HTTP_403_FORBIDDEN)

        employee_id = request.data.get('employee_id')
        employee_email = request.data.get('employee_email')
        year = request.data.get('year')
        week_number = request.data.get('week_number')
        timesheet_data = request.data.get('timesheet')

        if not employee_id and not employee_email:
            return Response({"error": EMPLOYEE_ERROR_MESSAGE}, status=status.HTTP_400_BAD_REQUEST)
        try:
            employee = self.get_employee(employee_id, employee_email)
            if not timesheet_data:
                return Response({"error": "No timesheet data provided."}, status=status.HTTP_400_BAD_REQUEST)
            self.validate_total_hours(timesheet_data)
            self.process_timesheet_entries(employee, year, week_number, timesheet_data)
            return Response({"message": "Timesheet submitted successfully."}, status=status.HTTP_201_CREATED)
        except ValueError as ve:
            return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TimesheetEstimationView(APIView):
    def post(self, request, *args, **kwargs):
        required_roles = ["c2c_timesheet_manager","c2c_super_admin","c2c_timesheet_employee","c2c_guest_employee"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            employee_id = request.data.get('employee_id')
            employee_email = request.data.get('employee_email')

            if not employee_id and not employee_email:
                return Response({"error": EMPLOYEE_ERROR_MESSAGE}, status=status.HTTP_400_BAD_REQUEST)
            try:
                if employee_id:
                    employee = Employee.objects.get(employee_source_id=employee_id)
                else:
                    employee = Employee.objects.get(employee_email=employee_email)
            except Employee.DoesNotExist:
                return Response({"error": EMPLOYEE_NOT_FOUND}, status=status.HTTP_404_NOT_FOUND)

            current_date = timezone.now().date()
            timesheets = Timesheet.objects.filter(
                resource_id=employee.pk,
                contract_sow__end_date__gte=current_date
            )

            if not timesheets.exists():
                return Response({"error": "No timesheet data found for the specified employee."}, status=status.HTTP_404_NOT_FOUND)
            serializer = TimesheetEstimationSerializer(timesheets, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_403_FORBIDDEN)


class EmployeeProjectsView(APIView):
    
    def check_permissions(self, request):
        required_roles = ["c2c_timesheet_manager", "c2c_super_admin", "c2c_timesheet_employee", "c2c_guest_employee"]
        return has_permission(request, required_roles)

    def get_employee(self, employee_id=None, employee_email=None):
        try:
            if employee_id:
                return Employee.objects.get(employee_source_id=employee_id)
            else:
                return Employee.objects.get(employee_email=employee_email)
        except Employee.DoesNotExist:
            raise ValueError("Employee not found.")

    def get_projects(self, employee):
        current_date = timezone.now().date()
        timesheets = EmployeeEntryTimesheet.objects.filter(employee_id=employee.pk).select_related('contract_sow')

        ongoing_projects = []
        completed_projects = []

        for timesheet in timesheets:
            contract = timesheet.contract_sow
            contract_start_date = contract.start_date
            contract_end_date = contract.end_date

            # Handle string date conversion
            if isinstance(contract_start_date, str):
                contract_start_date = datetime.strptime(contract_start_date, DATE_FORMAT).date()
            if isinstance(contract_end_date, str):
                contract_end_date = datetime.strptime(contract_end_date,DATE_FORMAT).date()

            if contract_end_date and contract_end_date < current_date:
                completed_projects.append(timesheet)
            elif contract_start_date <= current_date <= contract_end_date:
                ongoing_projects.append(timesheet)

        return ongoing_projects, completed_projects

    def post(self, request, *args, **kwargs):
        permission_result = self.check_permissions(request)
        if permission_result["status"] != 200:
            return Response(permission_result, status=status.HTTP_403_FORBIDDEN)

        employee_id = request.data.get('employee_id')
        employee_email = request.data.get('employee_email')

        if not employee_id and not employee_email:
            return Response({"error": EMPLOYEE_ERROR_MESSAGE}, status=status.HTTP_400_BAD_REQUEST)

        try:
            employee = self.get_employee(employee_id, employee_email)
            ongoing_projects, completed_projects = self.get_projects(employee)

            ongoing_serializer = EmployeeEntryTimesheetSerializer(ongoing_projects, many=True)
            completed_serializer = EmployeeEntryTimesheetSerializer(completed_projects, many=True)

            response_data = {
                "employee_id": employee.employee_source_id,
                "employee_name": employee.employee_full_name,
                "employee_role": employee.employee_assigned_role,
                "employee_email": employee.employee_email,
                "ongoing_projects_count": len(ongoing_projects),
                "completed_projects_count": len(completed_projects),
                "ongoing_projects": ongoing_serializer.data,
                "completed_projects": completed_serializer.data
            }

            return Response(response_data, status=status.HTTP_200_OK)

        except ValueError as ve:
            return Response({"error": str(ve)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": f"An unexpected error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class AllEmployeeProjectsView(APIView):
    def get(self, request, *args, **kwargs):
        required_roles = ["c2c_timesheet_manager","c2c_super_admin","c2c_guest_employee"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            current_date = timezone.now().date()
            ongoing_projects_count = EmployeeEntryTimesheet.objects.filter(
                contract_sow__end_date__gte=current_date
            ).count()
            completed_projects_count = EmployeeEntryTimesheet.objects.filter(
                contract_sow__end_date__lt=current_date
            ).count()
            totals = EmployeeEntryTimesheet.objects.aggregate(
                total_billable_hours=Sum('billable_hours'),
                total_non_billable_hours=Sum('non_billable_hours'),
                total_unplanned_hours=Sum('unplanned_hours'),
                total_hours_sum=Sum('total_hours')
            )
            return Response({
                "ongoing_projects_count": ongoing_projects_count,
                "completed_projects_count": completed_projects_count,
                "total_billable_hours": totals['total_billable_hours'] or 0,
                "total_non_billable_hours": totals['total_non_billable_hours'] or 0,
                "total_unplanned_hours": totals['total_unplanned_hours'] or 0,
                "total_hours_sum": totals['total_hours_sum'] or 0
            }, status=status.HTTP_200_OK)
        else:
            return Response(result, status=status.HTTP_403_FORBIDDEN)

class TimesheetRetrieveAPIView(APIView):
    def post(self, request, *args, **kwargs):
        required_roles = ["c2c_timesheet_manager", "c2c_super_admin", "c2c_timesheet_employee","c2c_guest_employee"]
        result = has_permission(request, required_roles)

        if result["status"] != 200:
            return Response(result, status=status.HTTP_403_FORBIDDEN)

        employee = self.get_employee(request.query_params)
        if isinstance(employee, Response):
            return employee

        filters = self.build_filters(request.query_params, employee.pk)
        timesheets = EmployeeEntryTimesheet.objects.filter(**filters)

        return self.handle_timesheet_response(timesheets)

    def get_employee(self, query_params):
        """Retrieve employee based on ID or email."""
        employee_id = query_params.get('employee_id')
        employee_email = query_params.get('employee_email')

        if not employee_id and not employee_email:
            return Response({"error": "Either employee_id or employee_email must be provided."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            if employee_id:
                return Employee.objects.get(employee_source_id=employee_id)
            return Employee.objects.get(employee_email=employee_email)
        except Employee.DoesNotExist:
            return Response({"error": "Employee does not exist."}, status=status.HTTP_404_NOT_FOUND)

    def build_filters(self, query_params, employee_id):
        """Construct filter dictionary for timesheet retrieval."""
        filters = {'employee_id': employee_id}
        if query_params.get('year'):
            filters['year'] = query_params['year']
        if query_params.get('week_number'):
            filters['week_number'] = query_params['week_number']
        return filters

    def handle_timesheet_response(self, timesheets):
        """Handle the response for timesheet retrieval."""
        if not timesheets.exists():
            return Response({"message": "No timesheets found for the specified criteria."}, status=status.HTTP_404_NOT_FOUND)

        timesheet_serializer = EmployeeEntryTimesheetSerializer(timesheets, many=True)
        return Response(timesheet_serializer.data, status=status.HTTP_200_OK)