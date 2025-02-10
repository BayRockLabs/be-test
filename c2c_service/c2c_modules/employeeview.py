from .models import Employee, SowContract, Timesheet, EmployeeEntryTimesheet, Client, EmployeeUnplannedNonbillableHours
from .serializer import TimesheetSerializer, EmployeeEntryTimesheetSerializer
from rest_framework.generics import GenericAPIView
from rest_framework.response import Response
from rest_framework import status, serializers
from django.db.models import Count
from rest_framework.views import APIView
from datetime import datetime, timedelta, date, timezone
from django.db.models import Sum, F, Q
from collections import Counter
from c2c_modules.utils import has_permission, get_date_from_utc_time, time_to_hours
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models.functions import Trim, Lower
from django.utils import timezone
import pandas as pd
from django.utils.dateparse import parse_date
from django.http import JsonResponse, HttpResponse
from openpyxl import Workbook
from io import BytesIO
from itertools import chain
from collections import defaultdict
import random
import math

DATE_FORMAT = '%Y-%m-%d'
class Pagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000

class RoleCountsView(GenericAPIView):
    queryset = Employee.objects.all().order_by('employee_source_id')

    def post(self, request, *args, **kwargs):
        role_counts = (
            Employee.objects.filter(employee_status__in=['Active'])
            .values('employee_assigned_role')
            .annotate(count=Count('employee_assigned_role'))
        )
        role_counts_list = [
            {
                "designation": role['employee_assigned_role'],
                "number_of_resources": role['count']
            }
            for role in role_counts
        ]
        return Response(role_counts_list, status=status.HTTP_200_OK)

class RoleEmployeeListView(GenericAPIView):
    queryset = Employee.objects.all()

    def post(self, request, *args, **kwargs):
        role = request.data.get('role')
        if not role:
            return Response({"error": "Role parameter is required."}, status=status.HTTP_400_BAD_REQUEST)

        employees = Employee.objects.filter(
            employee_assigned_role=role,
            employee_status__in=['Active']
        ).values('employee_full_name', 'employee_email', 'employee_work_authorization')

        result = [
            {
                "name": emp['employee_full_name'],
                "email": emp['employee_email'],
                "country": emp['employee_work_authorization'].strip()  # Strip spaces
            }
            for emp in employees
        ]

        return Response(result, status=status.HTTP_200_OK)


class SkillCountsView(GenericAPIView):
    queryset = Employee.objects.all().order_by('employee_source_id')

    def post(self, request, *args, **kwargs):
        all_skills = Employee.objects.filter(
            employee_status__in=['Active']
        ).values_list('employee_skills', flat=True)
        flattened_skills = []
        for skill_string in all_skills:
            if skill_string:
                skills = [skill.strip() for skill in skill_string.split(',')]
                flattened_skills.extend(skills)
        skill_counts = Counter(flattened_skills)
        skill_counts_list = [
            {"skill": skill.title(), "number_of_resources": count}
            for skill, count in skill_counts.items()
        ]
        return Response(skill_counts_list, status=status.HTTP_200_OK)

class SkillEmployeeListView(GenericAPIView):
    queryset = Employee.objects.all().order_by('employee_source_id')

    def post(self, request, *args, **kwargs):
        skill = request.data.get('skill')
        if not skill:
            return Response({"error": "Skill parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        employees = Employee.objects.filter(
            employee_status__in=['Active'],
            employee_skills__icontains=skill
        ).values('employee_full_name', 'employee_email', 'employee_work_authorization')
        result = [
            {
                "name": emp['employee_full_name'],
                "email": emp['employee_email'],
                "country": emp['employee_work_authorization'].strip()
            }
            for emp in employees
        ]
        return Response(result, status=status.HTTP_200_OK)


class EmpTypeCountryCountsView(GenericAPIView):
    queryset = Employee.objects.all().order_by('employee_source_id')

    def post(self, request, *args, **kwargs):
        employees = Employee.objects.filter(employee_status__in=['Active'])
        emp_type_country_counts = (
            employees
            .annotate(
                normalized_work_auth=Lower(Trim('employee_work_authorization'))  # Trim spaces
            )
            .values('employee_category', 'normalized_work_auth')
            .annotate(count=Count('employee_source_id'))
            .order_by('employee_category', 'normalized_work_auth')
        )
        
        result = [
            {
                'employee_type': item['employee_category'] if item['employee_category'] else 'Unknown',
                'region': "USA" if item['normalized_work_auth'].lower() == "usa" else item['normalized_work_auth'].title() if item['normalized_work_auth'] else 'Unknown',
                'number_of_resources': item['count'],
            }
            for item in emp_type_country_counts
        ]

        return Response(result, status=status.HTTP_200_OK)

class EmpTypeCountryEmployeeListView(GenericAPIView):
    queryset = Employee.objects.all().order_by('employee_source_id')

    def post(self, request, *args, **kwargs):
        emp_type = request.data.get('emp_type')
        country = request.data.get('country')

        if not emp_type or not country:
            return Response({"error": "Both emp_type and country parameters are required."}, status=status.HTTP_400_BAD_REQUEST)

        # Normalize the `employee_work_authorization` field and filter
        employees = Employee.objects.annotate(
            normalized_work_auth=Trim('employee_work_authorization')# Remove spaces
        ).filter(
            employee_category=emp_type,
            normalized_work_auth=country.strip(),  # Strip spaces from input
            employee_status__in=['Active']
        ).values(
            'employee_full_name', 'employee_email', 'normalized_work_auth'
        )

        result = [
            {
                "name": emp['employee_full_name'],
                "email": emp['employee_email'],
                "country": emp['normalized_work_auth']
            }
            for emp in employees
        ]
        return Response(result, status=status.HTTP_200_OK)

    
class EmployeeSearchAPIView(APIView):
    DATE_FORMAT = '%Y-%m-%dT%H:%M:%S.%fZ'

    def calculate_weekday_hours(self, start_date, end_date):
        total_hours = 0
        start_date = get_date_from_utc_time(str(start_date))
        end_date = get_date_from_utc_time(str(end_date))
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() < 5:
                total_hours += 8
            current_date += timedelta(days=1)
        return total_hours
        
    def check_timesheet_availability(self, timesheets, start_date, end_date, available_hours):
        total_free_hours = 0
        start_date = get_date_from_utc_time(str(start_date))
        end_date = get_date_from_utc_time(str(end_date))
        for timesheet in timesheets:
            planned_hours_per_day = 0
            estimation_data = timesheet.resource_estimation_data.get('Estimation_Data' , {}).get('daily', [])
            for data in estimation_data:
                est_date = datetime.strptime(data['date'], "%d/%m/%Y")
                est_date = est_date.date()
                if est_date.weekday() in [5, 6]:
                    continue
                if start_date <= est_date <= end_date:
                    if data.get('hours'):
                        worked_hours = data.get('hours', 0)
                    else:
                        worked_hours = 0
                    planned_hours_per_day +=worked_hours
            total_free_hours = available_hours - planned_hours_per_day
            available_hours = total_free_hours
        return available_hours if available_hours > 0 else 0

    def post(self, request, *args, **kwargs):
        employee_name = request.data.get('name')
        start_date = request.data.get('start_date')
        end_date = request.data.get('end_date')
        required_hours = request.data.get('hours')

        # Validate required fields
        if not start_date or not end_date or not required_hours:
            return Response(
                {"error": "Missing required fields: start_date, end_date, or hours."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            start_date = datetime.strptime(start_date, self.DATE_FORMAT)
            end_date = datetime.strptime(end_date, self.DATE_FORMAT)
            required_hours = int(required_hours)
        except (ValueError, TypeError):
            return Response(
                {"error": "Invalid date format or hours. Dates should be in ISO 8601 format, and hours should be an integer."},
                status=status.HTTP_400_BAD_REQUEST
            )

        employees = Employee.objects.all()
        if employee_name:
            employees = employees.filter(employee_full_name__icontains=employee_name)

        filtered_employees = []
        for employee in employees:
            timesheets = Timesheet.objects.filter(
                resource=employee,
                contract_sow__start_date__lte=end_date,
                contract_sow__end_date__gte=start_date
            )
            available_hours = self.calculate_weekday_hours(start_date, end_date)
            if not timesheets.exists():
                filtered_employees.append(self.build_employee_response(employee, available_hours, "Available", 0))
            else:
                free_hours = self.check_timesheet_availability(timesheets, start_date, end_date, available_hours)
                pre_planned_hours = available_hours - free_hours
                status_label = "Available" if free_hours >= required_hours else "Not Available"
                filtered_employees.append(self.build_employee_response(employee, free_hours, status_label, pre_planned_hours))

        return Response(filtered_employees, status=status.HTTP_200_OK)

    def build_employee_response(self, employee, available_hours, status, pre_planned_hours):
        return {
            "resource_id": employee.employee_source_id,
            "resource_name": employee.employee_full_name,
            "available_hours": available_hours,
            "pre_planned_hours": pre_planned_hours,
            "skills": employee.employee_skills,
            "availability_status": status
        }
    
class EmployeeTimesheetView(APIView):
    
    def get_employee(self, employee_email, employee_id):
        if employee_email:
            return Employee.objects.get(employee_email=employee_email)
        return Employee.objects.get(employee_source_id=employee_id)

    def classify_timesheets(self, timesheets, current_date):
        ongoing_timesheets, completed_timesheets = [], []
        for timesheet in timesheets:
            resource_data = timesheet.resource_estimation_data
            if resource_data:
                start_date, end_date = self.parse_dates(resource_data)
                if start_date and end_date:
                    if start_date <= current_date <= end_date:
                        ongoing_timesheets.append(timesheet)
                    elif end_date < current_date:
                        completed_timesheets.append(timesheet)
        return ongoing_timesheets, completed_timesheets

    def parse_dates(self, resource_data):
        try:
            start_date_str = resource_data['start_date'].split('T')[0]
            end_date_str = resource_data['end_date'].split('T')[0]
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except KeyError:
            raise ValueError("Missing start_date or end_date in resource_estimation_data.")
        except Exception as e:
            raise ValueError(f"Error parsing dates: {str(e)}")
        return start_date, end_date

    def calculate_total_hours(self, employee):
        total_unplanned_hours = 0
        total_non_billable_hours = 0
        entry_timesheets = EmployeeUnplannedNonbillableHours.objects.filter(employee_id=employee.employee_source_id)
        if entry_timesheets.exists():
            total_unplanned_hours += sum(entry.unplanned_hours or 0 for entry in entry_timesheets)
            total_non_billable_hours += sum(entry.non_billable_hours or 0 for entry in entry_timesheets)
        unplanned_hours = int(total_unplanned_hours)
        unplanned_minutes = int((total_unplanned_hours - unplanned_hours) * 60)
        unplanned_hours_str = f"{unplanned_hours:02}:{unplanned_minutes:02}"
        non_billable_hours = int(total_non_billable_hours)
        non_billable_minutes = int((total_non_billable_hours - non_billable_hours) * 60)
        non_billable_hours_str = f"{non_billable_hours:02}:{non_billable_minutes:02}"
        return unplanned_hours_str, non_billable_hours_str

    def check_permissions(self, request):
        required_roles = ["c2c_timesheet_manager", "c2c_super_admin", "c2c_timesheet_employee", "c2c_timesheet_admin"]
        return has_permission(request, required_roles)
    
    def post(self, request):
        # permission_result = self.check_permissions(request)
        # if permission_result["status"] != 200:
        #     return Response(permission_result, status=status.HTTP_403_FORBIDDEN)
        employee_email = request.data.get('employee_email')
        employee_id = request.data.get('employee_id')
        if not employee_email and not employee_id:
            return Response({"error": "Please provide either employee_email or employee_id."}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            employee = self.get_employee(employee_email, employee_id)
        except Employee.DoesNotExist:
            return Response({"error": "Employee not found."}, status=status.HTTP_200_OK)

        timesheets = Timesheet.objects.filter(resource=employee)
        current_date = date.today()
        
        ongoing_timesheets, completed_timesheets = self.classify_timesheets(timesheets, current_date)
        total_unplanned_hours, total_non_billable_hours = self.calculate_total_hours(employee)

        ongoing_serializer = TimesheetSerializer(ongoing_timesheets, many=True, context={'employee': employee})
        completed_serializer = TimesheetSerializer(completed_timesheets, many=True, context={'employee': employee})
        role = employee.employee_designation if employee.employee_designation else ""
        response_data = {
            "employee_id": employee.employee_source_id,
            "employee_name": employee.employee_full_name,
            "employee_role": role,
            "employee_email": employee.employee_email,
            "ongoing_projects_counts": len(ongoing_timesheets),
            "completed_projects_counts": len(completed_timesheets),
            "total_unplanned_hours": total_unplanned_hours,
            "non_billable_hours": total_non_billable_hours,
            "ongoing_projects": ongoing_serializer.data,
            "completed_projects": completed_serializer.data,
        }
        return Response(response_data, status=status.HTTP_200_OK)


class AddTimesheetView(APIView):
    
    def get_employee(self, employee_id):
        try:
            return Employee.objects.get(employee_source_id=employee_id)
        except Employee.DoesNotExist:
            raise ValueError(f"Employee with ID {employee_id} does not exist.")

    def get_client(self, client_name):
        if client_name:
            try:
                return Client.objects.get(name=client_name)
            except Client.DoesNotExist:
                raise ValueError(f"Client with name '{client_name}' does not exist.")
        return None

    def get_contract_sow(self, contract_sow_name, client):
        if contract_sow_name and client:
            try:
                return SowContract.objects.get(contractsow_name=contract_sow_name, client=client)
            except SowContract.DoesNotExist:
                raise ValueError(f"Contract SOW with name '{contract_sow_name}' does not exist for client '{client.name}'.")
        return None

    def create_or_update_timesheet(self, employee, client, contract_sow, year, week_number, billable_hours, non_billable_hours, unplanned_hours, total_hours, non_billable_hours_comments, unplanned_hours_comments,user_email):
        try:
            timesheet, _ = Timesheet.objects.get_or_create(
                resource=employee,
                client=client,
                contract_sow=contract_sow,
            )
            approver = timesheet.approver
            entry_timesheet, _ = EmployeeEntryTimesheet.objects.update_or_create(
                timesheet_id=timesheet,
                approver=approver,
                year=year,
                week_number=week_number,
                client=client,
                contract_sow=contract_sow,
                defaults={
                    "billable_hours": time_to_hours(billable_hours),
                    "non_billable_hours": time_to_hours(non_billable_hours),
                    "unplanned_hours": time_to_hours(unplanned_hours),
                    "total_hours": time_to_hours(total_hours),
                    "non_billable_hours_comments": non_billable_hours_comments,
                    "unplanned_hours_comments": unplanned_hours_comments,
                    "employee_id": employee,
                    "username_created": user_email,
                    "username_updated": user_email,
                    "ts_approval_status": "submitted",
                }
            )
            return entry_timesheet
        except Exception as e:
            raise ValueError(f"Error creating/updating Timesheet: {str(e)}")
        
    def create_non_billable_unplanned_entries(self, employee, year, week_number, non_billable_hours, unplanned_hours, non_billable_hours_comments, unplanned_hours_comments,user_email):
        try:
            entry_timesheet = EmployeeUnplannedNonbillableHours.objects.filter(
                employee_id=employee,
                year=year,
                week_number=week_number
            ).first()

            if entry_timesheet:
                entry_timesheet.non_billable_hours = time_to_hours(non_billable_hours)
                entry_timesheet.unplanned_hours = time_to_hours(unplanned_hours)
                entry_timesheet.non_billable_hours_comments = non_billable_hours_comments
                entry_timesheet.unplanned_hours_comments = unplanned_hours_comments
                entry_timesheet.ts_approval_status = "submitted"
                entry_timesheet.username_updated = user_email
                entry_timesheet.save()
            else:
                entry_timesheet = EmployeeUnplannedNonbillableHours.objects.create(
                    employee_id=employee,
                    year=year,
                    week_number=week_number,
                    approver=[{"approver_id": "PMO1", "approver_name": "HR Manager"}],
                    non_billable_hours=time_to_hours(non_billable_hours),
                    unplanned_hours=time_to_hours(unplanned_hours),
                    non_billable_hours_comments=non_billable_hours_comments,
                    unplanned_hours_comments=unplanned_hours_comments,
                    username_created = user_email,
                    ts_approval_status="submitted",
                )

            return entry_timesheet

        except Exception as e:
            raise ValueError(f"Error creating/updating Unplanned and Non Billable hours: {str(e)}")

    def check_permissions(self, request):
        required_roles = ["c2c_super_admin", "c2c_timesheet_employee"]
        return has_permission(request, required_roles)

    def post(self, request, *args, **kwargs):
        employee_id = request.data.get('employee_id')
        year = request.data.get('year')
        week_number = request.data.get('week_number')
        non_billable_hours = time_to_hours(request.data.get('non_billable_hours', 0))
        unplanned_hours = time_to_hours(request.data.get('unplanned_hours', 0))
        total_hours = time_to_hours(request.data.get('total_hours', 0))
        non_billable_hours_comments = request.data.get('non_billable_hours_comments', '')
        unplanned_hours_comments = request.data.get('unplanned_hours_comments', '')
        timesheets_data = request.data.get('timesheets', [])    
        try:
            employee = self.get_employee(employee_id)
        except ValueError as ve:
            return Response({"error": str(ve)}, status=status.HTTP_400_BAD_REQUEST)
        user_email = employee.employee_email
        if not math.isclose(unplanned_hours, 0.0) or not math.isclose(non_billable_hours, 0.0):
            entry_timesheet_unplanned = self.create_non_billable_unplanned_entries(
                employee, year, week_number, non_billable_hours, unplanned_hours, 
                non_billable_hours_comments, unplanned_hours_comments, user_email
            )
        elif math.isclose(unplanned_hours, 0.0) and math.isclose(non_billable_hours, 0.0):
            try:
                record = EmployeeUnplannedNonbillableHours.objects.get(
                    employee_id=employee,
                    year=year,
                    week_number=week_number
                )
                record.unplanned_hours = 0.0
                record.non_billable_hours = 0.0
                record.save()
            except EmployeeUnplannedNonbillableHours.DoesNotExist:
                print("No record found for this employee, year, and week_number.")
        errors = []
        if timesheets_data:
            for entry in timesheets_data:
                client_name = entry.get('client_name')
                contract_sow_name = entry.get('contract_sow_name')
                billable_hours = entry.get('billable_hours', 0)
                non_billable_hours = 0
                unplanned_hours = 0
                non_billable_hours_comments = ""
                unplanned_hours_comments = ""
                try:
                    client = self.get_client(client_name)
                    contract_sow = self.get_contract_sow(contract_sow_name, client)
                    entry_timesheet = self.create_or_update_timesheet(
                        employee,
                        client,
                        contract_sow,
                        year,
                        week_number,
                        billable_hours,
                        non_billable_hours,
                        unplanned_hours,
                        total_hours,
                        non_billable_hours_comments,
                        unplanned_hours_comments,
                        user_email,
                    )
                except ValueError as ve:
                    errors.append({"entry": entry, "error": str(ve)})
            if errors:
                return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"message": "Timesheet entries created/updated successfully."}, status=status.HTTP_201_CREATED)





class EmployeeTimesheetStatusAPIView(APIView):
    def post(self, request, *args, **kwargs):
        client_name = request.data.get('client_name')
        contract_sow_name = request.data.get('contract_sow_name')
        employee_id = request.data.get('employee_id', None)
        employee_email = request.data.get('employee_email', None)
        
        if not (employee_id or employee_email):
            return Response(
                {'error': 'Either employee_id or employee_email is required.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        try:
            employee = Employee.objects.get(employee_source_id=employee_id) if employee_id else Employee.objects.get(employee_email=employee_email)
        except Employee.DoesNotExist:
            return Response(
                {'error': 'Employee not found with the provided ID or email.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        client = None
        if client_name:
            try:
                client = Client.objects.get(name=client_name)
            except Client.DoesNotExist:
                return Response({'error': f"Client '{client_name}' does not exist."}, status=status.HTTP_404_NOT_FOUND)

        contract_sow = None
        if contract_sow_name and client:
            try:
                contract_sow = SowContract.objects.get(contractsow_name=contract_sow_name, client=client)
            except SowContract.DoesNotExist:
                return Response(
                    {'error': f"Contract SOW '{contract_sow_name}' does not exist for client '{client_name}'."},
                    status=status.HTTP_404_NOT_FOUND
                )
        
        filters = {'employee_id': employee}
        if client:
            filters['client'] = client
        if contract_sow:
            filters['contract_sow'] = contract_sow
        
        employee_timesheets = EmployeeEntryTimesheet.objects.filter(**filters)
        timesheet_ids = employee_timesheets.values_list('timesheet_id', flat=True)
        if not timesheet_ids:
            timesheet_ids = Timesheet.objects.filter(
                client=client,
                contract_sow=contract_sow,
                resource=employee
            ).values_list('id', flat=True)
        timesheet_resource_data = Timesheet.objects.filter(id__in=timesheet_ids).values_list('resource_estimation_data', flat=True)
        timesheet_data = self.process_estimation_data(timesheet_resource_data)
        unplanned_timesheets = EmployeeUnplannedNonbillableHours.objects.filter(employee_id=employee)
        unplanned_timesheets = {
            (timesheet.year, timesheet.week_number) : timesheet.ts_approval_status
            for timesheet in unplanned_timesheets
        }
        if not employee_timesheets.exists():
            response_data = self.compare_timesheet_with_employee_entry(timesheet_data, None, client_name, contract_sow_name, unplanned_timesheets)
        else:
            response_data = self.compare_timesheet_with_employee_entry(timesheet_data, employee_timesheets, client_name, contract_sow_name, unplanned_timesheets)
        response_data = sorted(response_data, key=lambda x: x['start_date'], reverse=True)
        for response_ in response_data:
            response_['billable_hours'] = format_hours(response_['billable_hours'])
            response_['non_billable_hours'] = format_hours(response_['non_billable_hours'])
            response_['unplanned_hours'] = format_hours(response_['unplanned_hours'])
        paginator = Pagination()
        paginated_response_data = paginator.paginate_queryset(response_data, request)
        return paginator.get_paginated_response(paginated_response_data)

    def process_estimation_data(self, resource_estimation_data):
        timesheet_data = {}
        current_date = datetime.now()
        current_year, current_week_number, _ = current_date.isocalendar()

        for estimation in resource_estimation_data:
            if estimation:
                daily_data = estimation.get('Estimation_Data', {}).get('daily', [])
                for daily_entry in daily_data:
                    entry_date = datetime.strptime(daily_entry['date'], "%d/%m/%Y")
                    if entry_date.weekday() >= 5:
                        continue  

                    iso_year, iso_week, _ = entry_date.isocalendar()
                    hours = int(daily_entry.get('hours', 0))
                    if iso_year == current_year and iso_week > current_week_number:
                        continue
                    key = (iso_year, iso_week)
                    if key not in timesheet_data:
                        timesheet_data[key] = {
                            'total_hours': 0,
                            'start_date': entry_date,
                            'end_date': entry_date
                        }

                    timesheet_data[key]['total_hours'] += hours
                    timesheet_data[key]['start_date'] = min(timesheet_data[key]['start_date'], entry_date)
                    timesheet_data[key]['end_date'] = max(timesheet_data[key]['end_date'], entry_date)
        return timesheet_data


    def compare_timesheet_with_employee_entry(self, timesheet_data, employee_timesheets, client_name, contract_sow_name, unplanned_timesheets):
        employee_timesheet_data = {}
        if employee_timesheets:
            for timesheet in employee_timesheets:
                key = (timesheet.year, timesheet.week_number)
                unplanned_timesheet_status = unplanned_timesheets.get(key)
                planned_timesheet_status = timesheet.ts_approval_status
                employee_timesheet_data[key] = {
                    'client_name': client_name,
                    'contract_sow_name': contract_sow_name,
                    'billable_hours': timesheet.billable_hours,
                    'non_billable_hours': timesheet.non_billable_hours,
                    'unplanned_hours': timesheet.unplanned_hours,
                    'non_billable_hours_comments': timesheet.non_billable_hours_comments or "",
                    'unplanned_hours_comments': timesheet.unplanned_hours_comments or "",
                    "unplanned_timesheet_status": unplanned_timesheet_status,
                    'timesheet_status': planned_timesheet_status,
                    'manager_comments': timesheet.approver_comments,
                    'submitted': True
                }
        else:
            for week_number, data in timesheet_data.items():
                employee_timesheet_data[week_number] = {
                    'client_name': client_name,
                    'contract_sow_name': contract_sow_name,
                    'billable_hours': 0,
                    'non_billable_hours': 0,
                    'unplanned_hours': 0,
                    'non_billable_hours_comments': "",
                    'unplanned_hours_comments': "",
                    'unplanned_timesheet_status': 'not_submitted',
                    'timesheet_status': 'not_submitted',
                    'manager_comments': '',
                    'submitted': False
                }
        week_report = []
        current_week_number = date.today().isocalendar()[1]
        current_year = date.today().isocalendar()[0]
        for week_number, data in timesheet_data.items():
            iso_year, iso_week = week_number
            if iso_week > current_week_number and iso_year >= current_year:
                continue
            
            key = (iso_year, iso_week)
            timesheet_entry = employee_timesheet_data.get(key, {})

            report_entry = {
                'start_date': data['start_date'],
                'end_date': data['end_date'],
                'week_number': iso_week,
                'year': iso_year,
                'allocated_hours': data['total_hours'],
                'client_name': timesheet_entry.get('client_name', client_name),
                'contract_sow_name': timesheet_entry.get('contract_sow_name', contract_sow_name),
                'billable_hours': timesheet_entry.get('billable_hours', None),
                'non_billable_hours': timesheet_entry.get('non_billable_hours', None),
                'unplanned_hours': timesheet_entry.get('unplanned_hours', None),
                'non_billable_hours_comments': timesheet_entry.get('non_billable_hours_comments', ""),
                'unplanned_hours_comments': timesheet_entry.get('unplanned_hours_comments', ""),
                'unplanned_timesheet_status': timesheet_entry.get('unplanned_timesheet_status', 'not_submitted'),
                'timesheet_status': timesheet_entry.get('timesheet_status', 'not_submitted'),
                'manager_comments': timesheet_entry.get('manager_comments', ""),
                'submitted': timesheet_entry.get('submitted', False)
            }
            week_report.append(report_entry)
        status_order = {'recall': 0, 'not_submitted': 1, 'submitted': 2, 'approved': 3}
        week_report.sort(key=lambda x: status_order.get(x['timesheet_status'], 4))
        return week_report
    
def get_week_range():
    """Get the start and end date for the current week (only weekdays)."""
    today = datetime.now().date()
    start_of_week = today - timedelta(days=today.weekday())
    end_of_week = start_of_week + timedelta(days=4)
    return start_of_week, end_of_week

def get_estimation_data_for_week(estimation_data, start_of_week, end_of_week):
    """Calculate the total hours allocated for the week from estimation data."""
    total_hours = 0
    daily_entries = None
    if 'Estimation_Data' in estimation_data:
        daily_entries = estimation_data['Estimation_Data'].get('daily')
    if daily_entries:
        for day_entry in daily_entries:
            entry_date = datetime.strptime(day_entry['date'], '%d/%m/%Y').date()
            if start_of_week <= entry_date <= end_of_week:
                total_hours += day_entry.get('hours', 0)
    return total_hours

class ClientTimesheetView(APIView):
    class ClientTimesheetInputSerializer(serializers.Serializer):
        client_names = serializers.ListField(
            child=serializers.CharField(), required=False, allow_empty=True
        )
        employee_id = serializers.IntegerField(required=False)
        employee_email = serializers.EmailField(required=False)

    
    def post(self, request, *args, **kwargs):
        serializer = self.ClientTimesheetInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        client_names = serializer.validated_data.get('client_names', [])
        start_of_week = request.data.get('start_date')
        end_of_week = request.data.get('end_date')
        if start_of_week:
            start_of_week = datetime.strptime(start_of_week, "%Y-%m-%d").date()

        if end_of_week:
            end_of_week = datetime.strptime(end_of_week, "%Y-%m-%d").date()
        employee_id = serializer.validated_data.get('employee_id')
        employee_email = serializer.validated_data.get('employee_email')
        if not employee_id and not employee_email:
            return Response(
                {'error': 'Either employee_id or employee_email is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        try:
            employee = Employee.objects.get(employee_source_id=employee_id) if employee_id else Employee.objects.get(employee_email=employee_email)
        except Employee.DoesNotExist:
            return Response({'error': 'No matching employee found for the provided identifier'}, status=status.HTTP_404_NOT_FOUND)
        if client_names:
            clients = Client.objects.filter(name__in=client_names)
            if not clients.exists():
                return Response({'error': 'No matching clients found for provided names'}, status=status.HTTP_404_NOT_FOUND)
            timesheets = Timesheet.objects.filter(client__in=clients, resource=employee)
        else:
            timesheets = Timesheet.objects.filter(resource=employee)
        result = []
        if not start_of_week and not end_of_week:
            start_of_week, end_of_week = get_week_range()
        year, week_number, _ = start_of_week.isocalendar()
        try:
            unplanned_timeoff_record = EmployeeUnplannedNonbillableHours.objects.filter(employee_id=employee, week_number=week_number, year=year).first()
        except:
            unplanned_timeoff_record = None
        unplanned_hours = unplanned_timeoff_record.unplanned_hours if unplanned_timeoff_record else 0
        timeoff_hours = unplanned_timeoff_record.non_billable_hours if unplanned_timeoff_record else 0
        unplanned_timesheet_status = unplanned_timeoff_record.ts_approval_status if unplanned_timeoff_record else ""
        timeoff_hours_comments = unplanned_timeoff_record.non_billable_hours_comments if unplanned_timeoff_record else ""
        unplanned_hours_comments = unplanned_timeoff_record.unplanned_hours_comments if unplanned_timeoff_record else ""
        total_hours = 0
        for timesheet in timesheets:
            estimation_data = timesheet.resource_estimation_data
            end_date = datetime.fromisoformat(estimation_data['end_date'].replace("Z", "")).date()
            start_date = datetime.fromisoformat(estimation_data['start_date'].replace("Z", "")).date()
            if start_of_week > end_date or end_of_week < start_date:
                continue
            allocated_hours = get_estimation_data_for_week(estimation_data, start_of_week, end_of_week)
            try:
                entry_timesheet_record = EmployeeEntryTimesheet.objects.filter(timesheet_id=timesheet, week_number=week_number, year=year).first()
            except:
                entry_timesheet_record = None
            manager_comments = entry_timesheet_record.approver_comments if entry_timesheet_record else ""
            timesheet_status = entry_timesheet_record.ts_approval_status if entry_timesheet_record else "not_submitted"
            non_billable_hours = entry_timesheet_record.non_billable_hours if entry_timesheet_record else 0
            billable_hours = entry_timesheet_record.billable_hours if entry_timesheet_record else 0
            total_hours += billable_hours + non_billable_hours
            result.append({
                "client_name": timesheet.client.name if timesheet.client else "N/A",
                "contract_sow_name": timesheet.contract_sow.contractsow_name if timesheet.contract_sow else "N/A",
                "allocated_hours": format_hours(allocated_hours),
                "non_billable_hours": format_hours(non_billable_hours),
                "billable_hours": format_hours(billable_hours),
                "week_start_date": start_of_week,
                "week_end_date": end_of_week,
                "manager_comments": manager_comments,
                "timesheet_status": timesheet_status,
            })
        total_hours_total = total_hours + unplanned_hours + timeoff_hours
        data = {
            "employee_id": employee.employee_source_id,
            "employee_name": employee.employee_full_name,
            "week_number": week_number,
            "year": year,
            "total_hours": format_hours(total_hours_total),
            "unplanned_hours": format_hours(unplanned_hours),
            "timeoff_hours": format_hours(timeoff_hours),
            "unplanned_hours_comments": unplanned_hours_comments,
            "timeoff_hours_comments": timeoff_hours_comments,
            "unplanned_timesheet_status": unplanned_timesheet_status,
            "timesheets" : result,
        }
        return Response(data, status=status.HTTP_200_OK)
    
def get_week_dates(year, week_number):
    first_day_of_year = datetime.strptime(f'{year}-01-01', DATE_FORMAT)
    start_date = first_day_of_year + timedelta(days=(week_number - 1) * 7 - first_day_of_year.weekday())
    end_date = start_date + timedelta(days=6)
    return start_date.date(), end_date.date()
    
class UnplannedHoursView(APIView):
    def post(self, request):
        employee_id = request.data.get('employee_id')
        employee_email = request.data.get('employee_email')
        if employee_id:
            employee = get_object_or_404(Employee, employee_source_id=employee_id)
        elif employee_email:
            employee = get_object_or_404(Employee, employee_email=employee_email)
        else:
            return Response({"error": "Please provide either employee_id or employee_email"}, status=status.HTTP_400_BAD_REQUEST)

        timesheets = EmployeeUnplannedNonbillableHours.objects.filter(
            employee_id=employee,
            unplanned_hours__isnull=False
        ).values('unplanned_hours', 'unplanned_hours_comments', 'week_number', 'year')

        data = []
        for timesheet in timesheets:
            week_number = timesheet['week_number']
            year = timesheet['year']
            start_date, end_date = get_week_dates(year, week_number)

            data.append({
                "unplanned_hours": timesheet['unplanned_hours'],
                "unplanned_hours_comments": timesheet['unplanned_hours_comments'],
                "week_number": week_number,
                "year": year,
                "start_date": start_date,
                "end_date": end_date
            })
        paginator = Pagination()
        paginated_response_data = paginator.paginate_queryset(data, request)
        return paginator.get_paginated_response(paginated_response_data)

class TimeOffHoursView(APIView):
    def post(self, request):
        employee_id = request.data.get('employee_id')
        employee_email = request.data.get('employee_email')
        if employee_id:
            employee = get_object_or_404(Employee, employee_source_id=employee_id)
        elif employee_email:
            employee = get_object_or_404(Employee, employee_email=employee_email)
        else:
            return Response({"error": "Please provide either employee_id or employee_email"}, status=status.HTTP_400_BAD_REQUEST)

        timesheets = EmployeeUnplannedNonbillableHours.objects.filter(
            employee_id=employee,
            unplanned_hours__isnull=False
        ).values('non_billable_hours', 'non_billable_hours_comments', 'week_number', 'year')

        data = []
        for timesheet in timesheets:
            week_number = timesheet['week_number']
            year = timesheet['year']
            start_date, end_date = get_week_dates(year, week_number)

            data.append({
                "non_billable_hours": timesheet['non_billable_hours'],
                "non_billable_hours_comments": timesheet['non_billable_hours_comments'],
                "week_number": week_number,
                "year": year,
                "start_date": start_date,
                "end_date": end_date
            })
        paginator = Pagination()
        paginated_response_data = paginator.paginate_queryset(data, request)
        return paginator.get_paginated_response(paginated_response_data)

class EmployeeHoursView(APIView):

    def get_weeks_between_dates(self, start_date, end_date):
        if start_date > end_date:
            raise ValueError("start_date must be earlier than or equal to end_date")
        current_date = start_date
        weeks = set()
        while current_date <= end_date:
            year, week_number, _ = current_date.isocalendar()
            weeks.add((year, week_number))
            current_date += timedelta(days=1)
        return sorted(weeks)

    def post(self, request, *args, **kwargs):
        required_roles = ["c2c_timesheet_export_user","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] != 200:
            return Response({"result": result}, status=status.HTTP_403_FORBIDDEN)
        today = date.today()
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")
        allocation_type = request.data.get("allocation_type", "overview_timesheet")
        export_type = request.data.get("export_type", "json")
        if not start_date or not end_date:
            start_date = today - timedelta(days=today.weekday() + 7)
            end_date = start_date + timedelta(days=4)
        try:
            start_date = parse_date(start_date) if isinstance(start_date, str) else start_date
            end_date = parse_date(end_date) if isinstance(end_date, str) else end_date
        except ValueError:
            return Response({"error": "Invalid date format"}, status=status.HTTP_400_BAD_REQUEST)
        weeks_list = self.get_weeks_between_dates(start_date, end_date)
        week_filters = Q()
        for year, week_number in weeks_list:
            week_filters |= Q(year=year, week_number=week_number)
        timesheet_data = EmployeeEntryTimesheet.objects.filter(
            week_filters
        ).values(
            "year", "week_number", "employee_id", "client_id", "contract_sow_id", "timesheet_id","ts_approval_status",
            "approver_comments", "approved_by"
        ).annotate(
            billable_hours=Sum("billable_hours"),
            non_billable_hours=Sum("non_billable_hours"),
        )
        timesheet_aggregated = defaultdict(list)
        for entry in timesheet_data:
            key = (entry["year"], entry["week_number"], entry["employee_id"])
            if allocation_type == "overview_timesheet":
                if not timesheet_aggregated[key]:
                    timesheet_aggregated[key] = {
                        "billable_hours": 0,
                        "non_billable_hours": 0,
                        "allocated_hours": 0,
                        "details": []
                    }
                timesheet_aggregated[key]["billable_hours"] += entry["billable_hours"]
                timesheet_aggregated[key]["non_billable_hours"] += entry["non_billable_hours"]
                timesheet_id = entry["timesheet_id"]
                entry_timesheet = Timesheet.objects.filter(id=timesheet_id).first()
                if entry_timesheet and entry_timesheet.resource_estimation_data:
                    week_start_date, week_end_date = get_week_start_and_end_dates(entry["year"], entry["week_number"])
                    daily_data = entry_timesheet.resource_estimation_data.get("Estimation_Data", {}).get("daily", [])
                    filtered_data = [
                        day for day in daily_data
                        if week_start_date <= datetime.strptime(day["date"], "%d/%m/%Y").date() <= week_end_date
                    ]
                    allocated_hours = sum(day["hours"] for day in filtered_data)
                    timesheet_aggregated[key]["allocated_hours"] += allocated_hours

                timesheet_aggregated[key]["details"].append(entry)

            elif allocation_type == "detailed_timesheet":
                timesheet_aggregated[key].append(entry)

        # Get unplanned data
        unplanned_data = EmployeeUnplannedNonbillableHours.objects.filter(
            week_filters
        ).values(
            "year", "week_number", "employee_id",
                "non_billable_hours", "unplanned_hours",
                "unplanned_hours_comments", "non_billable_hours_comments","ts_approval_status",
                "approver_comments", "approved_by"
            )
        unplanned_dict = {
            (entry["year"], entry["week_number"], entry["employee_id"]): entry
            for entry in unplanned_data
        }
        result = []
        all_keys = set(timesheet_aggregated.keys()) | set(unplanned_dict.keys())
        for key in all_keys:
            year, week_number, employee_id = key
            week_start_date, week_end_date = get_week_start_and_end_dates(year, week_number)
            unplanned_entry = unplanned_dict.get(key, {})

            if allocation_type == "overview_timesheet":
                timesheet_entry = timesheet_aggregated.get(key, {})
                employee_name = Employee.objects.filter(employee_source_id=employee_id).first().employee_full_name
                result.append({
                    "year": year,
                    "week_number": week_number,
                    "employee_id": employee_id,
                    "employee_name": employee_name,
                    "week_start_date": week_start_date,
                    "week_end_date": week_end_date,
                    "allocated_hours": timesheet_entry.get("allocated_hours", 0),
                    "billable_hours": timesheet_entry.get("billable_hours", 0),
                    "non_billable_hours": unplanned_entry.get("non_billable_hours", 0),
                    "timeoff_hours": unplanned_entry.get("non_billable_hours", 0),
                    "unplanned_hours": unplanned_entry.get("unplanned_hours", 0),
                })
            elif allocation_type == "detailed_timesheet":
                details = timesheet_aggregated.get(key, [])
                if details == []:
                    continue
                detailed_entries = []
                for entry in details:
                    allocated_hours = 0
                    timesheet_id = entry["timesheet_id"]
                    entry_timesheet = Timesheet.objects.filter(id=timesheet_id).first()
                    employee_name = Employee.objects.filter(employee_source_id=employee_id).first().employee_full_name
                    if entry_timesheet and entry_timesheet.resource_estimation_data:
                        daily_data = entry_timesheet.resource_estimation_data.get("Estimation_Data", {}).get("daily", [])
                        filtered_data = [
                            day for day in daily_data
                            if week_start_date <= datetime.strptime(day["date"], "%d/%m/%Y").date() <= week_end_date
                        ]
                        allocated_hours = sum(day["hours"] for day in filtered_data)

                    client = Client.objects.filter(uuid=entry["client_id"]).first()
                    contract_sow = SowContract.objects.filter(uuid=entry["contract_sow_id"]).first()
                    client_name = client.name if client else "Unknown"
                    contract_sow_name = contract_sow.contractsow_name if contract_sow else "Unknown"

                    detailed_entries.append({
                        "client_name": client_name,
                        "contract_sow_name": contract_sow_name,
                        "allocated_hours": allocated_hours,
                        "billable_hours": entry["billable_hours"],
                        "non_billable_hours": entry["non_billable_hours"],
                        "timesheet_status": entry["ts_approval_status"],
                        "approver_comments": entry["approver_comments"],
                        "approved_by": entry["approved_by"],
                    })

                result.append({
                    "year": year,
                    "week_number": week_number,
                    "employee_id": employee_id,
                    "employee_name": employee_name,
                    "week_start_date": week_start_date,
                    "week_end_date": week_end_date,
                    "details": detailed_entries,
                    "timeoff_hours": unplanned_entry.get("non_billable_hours", 0),
                    "unplanned_hours": unplanned_entry.get("unplanned_hours", 0),
                    "unplanned_hours_comments": unplanned_entry.get("unplanned_hours_comments", ""),
                    "timeoff_hours_comments": unplanned_entry.get("non_billable_hours_comments", ""),
                    "unplanned_timesheet_status": unplanned_entry.get("ts_approval_status", ""),
                    "approver_comments": unplanned_entry.get("approver_comments", ""),
                    "approved_by": unplanned_entry.get("approved_by", ""),
                })
        if export_type == "excel":
            return export_to_excel(result,allocation_type)
        else:
            return JsonResponse(result, safe=False, status=status.HTTP_200_OK)
    
def get_week_start_and_end_dates(year, week_number):
    """
    Returns the start and end date for the given year and ISO week number.
    """
    first_day_of_year = date(year, 1, 1)
    first_weekday = first_day_of_year.weekday()
    days_to_add = (week_number - 1) * 7 - first_weekday
    start_date = first_day_of_year + timedelta(days=days_to_add)
    end_date = start_date + timedelta(days=4)
    return start_date, end_date
def export_to_excel(data, allocation_type):
    """
    Convert the given data to an Excel file and return it as a response.
    Handles both overview_timesheet and detailed_timesheet formats.
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Timesheet Data"

    # Set headers
    if allocation_type == "overview_timesheet":
        headers = [
            "Year", "Week Number", "Employee ID", "Employee Name", "Week Start Date", "Week End Date",
            "Allocated Hours", "Billable Hours","Non Billable Hours", "Time Off Hours", "Unplanned Hours"
        ]
        ws.append(headers)

        # Fill data for overview_timesheet
        for row in data:
            ws.append([
                row["year"], row["week_number"], row["employee_id"],row["employee_name"],
                row["week_start_date"], row["week_end_date"],
                row["allocated_hours"], row["billable_hours"],row["non_billable_hours"],
                row["timeoff_hours"], row["unplanned_hours"]
            ])

    elif allocation_type == "detailed_timesheet":
        headers = [
            "Year", "Week Number", "Employee ID", "Employee Name", "Week Start Date", "Week End Date",
            "Client Name", "Contract SOW Name", "Allocated Hours", "Billable Hours","Non Billable Hours", "Project Timesheet Status",
            "Project Approver Comments", "Project Timesheet Approved By",
            "Time Off Hours", "Unplanned Hours", "Unplanned Hours Comments", "Time Off Hours Comments",
            "Non Working/Timeoff (HR) Timesheet Status", "HR Approver Comments", "HR Approved By" 
        ]
        ws.append(headers)

        # Fill data for detailed_timesheet
        for row in data:
            year = row["year"]
            week_number = row["week_number"]
            employee_id = row["employee_id"]
            employee_name = row["employee_name"]
            week_start_date = row["week_start_date"]
            week_end_date = row["week_end_date"]
            non_billable_hours = row["timeoff_hours"]
            unplanned_hours = row["unplanned_hours"]
            unplanned_hours_comments = row["unplanned_hours_comments"]
            non_billable_hours_comments = row["timeoff_hours_comments"]
            unplanned_approval_status = row["unplanned_timesheet_status"]
            unplanned_approver_comments = row["approver_comments"]
            unplanned_approved_by = row["approved_by"]

            # If there are details, iterate through each entry in the details
            if "details" in row and row["details"]:
                for entry in row["details"]:
                    client_name = entry["client_name"]
                    contract_sow_name = entry["contract_sow_name"]
                    allocated_hours = entry["allocated_hours"]
                    billable_hours = entry["billable_hours"]
                    non_billable_hours = entry["non_billable_hours"]
                    timesheet_status = entry["timesheet_status"]
                    approver_comments = entry["approver_comments"]
                    approved_by = entry["approved_by"]
                    # Append each entry as a new row
                    ws.append([
                        year, week_number, employee_id,employee_name,
                        week_start_date, week_end_date,
                        client_name, contract_sow_name,
                        allocated_hours, billable_hours,non_billable_hours,timesheet_status, approver_comments, approved_by,
                        non_billable_hours, unplanned_hours, unplanned_hours_comments,
                        non_billable_hours_comments,
                        unplanned_approval_status, unplanned_approver_comments, unplanned_approved_by
                    ])
            else:
                # If no details, add a row with N/A for client and contract info
                ws.append([
                    year, week_number, employee_id,employee_name,
                    week_start_date, week_end_date,
                    "N/A", "N/A", 0, 0, non_billable_hours, unplanned_hours, unplanned_hours_comments,
                    non_billable_hours_comments,
                    unplanned_approval_status, unplanned_approver_comments, unplanned_approved_by
                ])

    # Save to an in-memory file and return as response
    excel_file = BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)

    response = HttpResponse(excel_file, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    response['Content-Disposition'] = 'attachment; filename="timesheet_data.xlsx"'
    return response

class EmployeeHoursDownloadView(APIView):

    def get(self, request, *args, **kwargs):
        # required_roles = ["c2c_timesheet_export_user","c2c_super_admin"]
        # result = has_permission(request, required_roles)
        # if result["status"] != 200:
        #     return Response({"result": result}, status=status.HTTP_403_FORBIDDEN)
        today = date.today()
        allocation_type = "overview_timesheet"
        start_date = today - timedelta(days=today.weekday() + 7)
        end_date = start_date + timedelta(days=4)
        try:
            start_date = parse_date(start_date) if isinstance(start_date, str) else start_date
            end_date = parse_date(end_date) if isinstance(end_date, str) else end_date
        except ValueError:
            return Response({"error": "Invalid date format"}, status=status.HTTP_400_BAD_REQUEST)
        timesheet_data = EmployeeEntryTimesheet.objects.filter(
            year__gte=start_date.year,
            year__lte=end_date.year,
        ).values(
            "year", "week_number", "employee_id", "client_id", "contract_sow_id", "timesheet_id"
        ).annotate(
            billable_hours=Sum("billable_hours")
        )
        timesheet_aggregated = defaultdict(list)
        for entry in timesheet_data:
            key = (entry["year"], entry["week_number"], entry["employee_id"])
            if not timesheet_aggregated[key]:
                timesheet_aggregated[key] = {
                    "billable_hours": 0,
                    "allocated_hours": 0,
                    "details": []
                }
            timesheet_aggregated[key]["billable_hours"] += entry["billable_hours"]

            timesheet_id = entry["timesheet_id"]
            entry_timesheet = Timesheet.objects.filter(id=timesheet_id).first()
            if entry_timesheet and entry_timesheet.resource_estimation_data:
                week_start_date, week_end_date = get_week_start_and_end_dates(entry["year"], entry["week_number"])
                daily_data = entry_timesheet.resource_estimation_data.get("Estimation_Data", {}).get("daily", [])
                filtered_data = [
                    day for day in daily_data
                    if week_start_date <= datetime.strptime(day["date"], "%d/%m/%Y").date() <= week_end_date
                ]
                allocated_hours = sum(day["hours"] for day in filtered_data)
                timesheet_aggregated[key]["allocated_hours"] += allocated_hours

            timesheet_aggregated[key]["details"].append(entry)
        unplanned_data = EmployeeUnplannedNonbillableHours.objects.filter(
            year__gte=start_date.year,
            year__lte=end_date.year,
        ).values(
            "year", "week_number", "employee_id"
        ).annotate(
            non_billable_hours=Sum("non_billable_hours"),
            unplanned_hours=Sum("unplanned_hours"),
        )
        unplanned_dict = {
            (entry["year"], entry["week_number"], entry["employee_id"]): entry
            for entry in unplanned_data
        }
        result = []
        all_keys = set(timesheet_aggregated.keys()) | set(unplanned_dict.keys())
        for key in all_keys:
            year, week_number, employee_id = key
            week_start_date, week_end_date = get_week_start_and_end_dates(year, week_number)
            unplanned_entry = unplanned_dict.get(key, {})
            timesheet_entry = timesheet_aggregated.get(key, {})
            employee_name = Employee.objects.filter(employee_source_id=employee_id).first().employee_full_name
            result.append({
                "year": year,
                "week_number": week_number,
                "employee_id": employee_id,
                "employee_name": employee_name,
                "week_start_date": week_start_date,
                "week_end_date": week_end_date,
                "allocated_hours": timesheet_entry.get("allocated_hours", 0),
                "billable_hours": timesheet_entry.get("billable_hours", 0),
                "timeoff_hours": unplanned_entry.get("non_billable_hours", 0),
                "unplanned_hours": unplanned_entry.get("unplanned_hours", 0),
            })
        return export_to_excel(result, allocation_type)

def format_hours(hours):
    """Convert decimal hours to HH:MM format."""
    if hours is None:
        hours = 0
    total_minutes = int(hours * 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02}:{minutes:02}"

class RecallTimesheetView(APIView):

    def get_employee(self, employee_email, employee_id):
        if employee_email:
            return Employee.objects.get(employee_email=employee_email)
        return Employee.objects.get(employee_source_id=employee_id)

    def post(self, request, *args, **kwargs):
        from datetime import datetime, timedelta
        
        start_date = request.data.get("start_date")
        end_date = request.data.get("end_date")
        employee_id = request.data.get("employee_id", None)
        employee_email = request.data.get("employee_email", None)

        if not start_date or not end_date:
            return Response({"error": "Please provide start_date and end_date."}, status=status.HTTP_400_BAD_REQUEST)
        
        if not employee_email and not employee_id:
            return Response({"error": "Please provide either employee_email or employee_id."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            employee = self.get_employee(employee_email, employee_id)
        except Employee.DoesNotExist:
            return Response({"error": "Employee not found."}, status=status.HTTP_404_NOT_FOUND)
        
        try:
            start_date = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date, "%Y-%m-%d").date()
        except ValueError:
            return Response({"error": "Invalid date format. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)
        year, week_number, _ = start_date.isocalendar()
        response_data = {
            "employee_id": employee.employee_source_id,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "week_number": week_number,
            "year": year,
            "total_hours": "00:00",
            "timeoff_hours": "00:00",
            "unplanned_hours": "00:00",
            "timeoff_hours_comments": "",
            "unplanned_hours_comments": "",
            "hr_manager_comments": "",
            "unplanned_timesheet_status": "",
            "timesheets": []
        }
        try:
            unplanned_timeoff_record = EmployeeUnplannedNonbillableHours.objects.filter(employee_id=employee, week_number=week_number, year=year).first()
        except:
            unplanned_timeoff_record = None
        unplanned_hours = unplanned_timeoff_record.unplanned_hours if unplanned_timeoff_record else 0
        timeoff_hours = unplanned_timeoff_record.non_billable_hours if unplanned_timeoff_record else 0
        if not unplanned_hours:
            unplanned_hours = 0
        if not timeoff_hours:
            timeoff_hours = 0
        timeoff_hours_comments = unplanned_timeoff_record.non_billable_hours_comments if unplanned_timeoff_record else ""
        unplanned_hours_comments = unplanned_timeoff_record.unplanned_hours_comments if unplanned_timeoff_record else ""
        response_data['unplanned_hours'] = format_hours(unplanned_hours)
        response_data['timeoff_hours'] = format_hours(timeoff_hours)
        response_data['unplanned_hours_comments'] = unplanned_hours_comments
        response_data['timeoff_hours_comments'] = timeoff_hours_comments
        response_data['unplanned_timesheet_status'] = unplanned_timeoff_record.ts_approval_status if unplanned_timeoff_record else ""
        response_data['hr_manager_comments'] = unplanned_timeoff_record.approver_comments if unplanned_timeoff_record else ""
        timesheets = EmployeeEntryTimesheet.objects.filter(
            employee_id=employee,
            week_number = week_number,
            year = year
        )

        total_billable_hours = 0
        for ts in timesheets:
            data = ts.timesheet_id.resource_estimation_data
            if data:
                daily_data = data.get("Estimation_Data", {}).get("daily", [])
                filtered_data = [
                    day for day in daily_data
                    if start_date <= datetime.strptime(day["date"], "%d/%m/%Y").date() <= end_date
                ]
                allocated_hours = sum(day["hours"] for day in filtered_data)
            else:
                allocated_hours = 0
            billable_hours = ts.billable_hours or 0
            total_billable_hours += billable_hours

            timesheet_entry = {
                "client_name": ts.client.name if ts.client else "Unknown Client",
                "contract_sow_name": ts.contract_sow.contractsow_name if ts.contract_sow else "Unknown Contract",
                "allocated_hours": format_hours(allocated_hours),
                "billable_hours": format_hours(billable_hours),
                "manager_comments": ts.approver_comments or "",
                "timesheet_status": ts.ts_approval_status or ""
            }
            response_data['timesheets'].append(timesheet_entry)
        total_hours = total_billable_hours+ unplanned_hours+ timeoff_hours
        response_data['total_hours'] = format_hours(total_hours)

        return Response(response_data, status=status.HTTP_200_OK)
