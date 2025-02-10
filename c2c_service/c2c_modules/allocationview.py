from drf_yasg.utils import swagger_auto_schema
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin, CreateModelMixin
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import generics, status
from rest_framework.pagination import PageNumberPagination
from c2c_modules.serializer import AllocationSerializer, EstimationResourceSerializer, SowContractSerializer
from c2c_modules.models import Allocation, Client,SowContract, Estimation, Employee, Timesheet, EmployeeUnplannedNonbillableHours
from c2c_modules.utils import has_permission, get_date_from_utc_time
from django.db.models import F
from datetime import datetime, timedelta
from rest_framework.generics import ListAPIView
from c2c_modules.custom_logger import info, error, warning
from django.shortcuts import get_object_or_404
from datetime import datetime, timedelta, timezone
from collections import defaultdict
from config import PROFILE
#   ================================================================
class Pagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000


def get_week_date_range(year, week_number):
    """Returns the formatted week date range and start & end date."""
    week_start_date = datetime.fromisocalendar(year, week_number, 1)  # Monday
    week_end_date = week_start_date + timedelta(days=6)  # Sunday
    formatted_start_date = week_start_date.strftime('%d/%m/%Y')
    formatted_end_date = week_end_date.strftime('%d/%m/%Y')
    return f"{formatted_start_date} - {formatted_end_date}", week_start_date.date(), week_end_date.date()

def check_and_validate_timesheet_submission(current_estimation_data, employee_id):
    unique_weeks = set()
    for entry in current_estimation_data.get('Estimation_Data', {}).get('daily', []):
        date_str = entry.get('date')
        if date_str:
            date_obj = datetime.strptime(date_str, "%d/%m/%Y")
            week_number = date_obj.isocalendar()[1]
            year = date_obj.year
            unique_weeks.add((week_number, year))
    weeks_list = [{'week_number': week, 'year': year} for week, year in unique_weeks]
    existing_timesheets = EmployeeUnplannedNonbillableHours.objects.filter(
        employee_id=employee_id,
        year__in=[w['year'] for w in weeks_list],
        week_number__in=[w['week_number'] for w in weeks_list],
        ts_approval_status="submitted"
    ).values_list('week_number', 'year')
    existing_timesheets_set = set(existing_timesheets)
    if len(existing_timesheets_set) > 0:
        conflicting_weeks = [
            f"Week {week_number} of {year} ({get_week_date_range(year, week_number)[0]})"
            for week_number, year in existing_timesheets_set
        ]
    else:
        conflicting_weeks = []
    return conflicting_weeks

def get_current_estimation_data(estimation_list):
    new_estimation__indexes = []
    for resource in estimation_list:
        for resource_count in range(0,resource['num_of_resources']):
            new_estimation__indexes.append(resource)
    return new_estimation__indexes

class AllocationAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    queryset = Allocation.objects.all().order_by('-uuid')
    pagination_class = Pagination
    lookup_field = 'uuid'

    def get_serializer_class(self):
        return AllocationSerializer

    @swagger_auto_schema(tags=["Allocation"])
    def get(self, request, *args, **kwargs):
        """ list of Allocations """
        required_roles = ["c2c_allocation_admin","c2c_allocation_viewer","c2c_viewer","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            info(f"User {request.user} has permission to list Allocations.")
            response = self.list(request, *args, **kwargs)
            response.data.update({"result":result})
            return response
        else:
            warning(f"User {request.user} does not have permission to list Allocations.")
            return Response({"result":result}, status=status.HTTP_403_FORBIDDEN)

    def post(self, request, *args, **kwargs):
        """Create Allocation"""
        required_roles = ["c2c_allocation_admin", "c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] != 200:
            return Response({"error": "Permission denied"}, status=status.HTTP_403_FORBIDDEN)
        
        username = result['username']
        request.data['username_created'] = username
        request.data['username_updated'] = username
        info(f"User {request.user} has permission to create an Allocation.")
        approver = request.data.get('approver',[])
        resource_data = request.data.get('resource_data', [])
        if PROFILE == 'PROD' and len(approver) == 1:
            single_approver = approver[0]
            for resource in resource_data:
                if resource.get('resource_id') == single_approver:
                    return Response({
                        "error": "Conflict detected",
                        "details": f"The approver '{single_approver}' is also present in resource_data. "
                                "Please add additional approvers to avoid self-approval."
                    }, status=status.HTTP_400_BAD_REQUEST)
        invalid_resources = []
        for resource in request.data['resource_data']:
            cost_hours = resource.get('cost_hours', 0)
            billable_hours = resource.get('billable_hours', 0)
            if billable_hours < cost_hours:
                invalid_resources.append({
                    "resource_id": resource.get('resource_id'),
                    "resource_name": resource.get('resource_name'),
                    "role": resource.get('role'),
                    "cost_hours": cost_hours,
                    "billable_hours": billable_hours,
                    "error": "billable hours are not sufficient for the given cost hours"
                })
            else:
                resource['billable_hours'] = cost_hours

        if invalid_resources:
            warning(f"Validation failed for resources: {invalid_resources}")
            return Response(
                {
                    "error": "Validation failed",
                    "details": invalid_resources
                },
                status=status.HTTP_409_CONFLICT
            )
        estimation = get_object_or_404(Estimation, uuid=request.data['estimation'])
        estimation_data = estimation.resource
        estimation_list = estimation_data if isinstance(estimation_data, list) else [estimation_data]
        new_estimation_data = get_current_estimation_data(estimation_list)
        if not new_estimation_data:
            warning("No Estimation data found for the given estimation.")
            return Response(
                {
                    "error": "No Estimation data found for the given estimation."
                },
                status=status.HTTP_409_CONFLICT
            )
        for resource in request.data['resource_data']:
            start_date = resource.get('start_date')
            end_date = resource.get('end_date')
            resource_name = resource.get('resource_name')
            resource_index = request.data['resource_data'].index(resource)
            current_estimation_data = new_estimation_data[resource_index]
            resource_timesheets = Timesheet.objects.filter(
                resource__employee_source_id=resource['resource_id'],
                contract_sow__start_date__lte=end_date,
                contract_sow__end_date__gte=start_date
            )
            resource_estimation_data = [
                timesheet.resource_estimation_data for timesheet in resource_timesheets
            ]
            daily_hours_map = {}
            conflicting_weeks = check_and_validate_timesheet_submission(current_estimation_data, resource['resource_id'])
            if conflicting_weeks:
                    return Response({"error": f"Cannot create allocation because the employee {resource_name}has already submitted timesheets",
                                      "details": f"{', '.join(conflicting_weeks)}."},
                                      status=status.HTTP_400_BAD_REQUEST
                    )
            for res_data in resource_estimation_data:
                for entry in res_data.get('Estimation_Data',{}).get('daily', []):
                    date = entry.get('date')
                    hours = entry.get('hours', 0)
                    daily_hours_map[date] = daily_hours_map.get(date, 0) + hours

            for entry in current_estimation_data.get('Estimation_Data',{}).get('daily', []):
                date = entry.get('date')
                hours = entry.get('hours', 0)
                daily_hours_map[date] = daily_hours_map.get(date, 0) + hours
                if daily_hours_map[date] > 8:
                    warning(f"Resource {resource['resource_id']} exceeds daily limit on {date}")
                    return Response(
                        {
                            "error": f"Resource {resource['resource_name']} exceeds daily limit on {date}",
                            "details": [{
                                "resource_id": resource['resource_id'],
                                "date": date,
                                "total_hours": daily_hours_map[date],
                                "limit": 8
                            }]
                        },
                        status=status.HTTP_409_CONFLICT
                    )
        response = self.create_allocation(request)
        if response.status_code != 201:
            warning(f"Failed to create Allocation: {response.data}")
            return response
        allocation_data = response.data
        allocation = Allocation.objects.get(uuid=allocation_data['uuid'])
        client = get_object_or_404(Client, uuid=allocation_data['client'])
        estimation = get_object_or_404(Estimation, uuid=allocation_data['estimation'])
        contract_sow = get_object_or_404(SowContract, uuid=allocation_data['contract_sow'])
        approver = request.data.get('approver',[])      
        for resource in request.data['resource_data']:
            resource_role = resource.get('role')
            resource_id = resource.get('resource_id')
            
            if resource_id == 'BUDGETO123':
                info(f"Skipping timesheet creation for resource: {resource_id} as per the requirement.")
                continue
            resource_index = request.data['resource_data'].index(resource)
            current_estimation_data = new_estimation_data[resource_index]
            if not current_estimation_data:
                warning(f"No matching estimation data found for role: {resource_role}")
                continue
            employee = get_object_or_404(Employee, employee_source_id=resource['resource_id'])
            Timesheet.objects.create(
                client=client,
                estimation=estimation,
                allocation=allocation,
                resource=employee,
                resource_role=resource_role,
                billable_hours=resource.get('cost_hours'),
                cost_hours=resource.get('cost_hours'),
                resource_estimation_data=current_estimation_data,
                approver = approver,
                contract_sow=contract_sow,
                username_created=username,
                username_updated=username
            )
            info(f"timesheet created successfully for resource: {resource['resource_id']} - {resource['resource_name']} - {resource_role}")
        info(f"Allocation {allocation.uuid} created successfully with Timesheets.")
        response.data.update({"result": result})
        return response

    def create_allocation(self, request):
        """Helper method to handle allocation creation."""
        allocation_serializer = AllocationSerializer(data=request.data)
        if allocation_serializer.is_valid():
            allocation_serializer.save()
            return Response(allocation_serializer.data, status=status.HTTP_201_CREATED)
        return Response(allocation_serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
class AllocationClientGetAPIView(ListModelMixin, GenericAPIView):
    serializer_class = AllocationSerializer
    pagination_class = Pagination
    def get_queryset(self):
        return Allocation.objects.filter(client=self.kwargs['client_uuid']) \
                                 .annotate(contractsow_name=F('contract_sow__contractsow_name'),
                                           estimation_name=F('estimation__name')) \
                                 .order_by('-uuid')

    @swagger_auto_schema(tags=["Allocation"])
    def get(self, request, client_uuid, *args, **kwargs):
        required_roles = ["c2c_allocation_admin","c2c_allocation_viewer","c2c_viewer","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"roles_response": result})
            return response
        else:
            return Response({"roles_response": result})


class AllocationDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Allocation.objects.all()
    serializer_class = AllocationSerializer
    lookup_field = 'uuid'

    @swagger_auto_schema(tags=["Allocation"], operation_description="Get an allocation by UUID")
    def get(self, request, *args, **kwargs):
        required_roles = ["c2c_allocation_admin","c2c_allocation_viewer","c2c_viewer","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            response = self.retrieve(request, *args, **kwargs)
            response.data.update({"result":result})
            return response
        else:
            return Response({"result":result})
        
    def old_and_new_entries(self, allocation_list, update_allocation_list):
        old_data_list = []
        new_data_list = []
        old_data = []
        for entry in allocation_list:
            old_data_list.append(entry)
        for entry in update_allocation_list:
            new_data_list.append(entry)
        non_matches = []
        for old_entry, new_entry in zip(old_data_list, new_data_list):
            if (
                old_entry['resource_id'] != new_entry['resource_id'] or
                old_entry.get('change_effective_from') != new_entry.get('change_effective_from')
            ):
                non_matches.append(new_entry)
                old_data.append(old_entry)
        return non_matches, old_data


    def put(self, request, *args, **kwargs):
        required_roles = ["c2c_allocation_admin","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] != 200:
            return Response({"result": result}, status=status.HTTP_403_FORBIDDEN)
        username = result['username']
        allocation = self.get_object()
        resource_data = request.data.get('resource_data', [])
        client = allocation.client
        contract_sow = allocation.contract_sow
        estimation = allocation.estimation
        estimation_data = estimation.resource
        estimation_list = estimation_data if isinstance(estimation_data, list) else [estimation_data]
        new_estimation_data = get_current_estimation_data(estimation_list)
        if not new_estimation_data:
            warning("No Estimation data found for the given estimation.")
            return Response(
                {
                    "error": "No Estimation data found for the given estimation."
                },
                status=status.HTTP_409_CONFLICT
            )
        allocation_list = allocation.resource_data
        non_matched_entries, old_data = self.old_and_new_entries(allocation_list,resource_data)
        current_approver = allocation.approver
        new_approver = request.data.get('approver')
        approver_changed = current_approver != new_approver
        if not non_matched_entries and not approver_changed:
            return Response({"message": "No change in allocations or approver"}, status=status.HTTP_200_OK)
        else:
            invalid_resources = []
            for resource in non_matched_entries:
                cost_hours = resource.get('cost_hours', 0)
                billable_hours = resource.get('billable_hours', 0)
                if billable_hours < cost_hours:
                    invalid_resources.append({
                        "resource_id": resource.get('resource_id'),
                        "resource_name": resource.get('resource_name'),
                        "role": resource.get('role'),
                        "cost_hours": cost_hours,
                        "billable_hours": billable_hours,
                        "error": "billable hours are not sufficient for the given cost hours"
                    })
                else:
                    resource['billable_hours'] = cost_hours

            if invalid_resources:
                warning(f"Validation failed for resources: {invalid_resources}")
                return Response(
                    {
                        "error": "Validation failed",
                        "details": invalid_resources
                    },
                    status=status.HTTP_400_BAD_REQUEST
                )
            for resource in non_matched_entries:
                resource_role = resource.get('role')
                start_date = resource.get('start_date')
                end_date = resource.get('end_date')
                old_resource_data_ = old_data[non_matched_entries.index(resource)]
                employee_id = old_resource_data_.get('resource_id')
                employee_record = Employee.objects.get(employee_source_id=employee_id)
                employee_timesheet_record = Timesheet.objects.filter(allocation = allocation, resource=employee_record).first()
                if employee_timesheet_record:
                    current_estimation_data = employee_timesheet_record.resource_estimation_data
                else:
                    current_estimation_data = new_estimation_data[allocation_list.index(old_data[non_matched_entries.index(resource)])]
                conflicting_weeks = check_and_validate_timesheet_submission(current_estimation_data, resource['resource_id'])
                if conflicting_weeks:
                        return Response({"error": f"Cannot create allocation because the employee {resource_name}has already submitted timesheets",
                                        "details": f"{', '.join(conflicting_weeks)}."},
                                        status=status.HTTP_400_BAD_REQUEST
                        )
                resource_timesheets = Timesheet.objects.filter(
                    resource__employee_source_id=resource['resource_id'],
                    contract_sow__start_date__lte=end_date,
                    contract_sow__end_date__gte=start_date
                )
                resource_estimation_data = [
                    timesheet.resource_estimation_data for timesheet in resource_timesheets
                ]
                daily_hours_map = {}
                for res_data in resource_estimation_data:
                    for entry in res_data.get('Estimation_Data',{}).get('daily', []):
                        date = entry.get('date')
                        hours = entry.get('hours', 0)
                        daily_hours_map[date] = daily_hours_map.get(date, 0) + hours

                for entry in current_estimation_data.get('Estimation_Data',{}).get('daily', []):
                    date = entry.get('date')
                    hours = entry.get('hours', 0)
                    daily_hours_map[date] = daily_hours_map.get(date, 0) + hours
                    if daily_hours_map[date] > 8:
                        warning(f"Resource {resource['resource_id']} exceeds daily limit on {date}")
                        return Response(
                            {
                                "error": f"Resource {resource['resource_name']} exceeds daily limit on {date}",
                                "details": {
                                    "resource_id": resource['resource_id'],
                                    "date": date,
                                    "total_hours": daily_hours_map[date],
                                    "limit": 8
                                }
                            },
                            status=status.HTTP_400_BAD_REQUEST
                        )
            if approver_changed:
                allocation.approver = new_approver
                info(f"Approver updated for allocation ID {current_approver} to {new_approver}")
                allocation.save(update_fields=['approver'])
                timesheets = Timesheet.objects.filter(allocation=allocation)
                for timesheet in timesheets:
                    timesheet.approver = new_approver
                    timesheet.save(update_fields=['approver'])
                    info(f"Updated approver for timesheet ID {timesheet.id}")
            for resource in resource_data:
                change_effective_from = resource.get('change_effective_from')
                if change_effective_from:
                    resource['start_date'] = change_effective_from
            serializer = self.get_serializer(allocation, data=request.data, partial=True)
            serializer.is_valid(raise_exception=True)
            serializer.save(username_updated=username)
            for resource in non_matched_entries:
                resource_id = resource.get('resource_id')
                role = resource.get('role')
                change_effective_from = resource.get('change_effective_from',"")
                billable_hours = resource.get('billable_hours')
                cost_hours = resource.get('cost_hours')
                old_resource_data = old_data[non_matched_entries.index(resource)]
                employee_record = Employee.objects.get(employee_source_id=resource_id)
                employee_timesheet_record = Timesheet.objects.filter(allocation = allocation, resource=employee_record).first()
                if employee_timesheet_record:
                    current_estimation_data = employee_timesheet_record.resource_estimation_data
                else:
                    current_estimation_data = new_estimation_data[allocation_list.index(old_data[non_matched_entries.index(resource)])]
                if resource_id == 'BUDGETO123' and change_effective_from and old_resource_data['resource_id'] == 'BUDGETO123':
                    info(f"Skipping timesheet creation for resource: {resource_id} as per the requirement.")
                elif resource_id == 'BUDGETO123' and change_effective_from and old_resource_data['resource_id'] != 'BUDGETO123':
                    timesheet = Timesheet.objects.get(resource__employee_source_id=old_resource_data['resource_id'],allocation = allocation)
                    self.update_resource_estimation_data(timesheet, change_effective_from)
                elif resource_id != 'BUDGETO123' and change_effective_from and old_resource_data['resource_id'] == 'BUDGETO123':
                    timesheet = self.create_or_update_timesheet(allocation, resource_id, role, billable_hours, cost_hours, client, contract_sow, estimation, current_estimation_data, username)
                    self.initialize_estimation_data(timesheet, change_effective_from)
                elif resource_id != 'BUDGETO123' and change_effective_from and old_resource_data['resource_id'] != 'BUDGETO123':
                    old_timesheet = Timesheet.objects.get(resource__employee_source_id=old_resource_data['resource_id'],allocation = allocation)
                    self.update_resource_estimation_data(old_timesheet, change_effective_from)
                    timesheet = self.create_or_update_timesheet(allocation, resource_id, role, billable_hours, cost_hours, client, contract_sow, estimation, current_estimation_data, username)
                    self.initialize_estimation_data(timesheet, change_effective_from)
            response_data = serializer.data
            response_data.update({
                "result": result
            })
            return Response(response_data, status=status.HTTP_200_OK)
            
    def update_resource_estimation_data(self, resource, current_date):
        """
        Updates the resource's estimation data by filtering out dates beyond the current date
        and updates the end_date field to the current date.
        """
        striped_current_date = get_date_from_utc_time(str(current_date))
        resource_estimation_data = resource.resource_estimation_data or {}
        estimation_data = resource_estimation_data.get("Estimation_Data", {}).get("daily", [])
        filtered_estimation_data = []
        for entry in estimation_data:
            try:
                entry_date = datetime.strptime(entry["date"], "%d/%m/%Y").date()
                if entry_date <= striped_current_date:
                    filtered_estimation_data.append(entry)
            except ValueError:
                print(f"Skipping invalid date format in entry: {entry}")
        if "Estimation_Data" not in resource_estimation_data:
            resource_estimation_data["Estimation_Data"] = {}
        resource_estimation_data["Estimation_Data"]["daily"] = filtered_estimation_data
        resource_estimation_data["end_date"] = current_date
        resource.resource_estimation_data = resource_estimation_data
        resource.save()

    def initialize_estimation_data(self, resource, current_date):
        """
        Updates the estimation data for a resource.
        - Sets the `start_date` to the current date.
        - Removes all entries from `Estimation_Data.daily` with dates earlier than the current date.
        """
        striped_current_date = get_date_from_utc_time(str(current_date))
        resource_estimation_data = resource.resource_estimation_data or {}
        estimation_data = resource_estimation_data.get("Estimation_Data", {"daily": []})
        daily_entries = estimation_data.get("daily", [])
        filtered_entries = [
            entry for entry in daily_entries
            if datetime.strptime(entry["date"], "%d/%m/%Y").date() >= striped_current_date
        ]
        estimation_data["daily"] = filtered_entries
        resource_estimation_data["start_date"] = current_date
        resource_estimation_data["Estimation_Data"] = estimation_data
        resource.resource_estimation_data = resource_estimation_data
        resource.save()

    def create_or_update_timesheet(self, allocation, resource_id, role, billable_hours, cost_hours, client, contract_sow, estimation, current_estimation_data, username):
        try:
            employee = get_object_or_404(Employee, employee_source_id=resource_id)
            timesheet, created = Timesheet.objects.update_or_create(
                allocation=allocation,
                resource=employee,
                defaults={
                    'resource_role': role,
                    'billable_hours': billable_hours,
                    'cost_hours': cost_hours,
                    'client': client,
                    'contract_sow': contract_sow,
                    'estimation': estimation,
                    'approver': allocation.approver,
                    'resource_estimation_data': current_estimation_data,
                    'username_created': username,
                    'username_updated': username
                }
            )
            action = "created" if created else "updated"
            info(f"Timesheet {action} successfully for resource_id: {resource_id} with allocation: {allocation.uuid}")
            return timesheet
        except Exception as e:
            error(f"Failed to create or update timesheet for resource_id: {resource_id}. Error: {str(e)}")

    def delete(self, request, *args, **kwargs):
        required_roles = ["c2c_allocation_admin","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            allocation = self.get_object()
            allocation.delete()
            return Response({"message": "Allocation and respective timesheets deleted successfully", "result": result})
        else:
            return Response({"result": result})


class EstimationDetailByContractView(APIView):
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

    def parse_date(self, date_str):
        for fmt in ('%d/%m/%Y', '%m/%d/%Y'):
            try:
                return datetime.strptime(date_str, fmt).date()
            except ValueError:
                continue
        info(f"Error parsing date: {date_str}. Skipping this entry.")
        return None

    def calculate_free_hours_for_day(self, worked_hours):
        return max(8 - worked_hours, 0)

    def get_estimation_data(self, resource_estimation_data):
        return resource_estimation_data.get('Estimation_Data', {}).get('daily', [])
    
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

    def build_employee_response(self, employee, available_hours, status, pre_planned_hours):
        return {
            "resource_id": employee.employee_source_id,
            "resource_name": employee.employee_full_name,
            "available_hours": available_hours,
            "pre_planned_hours": pre_planned_hours,
            "availability_status": status
        }

    def get_employee_data(self, role, start_date, end_date):
        filtered_employees = Employee.objects.filter(
            employee_assigned_role=role,
            employee_status__in=['Active']
        )
        employee_data = []
        for employee in filtered_employees:
            timesheets = Timesheet.objects.filter(
                resource=employee,
                contract_sow__start_date__lte=end_date,
                contract_sow__end_date__gte=start_date
            )
            available_hours, status, pre_planned_hours = self.get_employee_availability(timesheets, start_date, end_date)
            employee_data.append(self.build_employee_response(employee, available_hours, status, pre_planned_hours))
        return employee_data

    def get_employee_availability(self, timesheets, start_date, end_date):
        available_hours = self.calculate_weekday_hours(start_date, end_date)
        if not timesheets.exists():
            pre_planned_hours = 0
            status = "Available" if available_hours else "Not Available"
        else:
            free_hours = self.check_timesheet_availability(timesheets, start_date, end_date, available_hours)
            status = "Available" if free_hours else "Not Available"
            pre_planned_hours = available_hours - free_hours
            available_hours = free_hours
        return available_hours, status, pre_planned_hours

    @swagger_auto_schema(tags=["Allocation"])
    def get(self, request, contractsow_id, estimation_id, *args, **kwargs):
        required_roles = ["c2c_allocation_admin", "c2c_allocation_viewer", "c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] != 200:
            return Response({"result": result})

        try:
            contract = SowContract.objects.get(uuid=contractsow_id, estimation__uuid=estimation_id)
            estimation = contract.estimation

            for resource in estimation.resource:
                start_date = datetime.strptime(resource['start_date'], self.DATE_FORMAT)
                end_date = datetime.strptime(resource['end_date'], self.DATE_FORMAT)
                role = resource['role']
                num_of_resources = resource['num_of_resources']
                employee_data = self.get_employee_data(role, start_date, end_date)
                resource["resource_data"] = employee_data
                resource["start_date"] = resource['start_date']
                resource["end_date"] = resource['end_date']
                resource["num_of_resources"] = num_of_resources

            serializer = EstimationResourceSerializer(estimation)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except SowContract.DoesNotExist:
            return Response({'error': 'Contract or Estimation not found.'}, status=status.HTTP_404_NOT_FOUND)

class SowContractListView(ListAPIView):
    serializer_class = SowContractSerializer
    @swagger_auto_schema(tags=["Allocation"])
    def get(self, request, client_uuid, *args, **kwargs):
        """List of Contracts with Estimation names for a specific client"""
        self.queryset = SowContract.objects.filter(client__uuid=client_uuid)
        return self.list(request, *args, **kwargs)

class CheckAllocationView(APIView):
    @swagger_auto_schema(tags=["Allocation"])
    def post(self, request, contract_sow_id, *args, **kwargs):
        try:
            contract_sow = SowContract.objects.get(uuid=contract_sow_id)
            allocation_exists = Allocation.objects.filter(contract_sow=contract_sow).exists()
            if allocation_exists:
                allocation = Allocation.objects.filter(contract_sow=contract_sow)
                allocation_data = AllocationSerializer(allocation, many=True).data
                info(f"Allocation Exists with the given contract_sow id {contract_sow_id}")
                return Response({'exist': True, 'allocations': allocation_data}, status=status.HTTP_200_OK)
            else:
                return Response({'exist': False}, status=status.HTTP_200_OK)
        except SowContract.DoesNotExist:
            error("contract_sow_id not found, please provide the valid contract_sow_id")
            return Response({'error': 'Contract SOW not found.'}, status=status.HTTP_404_NOT_FOUND)
