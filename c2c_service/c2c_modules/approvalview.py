from rest_framework.views import APIView
from rest_framework.response import Response
from c2c_modules.utils import has_permission, check_role
from c2c_modules.models import GuestUser, Employee, EmployeeEntryTimesheet, Timesheet, EmployeeUnplannedNonbillableHours
from c2c_modules.serializer import UnplannedHoursSerializer, GuestUserSerializer, EmployeeSerializer, AdminApprovalPendingSerializer,ApprovalPendingSerializer, EmployeeUnplannedNonbillableHoursSerializer
from rest_framework import status
from django.db.models import Q
from collections import defaultdict
from config import PROFILE
import datetime
from django.utils.timezone import now
from c2c_modules.employeeview import get_estimation_data_for_week, format_hours
from rest_framework.pagination import PageNumberPagination
from datetime import datetime, timedelta, date
from django.db import transaction
from django.core.exceptions import ObjectDoesNotExist
import math
class Pagination(PageNumberPagination):
    page_size = 100
    page_size_query_param = 'page_size'
    max_page_size = 1000

def get_approver_by_email(approver_email=None):
    if approver_email:
        guest_user = GuestUser.objects.filter(guest_user_email_id=approver_email).first()
        if guest_user:
            return guest_user.guest_user_id
        employee = Employee.objects.filter(employee_email=approver_email).first()
        if employee:
            return employee.employee_source_id
    return None

class TimesheetApproverSearchView(APIView):
    def get_guest_by_client_id(self, client_id):
        try:
            guest_user_instances = GuestUser.objects.filter(client_ids__contains=[client_id])
            if not guest_user_instances.exists():
                return None
            serializer = GuestUserSerializer(guest_user_instances, many=True)
            serialized_data = serializer.data
            return serialized_data
        except GuestUser.DoesNotExist:
            return None
        
    def get_employee_by_employee_id(self):
        employee_instance = Employee.objects.all()
        serializer = EmployeeSerializer(employee_instance, many=True)
        serialized_data = serializer.data
        return serialized_data
    def post(self, request):
        required_roles = ["c2c_timesheet_manager", "c2c_super_admin", "c2c_timesheet_employee"]
        result = has_permission(request, required_roles)
        if result["status"] != 200:
            return Response(result, status=status.HTTP_403_FORBIDDEN)
        client_id = request.data.get('client_id', '')
        guest_user_data = self.get_guest_by_client_id(client_id)
        employee_data = self.get_employee_by_employee_id()
        if guest_user_data:
            response_data = guest_user_data + employee_data
        else:
            response_data = employee_data
        return Response(response_data, status=200)

    
class ApprovalPendingListView(APIView):

    def get_billability_status(self, timesheet_record) -> bool:
        if (timesheet_record and 
            getattr(timesheet_record, 'resource_estimation_data', None) and 
            isinstance(timesheet_record.resource_estimation_data, dict) and 
            "billability" in timesheet_record.resource_estimation_data):
            return timesheet_record.resource_estimation_data["billability"] == "Billable"
        return False
    
    def transform_data(self, serialized_data, approver_id) -> list:
        grouped_data = defaultdict(lambda: {"pending_timesheets": [], "isBillable": False})

        for record in serialized_data:
            employee_id = record["employee_id"]
            employee_name = record["employee_name"]
            if employee_id == approver_id and PROFILE == "PROD":
                continue
            
            # Set employee details if not already set
            if "employee_name" not in grouped_data[employee_id]:
                grouped_data[employee_id]["employee_name"] = employee_name
                grouped_data[employee_id]["employee_id"] = employee_id
            
            week = record["pending_timesheets"]["week"]
            week_number = record["pending_timesheets"]["week_number"]
            contracts = record["pending_timesheets"].get("contracts", [])
            unplanned_hours = record["pending_timesheets"]["unplanned_hours"]
            timeoff_hours = record["pending_timesheets"]["timeoff_hours"]
            timesheet_id = record.get("timesheet_id")
            if not timesheet_id:
                continue

            timesheet_record = Timesheet.objects.filter(
                id=timesheet_id,
            ).first()
            grouped_data[employee_id]["isBillable"] = self.get_billability_status(timesheet_record)

            week_data = next(
                (week for week in grouped_data[employee_id]["pending_timesheets"] if week["week_number"] == week_number),
                None
            )
            
            if week_data:
                week_data["contracts"].extend(contracts)
            else:
                grouped_data[employee_id]["pending_timesheets"].append({
                    "week": week,
                    "week_number": week_number,
                    "contracts": contracts,
                    "unplanned_hours": unplanned_hours,
                    "timeoff_hours": timeoff_hours,
                })
        
        return list(grouped_data.values())
    

    def check_permissions(self, request):
        required_roles = ["c2c_timesheet_manager", "c2c_super_admin", "c2c_guest_employee", "c2c_timesheet_admin"]
        return has_permission(request, required_roles)

    def post(self, request):
        permission_result = self.check_permissions(request)
        if permission_result["status"] != 200:
            return Response(permission_result, status=status.HTTP_403_FORBIDDEN)
        approver_email = request.data.get("approver_email")
        if not approver_email:
            return Response(
                {"error": "approver_email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        approver_id = get_approver_by_email(approver_email=approver_email)
        approver_user_roles = permission_result.get('user_roles')
        if check_role("c2c_timesheet_admin") in approver_user_roles:
            timesheets = EmployeeEntryTimesheet.objects.filter(ts_approval_status="submitted")
        elif check_role("c2c_guest_employee") in approver_user_roles:
            guest_user = GuestUser.objects.filter(guest_user_id=approver_id).first()
            client_ids = guest_user.client_ids
            timesheets = EmployeeEntryTimesheet.objects.filter(
                client__in=client_ids, ts_approval_status="submitted")
        else:
            timesheets = EmployeeEntryTimesheet.objects.filter(
                approver__contains=[{"approver_id": approver_id}], ts_approval_status="submitted"
            )
        serializer = ApprovalPendingSerializer(timesheets, many=True)
        serialized_data = serializer.data
        transformed_data = self.transform_data(serialized_data, approver_id)
        return Response(transformed_data, status=status.HTTP_200_OK)
        
class ManagerApprovalPendingCountsView(APIView):

    def check_permissions(self, request):
        required_roles = ["c2c_timesheet_manager", "c2c_super_admin", "c2c_guest_employee", "c2c_hr_manager", "c2c_timesheet_admin"]
        return has_permission(request, required_roles)

    def get_unique_timesheet_count(self,timesheets):
        unique_weeks = set()
        for timesheet in timesheets:
            week_number = timesheet.week_number
            year = timesheet.year
            employee_id = timesheet.employee_id
            unique_weeks.add((employee_id, week_number, year))
        return list(unique_weeks)

    def get_planned_timesheets(self,approver_id=None):
        if approver_id:
            return EmployeeEntryTimesheet.objects.filter(approver__contains=[{"approver_id": approver_id}], ts_approval_status="submitted")
        return EmployeeEntryTimesheet.objects.filter(ts_approval_status="submitted")
    
    def get_unplanned_timesheets(self, approver_id=None):
        return EmployeeUnplannedNonbillableHours.objects.filter(Q(ts_approval_status="submitted") &(Q(unplanned_hours__gt=0) | Q(non_billable_hours__gt=0)))
    
    def get_unique_combined_timesheet_count(self, timesheets, unplanned_timesheets):
        unique_weeks = set()
        unique_weeks.update(
            (timesheet.employee_id, timesheet.week_number, timesheet.year) 
            for timesheet in timesheets
        )
        unique_weeks.update(
            (unplanned_timesheet.employee_id, unplanned_timesheet.week_number, unplanned_timesheet.year) 
            for unplanned_timesheet in unplanned_timesheets
        )
        return len(unique_weeks)

    def post(self, request):
        permission_result = self.check_permissions(request)
        if permission_result["status"] != 200:
            return Response(permission_result, status=status.HTTP_403_FORBIDDEN)
        approver_email = request.data.get("approver_email")
        if not approver_email:
            return Response(
                {"error": "approver_email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        timesheet_unique_weeks = []
        unplanned_timesheet_weeks = []
        actual_count = 0
        approver_id = get_approver_by_email(approver_email=approver_email)
        timesheets = self.get_planned_timesheets(approver_id)
        timesheet_unique_weeks = self.get_unique_timesheet_count(timesheets)
        unplanned_timesheets = self.get_unplanned_timesheets()
        unplanned_timesheet_weeks = self.get_unique_timesheet_count(unplanned_timesheets)
        if check_role('c2c_timesheet_admin') in permission_result['user_roles'] and check_role('c2c_timesheet_manager') in permission_result['user_roles']:
            timesheets_admin = self.get_planned_timesheets()
            timesheet_admin_unique_weeks = self.get_unique_timesheet_count(timesheets_admin)
            admin_week_list = timesheet_admin_unique_weeks + unplanned_timesheet_weeks
            actual_count = len(set(admin_week_list)) + len(timesheet_unique_weeks)
        elif check_role('c2c_timesheet_admin') in permission_result['user_roles'] and check_role('c2c_hr_manager') in permission_result['user_roles']:
            timesheets_admin = self.get_planned_timesheets()
            timesheet_admin_unique_weeks = self.get_unique_timesheet_count(timesheets_admin)
            actual_count = timesheet_admin_unique_weeks + unplanned_timesheet_weeks
            actual_count = len(set(actual_count))
        elif check_role('c2c_timesheet_admin') in permission_result['user_roles']:
            timesheets_admin = self.get_planned_timesheets()
            timesheet_admin_unique_weeks = self.get_unique_timesheet_count(timesheets_admin)
            actual_count = timesheet_admin_unique_weeks + unplanned_timesheet_weeks
            actual_count = len(set(actual_count))
        elif check_role('c2c_hr_manager') in permission_result['user_roles'] and check_role('c2c_timesheet_manager') in permission_result['user_roles']:
            actual_count = len(timesheet_unique_weeks) + len(unplanned_timesheet_weeks)
        elif check_role('c2c_hr_manager') in permission_result['user_roles']:
            actual_count = len(unplanned_timesheet_weeks)
        elif check_role('c2c_timesheet_manager') in permission_result['user_roles']:
            actual_count = len(timesheet_unique_weeks)
        elif check_role('c2c_guest_employee') in permission_result['user_roles']:
            actual_count = len(timesheet_unique_weeks)
        response_data = {
                    "timesheet_pending_approval_count": actual_count
                }
        return Response(response_data, status=200)
    
class UpdateTimesheetsByManagerView(APIView):

    def convert_to_float(self,hours_str):
        try:
            hours, minutes = map(int, hours_str.split(":"))
            return hours + minutes / 60.0
        except ValueError:
            raise ValueError(f"Invalid time format: {hours_str}")

    def check_permissions(self, request):
        required_roles = ["c2c_timesheet_manager", "c2c_super_admin", "c2c_guest_employee", "c2c_timesheet_admin"]
        return has_permission(request, required_roles)
    def post(self, request):
        permission_result = self.check_permissions(request)
        if permission_result["status"] != 200:
            return Response(permission_result, status=status.HTTP_403_FORBIDDEN)
        user_email = permission_result["user_email"]
        data = request.data
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return Response({"error": "Request data must be a list"}, status=status.HTTP_400_BAD_REQUEST)
        errors = []
        for item in data:
            timesheet_id = item.get("timesheet_id")
            employee_id = item.get("employee_id")
            billable_hours = item.get("billable_hours")
            non_billable_hours = item.get("non_billable_hours")
            approver_comments = item.get("approver_comments")
            ts_approval_status = item.get("ts_approval_status", "approved")
            try:
                timesheet = EmployeeEntryTimesheet.objects.get(
                    id=timesheet_id,
                    employee_id=employee_id
                )
                if ts_approval_status == "approved":
                    week_number = timesheet.week_number
                    year = timesheet.year
                    employee_id = timesheet.employee_id
                    try:
                        record = EmployeeUnplannedNonbillableHours.objects.get(
                            week_number=week_number, year=year, employee_id=employee_id
                        )
                        unplanned_hours = float(record.unplanned_hours or 0.0)
                        non_billable_hours = float(record.non_billable_hours or 0.0)
                        if math.isclose(unplanned_hours, 0.0, abs_tol=1e-9) and math.isclose(non_billable_hours, 0.0, abs_tol=1e-9):
                            record.ts_approval_status = "approved"
                            record.approved_by = user_email
                            record.save()
                    except EmployeeUnplannedNonbillableHours.DoesNotExist:
                        pass
            except EmployeeEntryTimesheet.DoesNotExist:
                errors.append({"data":item, "error": "Timesheet not found"})
                continue
            if billable_hours is not None:
                    if isinstance(billable_hours, str) and ":" in billable_hours:
                        billable_hours = self.convert_to_float(billable_hours)
                    timesheet.billable_hours = float(billable_hours)
            if non_billable_hours is not None:
                if isinstance(non_billable_hours, str) and ":" in non_billable_hours:
                    non_billable_hours = self.convert_to_float(non_billable_hours)
                timesheet.non_billable_hours = float(non_billable_hours)
            if approver_comments is not None:
                timesheet.approver_comments = approver_comments
            if ts_approval_status in ["approved", "recall"]:
                timesheet.ts_approval_status = ts_approval_status
            try:
                timesheet.approved_by = user_email
                timesheet.save()
            except Exception as e:
                errors.append({"data": item, "error": str(e)})
            

        response_data = {
            "updated_timesheets": [],
            "errors": errors
        }
        return Response(response_data, status=status.HTTP_200_OK if not errors else status.HTTP_400_BAD_REQUEST)
    
class PendingTimesheetsView(APIView):
    def check_permissions(self, request):
        required_roles = ["c2c_hr_manager", "c2c_super_admin"]
        return has_permission(request, required_roles)

    def post(self, request):
        permission_result = self.check_permissions(request)
        if permission_result["status"] != 200:
            return Response(permission_result, status=status.HTTP_403_FORBIDDEN)

        approver_email = request.data.get("approver_email")
        if not approver_email:
            return Response({"error": "approver_email is required"}, status=status.HTTP_400_BAD_REQUEST)

        approver_id = get_approver_by_email(approver_email)
        if not approver_id:
            return Response({"error": "Approver not found"}, status=status.HTTP_404_NOT_FOUND)
        timesheets = EmployeeUnplannedNonbillableHours.objects.filter(Q(ts_approval_status="submitted") &(Q(unplanned_hours__gt=0) | Q(non_billable_hours__gt=0)))
        serializer = EmployeeUnplannedNonbillableHoursSerializer(timesheets, many=True)
        grouped_data = defaultdict(lambda: {"employee_id": "", "employee_name": "", "pending_timesheets": []})

        for item in serializer.data:
            employee_id = item["employee_id"]
            if employee_id not in grouped_data:
                grouped_data[employee_id]["employee_id"] = employee_id
                grouped_data[employee_id]["employee_name"] = item["employee_name"]

            grouped_data[employee_id]["pending_timesheets"].append({
                "timesheet_id": item["timesheet_id"],
                "year": item["year"],
                "week": item["week"],
                "week_number": item["week_number"],
                "timeoff_hours": format_hours(item["timeoff_hours"]),
                "unplanned_hours": format_hours(item["unplanned_hours"]),
                "timeoff_hours_comments": item["timeoff_hours_comments"],
                "unplanned_hours_comments": item["unplanned_hours_comments"],
                "ts_approval_status": item["ts_approval_status"],
                "approver_comments": item["approver_comments"],
            })

        final_response = list(grouped_data.values())
        return Response(final_response, status=status.HTTP_200_OK)
    
class ApproveOrRecallTimesheetsView(APIView):
    def check_permissions(self, request):
        required_roles = ["c2c_hr_manager", "c2c_super_admin"]
        return has_permission(request, required_roles)
    def post(self, request):
        permission_result = self.check_permissions(request)
        if permission_result["status"] != 200:
            return Response(permission_result, status=status.HTTP_403_FORBIDDEN)
        approver_email = request.data.get("approver_email")
        timesheets_data = request.data.get("timesheets", [])

        if not approver_email:
            return Response({"error": "approver_email is required"}, status=status.HTTP_400_BAD_REQUEST)

        if not timesheets_data:
            return Response({"error": "timesheets list is required"}, status=status.HTTP_400_BAD_REQUEST)
        approver_id = get_approver_by_email(approver_email)
        if not approver_id:
            return Response({"error": "Approver not found"}, status=status.HTTP_404_NOT_FOUND)
        for ts_data in timesheets_data:
            timesheet_id = ts_data.get("timesheet_id")
            new_status = ts_data.get("ts_approval_status", "").lower()
            approver_comments = ts_data.get("approver_comments", "")

            if new_status not in ["approved", "recall"]:
                return Response({"error": f"Invalid ts_approval_status: {new_status}"}, status=status.HTTP_400_BAD_REQUEST)

            # Fetch the timesheet entry
            timesheet = EmployeeUnplannedNonbillableHours.objects.filter(Q(id=timesheet_id)).first()

            if not timesheet:
                return Response({"error": f"Timesheet {timesheet_id} not found or not in submitted state"}, status=status.HTTP_404_NOT_FOUND)

            # Update timesheet fields
            timesheet.ts_approval_status = new_status
            timesheet.approver_comments = approver_comments
            timesheet.approved_by = approver_email
            timesheet.save()
        return Response(
            {
                "message": "Timesheets processed successfully",
                "updated_timesheets": []
            },
            status=status.HTTP_200_OK
        )


class EmployeeMissingTimesheetAPIView(APIView):
    pagination_class = Pagination

    def post(self, request):
        employee_email = request.data.get("employee_email")
        if not employee_email:
            return Response({'error': 'Employee email is required'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            employee = Employee.objects.get(employee_email=employee_email)
        except Employee.DoesNotExist:
            return Response({'error': 'Employee not found'}, status=status.HTTP_404_NOT_FOUND)

        current_date = now().date()
        four_weeks_ago = current_date - timedelta(weeks=4)

        timesheets = Timesheet.objects.filter(resource=employee)
        missing_weeks = []
        existing_timesheet_entries = EmployeeEntryTimesheet.objects.filter(employee_id=employee).values_list(
            'timesheet_id', 'week_number', 'year'
        )
        existing_entries_set = set(existing_timesheet_entries)
        for timesheet in timesheets:
            estimation_data = timesheet.resource_estimation_data
            start_date = datetime.fromisoformat(estimation_data['start_date'].replace("Z", "")).date()
            end_date = datetime.fromisoformat(estimation_data['end_date'].replace("Z", "")).date()
            date_range = current_date
            if end_date > four_weeks_ago:
                date_range = current_date if end_date > current_date else end_date
            week_numbers = get_week_numbers_in_range(start_date, date_range)
            for week_number, year in week_numbers:
                if (timesheet.id, week_number, year) in existing_entries_set:
                    continue
                start_date_str, end_date_str = get_week_start_end_dates(year, week_number)
                start_date_str = datetime.fromisoformat(start_date_str).date() if isinstance(start_date_str, str) else start_date_str
                end_date_str = datetime.fromisoformat(end_date_str).date() if isinstance(end_date_str, str) else end_date_str
                allocated_hours = get_estimation_data_for_week(estimation_data, start_date_str, end_date_str)
                timesheet_data = {
                    "week_start_date": start_date_str,
                    "week_end_date": end_date_str,
                    "week_number": week_number,
                    "year": year,
                    "timeoff_hours": format_hours(0),
                    "total_hours": format_hours(0),
                    "unplanned_hours": format_hours(0),
                    "timeoff_hours_comments": "",
                    "unplanned_hours_comments": "",
                    "approver_comments": "",
                    "timesheet_status": "not_submitted",
                    "timesheets": [
                        {
                            "client_name": timesheet.client.name,
                            "contract_sow_name": timesheet.contract_sow.contractsow_name,
                            "allocated_hours": format_hours(allocated_hours),
                            "billable_hours": format_hours(0),
                            "non_billable_hours": format_hours(0),
                            "timesheet_status": "not_submitted",
                            "manager_comments": ""
                        }
                    ]
                }

                # Check if the same week already exists in missing_weeks
                existing_entry = next(
                    (entry for entry in missing_weeks 
                    if (entry["week_number"] == week_number and entry["year"] == year) or 
                    # (entry["week_start_date"] == start_date_str)),
                    (entry["week_start_date"] <= end_date_str and entry["week_end_date"] >= start_date_str)),
                    None
                )

                if existing_entry:
                    existing_entry["timesheets"].append(timesheet_data["timesheets"][0])  # Append to existing week's timesheets
                else:
                    missing_weeks.append(timesheet_data)

        recalled_timesheets = get_recalled_timesheets(employee)
        week_start_date_lookup = {}
        for recalled_entry in recalled_timesheets:
            recalled_week_start_date = datetime.strptime(recalled_entry['week_start_date'], '%Y-%m-%d').date()
            recalled_entry['week_start_date'] = recalled_week_start_date
            week_start_date_lookup[recalled_week_start_date] = recalled_entry
        for missing_week in missing_weeks:
            if missing_week['week_start_date'] not in week_start_date_lookup:
                week_start_date_lookup[missing_week['week_start_date']] = missing_week

        complete_data = list(week_start_date_lookup.values())
        complete_data = sorted(complete_data, key=lambda x: (-x["year"], -x["week_number"]))

        paginator = self.pagination_class()
        result_page = paginator.paginate_queryset(complete_data, request)
        response_data = paginator.get_paginated_response(result_page).data
        response_data["is_recalled_timesheets"] = bool(recalled_timesheets)
        response_data["total_recalled_count"] = len(recalled_timesheets)
        return Response(response_data, status=status.HTTP_200_OK)
        # return paginator.get_paginated_response(result_page)

def get_week_numbers_in_range(start_date, end_date):
    week_numbers = []
    if start_date.weekday() in [5, 6]:
        days_to_add = (7 - start_date.weekday()) % 7
        start_date += timedelta(days=days_to_add)
    while start_date <= end_date:
        year, week_number, _ = start_date.isocalendar()
        if (week_number, year) not in week_numbers:
            week_numbers.append((week_number, year))
        start_date += timedelta(days=1)
    return week_numbers

def get_week_start_end_dates(year, week_number):
    monday = date.fromisocalendar(year, week_number, 1)
    friday = monday + timedelta(days=4)
    return monday.strftime('%Y-%m-%d'), friday.strftime('%Y-%m-%d')


def get_recalled_timesheets(employee):
    recalled_timesheets = EmployeeEntryTimesheet.objects.filter(employee_id=employee, ts_approval_status="recall")
    recalled_unplanned_hours = EmployeeUnplannedNonbillableHours.objects.filter(employee_id=employee, ts_approval_status="recall")
    grouped_recalled_data = defaultdict(lambda: {"timesheets": [], "unplanned_hours": None})
    total_hours = 0
    unplanned_dummy = {
            "timeoff_hours": format_hours(0),
            "unplanned_hours": format_hours(0),
            "timeoff_hours_comments": "",
            "unplanned_hours_comments": "",
            "approver_comments": "",
            "timesheet_status": "recall",
        }
    for timesheet in recalled_timesheets:
        key = (timesheet.year, timesheet.week_number)
        estimation_data = timesheet.timesheet_id.resource_estimation_data
        start_date_str, end_date_str = get_week_start_end_dates(timesheet.year, timesheet.week_number)
        start_date_str = datetime.fromisoformat(start_date_str).date() if isinstance(start_date_str, str) else start_date_str
        end_date_str = datetime.fromisoformat(end_date_str).date() if isinstance(end_date_str, str) else end_date_str
        allocated_hours = get_estimation_data_for_week(
                    estimation_data, start_date_str, end_date_str
                )
        total_hours += timesheet.non_billable_hours + timesheet.billable_hours
        grouped_recalled_data[key]["timesheets"].append({
            "client_name": timesheet.client.name if timesheet.client else "N/A",
            "contract_sow_name": timesheet.contract_sow.contractsow_name if timesheet.contract_sow else "N/A",
            "allocated_hours": format_hours(allocated_hours),
            "billable_hours": format_hours(timesheet.billable_hours),
            "non_billable_hours": format_hours(timesheet.non_billable_hours),
            "total_hours": format_hours(timesheet.total_hours),
            "approver_comments": timesheet.approver_comments,
            "timesheet_status": timesheet.ts_approval_status
        })
    for unplanned in recalled_unplanned_hours:
        if unplanned.non_billable_hours:
            hours_non_billable = unplanned.non_billable_hours
        else:
            hours_non_billable = 0
        if unplanned.unplanned_hours:
            hours_unplanned = unplanned.unplanned_hours
        else:
            hours_unplanned = 0
        total_hours += hours_non_billable + hours_unplanned
        key = (unplanned.year, unplanned.week_number)
        grouped_recalled_data[key]["unplanned_hours"] = {
            "timeoff_hours": format_hours(unplanned.non_billable_hours),
            "unplanned_hours": format_hours(unplanned.unplanned_hours),
            "timeoff_hours_comments": unplanned.non_billable_hours_comments,
            "unplanned_hours_comments": unplanned.unplanned_hours_comments,
            "approver_comments": unplanned.approver_comments,
            "timesheet_status": unplanned.ts_approval_status
        }
    final_result = [
        {   
            "employee_id": employee.employee_source_id,
            "employee_name": employee.employee_full_name,
            "week_start_date": get_week_start_end_dates(year, week)[0],
            "week_end_date": get_week_start_end_dates(year, week)[1],
            "year": year,
            "week_number": week,
            "total_hours": format_hours(total_hours),
            "timesheets": data["timesheets"],
            **(data["unplanned_hours"] if data["unplanned_hours"] else unplanned_dummy)
        }
        for (year, week), data in sorted(grouped_recalled_data.items())
    ]
    return final_result

class SubmittedTimesheetsAPIView(APIView):
    # def get_billability_status(self, timesheet_record) -> bool:
    #     if (timesheet_record and 
    #         getattr(timesheet_record, 'resource_estimation_data', None) and 
    #         isinstance(timesheet_record.resource_estimation_data, dict) and 
    #         "billability" in timesheet_record.resource_estimation_data):
    #         return timesheet_record.resource_estimation_data["billability"] == "Billable"
    #     return False
    def transform_data(self, serialized_data, approver_id) -> list:
        grouped_data = defaultdict(lambda: {"pending_timesheets": []}) #"isBillable": False})

        for record in serialized_data:
            employee_id = record["employee_id"]
            employee_name = record["employee_name"]
            if employee_id == approver_id and PROFILE == "PROD":
                continue
            if "employee_name" not in grouped_data[employee_id]:
                grouped_data[employee_id]["employee_name"] = employee_name
                grouped_data[employee_id]["employee_id"] = employee_id
            
            week = record["pending_timesheets"]["week"]
            week_number = record["pending_timesheets"]["week_number"]
            contracts = record["pending_timesheets"].get("contracts", [])
            unplanned_hours = record["pending_timesheets"]["unplanned_hours"]
            timeoff_hours = record["pending_timesheets"]["timeoff_hours"]
            timeoff_hours_comments = record["pending_timesheets"]["timeoff_hours_comments"]
            unplanned_hours_comments = record["pending_timesheets"]["unplanned_hours_comments"]
            unplanned_timesheet_id = record["pending_timesheets"]["unplanned_timesheet_id"]
            unplanned_timesheet_status = record["pending_timesheets"]["unplanned_timesheet_status"]
            timesheet_id = record.get("timesheet_id")
            # if not timesheet_id:
            #     continue

            # timesheet_record = Timesheet.objects.filter(
            #     id=timesheet_id,
            # ).first()
            # grouped_data[employee_id]["isBillable"] = self.get_billability_status(timesheet_record)
            week_data = next(
                (week for week in grouped_data[employee_id]["pending_timesheets"] if week["week_number"] == week_number),
                None
            )
            
            if week_data:
                week_data["contracts"].extend(contracts)
            else:
                grouped_data[employee_id]["pending_timesheets"].append({
                    "week": week,
                    "week_number": week_number,
                    "contracts": contracts,
                    "unplanned_hours": unplanned_hours,
                    "timeoff_hours": timeoff_hours,
                    "unplanned_hours_comments": unplanned_hours_comments,
                    "timeoff_hours_comments": timeoff_hours_comments,
                    "unplanned_timesheet_id": unplanned_timesheet_id,
                    "unplanned_timesheet_status": unplanned_timesheet_status
                })
        
        return list(grouped_data.values())
    

    def check_permissions(self, request):
        required_roles = ["c2c_super_admin", "c2c_timesheet_admin"]
        return has_permission(request, required_roles)

    def group_unplanned_entries(self, unplanned_entries):
        grouped_data = defaultdict(lambda: {"pending_timesheets": []})
        for entry in unplanned_entries:
            employee_id = entry["employee_id"]
            pending_timesheet = entry["pending_timesheets"]
            grouped_data[employee_id]["employee_id"] = employee_id
            grouped_data[employee_id]["employee_name"] = entry["employee_name"]
            grouped_data[employee_id]["pending_timesheets"].append(pending_timesheet)
        return list(grouped_data.values())

    def post(self, request):
        permission_result = self.check_permissions(request)
        if permission_result["status"] != 200:
            return Response(permission_result, status=status.HTTP_403_FORBIDDEN)
        approver_email = request.data.get("approver_email")
        if not approver_email:
            return Response(
                {"error": "approver_email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        approver_id = get_approver_by_email(approver_email=approver_email)
        timesheets = EmployeeEntryTimesheet.objects.filter(ts_approval_status="submitted")
        serializer = AdminApprovalPendingSerializer(timesheets, many=True)
        serialized_data = serializer.data
        transformed_data = self.transform_data(serialized_data, approver_id)
        excluded_weeks = EmployeeEntryTimesheet.objects.filter(ts_approval_status="submitted").values_list(
            "employee_id", "week_number", "year", flat=False)
        unplanned_entries = EmployeeUnplannedNonbillableHours.objects.exclude(
                            employee_id__in=[x[0] for x in excluded_weeks],
                            week_number__in=[x[1] for x in excluded_weeks],
                            year__in=[x[2] for x in excluded_weeks]
                        ).exclude(
                            unplanned_hours=0,
                            non_billable_hours=0
                        ).filter(ts_approval_status="submitted")
        
        unplanned_serializer = UnplannedHoursSerializer(unplanned_entries, many=True)
        grouped_unplanned_entries = self.group_unplanned_entries(unplanned_serializer.data)
        for item in grouped_unplanned_entries:
            for tranformed_item in transformed_data:
                if item["employee_id"] == tranformed_item["employee_id"]:
                    tranformed_item["pending_timesheets"].extend(item["pending_timesheets"])
                    grouped_unplanned_entries.remove(item)
        response_data = transformed_data + grouped_unplanned_entries
        return Response(response_data, status=status.HTTP_200_OK)

class BulkApproveTimesheetsAPIView(APIView):
    def check_permissions(self, request):
        required_roles = ["c2c_timesheet_admin", "c2c_super_admin"]
        return has_permission(request, required_roles)

    def post(self, request):
        permission_result = self.check_permissions(request)
        if permission_result["status"] != 200:
            return Response(permission_result, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        user_email = permission_result["user_email"]
        if not isinstance(data, list):
            return Response({"error": "Invalid input format. Expected a list of employee timesheets."}, status=status.HTTP_400_BAD_REQUEST)
        
        errors = []

        for employee_entry in data:
            employee_id = employee_entry.get("employee_id")
            unplanned_timesheet_id = employee_entry.get("unplanned_timesheet_id")
            unplanned_status = employee_entry.get("ts_approval_status", "approved")
            unplanned_hours = employee_entry.get("unplanned_hours", "")
            timeoff_hours = employee_entry.get("timeoff_hours","")
            
            approver_comments = employee_entry.get("approver_comments", "")
            if unplanned_timesheet_id:
                try:
                    unplanned_entry = EmployeeUnplannedNonbillableHours.objects.get(id=unplanned_timesheet_id)
                    unplanned_entry.ts_approval_status = unplanned_status
                    unplanned_entry.unplanned_hours = (unplanned_hours if  unplanned_hours else unplanned_entry.unplanned_hours)
                    unplanned_entry.non_billable_hours = (timeoff_hours if timeoff_hours else unplanned_entry.non_billable_hours)
                    unplanned_entry.approver_comments = approver_comments
                    unplanned_entry.approved_by = user_email
                    unplanned_entry.save()
                except ObjectDoesNotExist:
                    errors.append(f"Unplanned timesheet with ID {unplanned_timesheet_id} not found.")

            # Process planned timesheets
            timesheets = employee_entry.get("timesheets", [])
            for ts in timesheets:
                entry_timesheet_id = ts.get("timesheet_id")
                timesheet_status = ts.get("ts_approval_status", "approved")

                if not entry_timesheet_id:
                    errors.append(f"Missing timesheet_id for employee {employee_id}.")
                    continue

                try:
                    timesheet_entry = EmployeeEntryTimesheet.objects.get(id=entry_timesheet_id)
                    timesheet_entry.ts_approval_status = timesheet_status
                    timesheet_entry.approver_comments = employee_entry.get("approver_comments", "")
                    timesheet_entry.approved_by = user_email
                    timesheet_entry.save()
                except ObjectDoesNotExist:
                    errors.append(f"Timesheet entry with ID {entry_timesheet_id} not found.")

        if errors:
            return Response({"errors": errors}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "Timesheets approved successfully."}, status=status.HTTP_200_OK)