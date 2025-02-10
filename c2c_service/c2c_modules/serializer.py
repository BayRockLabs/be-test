from rest_framework import serializers
from decimal import Decimal
from c2c_modules.models import Client, Contract, FileModel, Estimation, Pricing, PurchaseOrder, UtilizedAmount, SowContract, MainMilestone, SkillPayRate, Allocation, Invoices, EmployeeEntryTimesheet, Timesheet, Employee, GuestUser, EmployeeUnplannedNonbillableHours, C2CRateCardConfig
import re
from c2c_modules.custom_logger import info
from collections import defaultdict
from django.db.models import Q
from datetime import datetime, timedelta, date
from django.db.models import Sum
from django.core.exceptions import ObjectDoesNotExist
import uuid
import calendar


EST_NAME = 'estimation.name'
CLIENT_NAME = 'client.name'
SOW_NAME = 'contract_sow.contractsow_name'

class ClientSerializer(serializers.ModelSerializer):
    client_contracts = serializers.SerializerMethodField()
    class Meta:
        model = Client
        fields = '__all__'

    def get_client_contracts(self, obj):
        contracts = obj.client_contracts.all()
        serialized_contracts = []
        for contract in contracts:
            files = FileModel.objects.filter(document_id=contract.uuid,status='active').values('uuid', 'blob_name')
            serialized_contract = {
                'uuid': contract.uuid,
                'name': contract.name,
                'start_date': contract.start_date,
                'end_date': contract.end_date,
                'end_type': contract.end_type,
                'status': contract.status,
                'contract_creation_date' : contract.contract_creation_date,
                'contract_created_by' : contract.contract_created_by,
                'contract_version' : contract.contract_version,
                'files' : list(files),
            }
            serialized_contracts.append(serialized_contract)
        return serialized_contracts

class ContractSerializer(serializers.ModelSerializer):
    client = serializers.SerializerMethodField()
    files = serializers.SerializerMethodField()
    class Meta:
        model = Contract
        fields = ['uuid', 'name', 'start_date', 'end_date', 'end_type', 'client', 'files', 'status', 'payment_terms', 'contract_name', 'contract_end_type', 'contract_version', 'contract_created_by', 'contract_creation_date','username_created','username_updated']

    payment_terms = serializers.CharField(read_only=True)
    contract_name = serializers.CharField(read_only=True)

    def get_client(self, obj):
        client = obj.client
        serialized_client = {
            'uuid': client.uuid,
            'name': client.name,
            'address': client.address,
        }
        return serialized_client

    def get_files(self, obj):
        files = FileModel.objects.filter(document_id=obj.uuid,status='active').values('uuid', 'blob_name')
        return list(files)

class ContractCreateSerializer(serializers.ModelSerializer):
    files = serializers.SerializerMethodField()
    class Meta:
        model = Contract
        fields = ['uuid', 'name', 'start_date', 'end_date', 'end_type', 'client', 'status', 'payment_terms', 'contract_name', 'contract_end_type', 'contract_version', 'contract_created_by', 'contract_creation_date','username_created','username_updated','files']

    def get_files(self, obj):
        files = FileModel.objects.filter(document_id=obj.uuid,status='active').values('uuid', 'blob_name')
        return list(files)

class ContractUpdateSerializer(serializers.ModelSerializer):
    files = serializers.SerializerMethodField()

    class Meta:
        model = Contract
        fields = ['uuid','name', 'start_date', 'end_date', 'end_type', 'client', 'status', 'files', 'payment_terms', 'contract_name', 'contract_end_type', 'contract_version', 'contract_created_by', 'contract_creation_date','username_updated']

    def get_files(self, obj):
        files = FileModel.objects.filter(document_id=obj.uuid,status='active').values('uuid', 'blob_name')
        return list(files)


class ContractSowSerializer(serializers.ModelSerializer):
    client_uuid = serializers.ReadOnlyField(source='client.uuid')
    pricing_uuid = serializers.ReadOnlyField(source='pricing.uuid')
    pricing_name = serializers.CharField(source='pricing.name')
    estimation_name = serializers.CharField(source=EST_NAME)
    estimation_uuid = serializers.ReadOnlyField(source='estimation.uuid')
    doc_contract_amount = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_contract_amount = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False)
    is_contract_utilized_po = serializers.SerializerMethodField()
    document = serializers.SerializerMethodField()
    parent_contract_name = serializers.CharField(read_only=True)
    class Meta:
        model = SowContract
        fields = ['uuid', 'contractsow_name','doc_contract_amount', 'total_contract_amount', 'start_date', 'end_date', 'document', 'payment_term_client', 'payment_term_contract', 'contractsow_type', 'client_uuid', 'pricing_uuid', 'pricing_name', 'estimation_name', 'estimation_uuid','doc_start_date','doc_end_date','is_contract_utilized_po','username_created','username_updated','extension_sow_contract','parent_contract_name']

    def get_is_contract_utilized_po(self, obj):
        return UtilizedAmount.objects.filter(sow_contract=obj).exists()

    def get_document(self, obj):
        files = FileModel.objects.filter(document_id=obj.uuid,status='active').values('uuid', 'blob_name')
        return list(files)
    
    def get_parent_contract_name(self, obj):
        if obj.extension_sow_contract:
            try:
                # Validate if extension_sow_contract is a valid UUID
                uuid_obj = uuid.UUID(obj.extension_sow_contract, version=4)
                # If valid, fetch the parent contract
                parent_contract = SowContract.objects.filter(uuid=uuid_obj).first()
                return parent_contract.contractsow_name if parent_contract else None
            except ValueError:
                # Return None if extension_sow_contract is not a valid UUID
                return None
        return None

class ContractSowCreateSerializer(serializers.ModelSerializer):
    total_contract_amount = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False, default=Decimal('0.00'))  # Set the appropriate default value
    doc_contract_amount = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False, default=Decimal('0.00'))
    is_contract_utilized_po = serializers.SerializerMethodField()
    document = serializers.SerializerMethodField()
    parent_contract_name = serializers.CharField(read_only=True)
    class Meta:
        model = SowContract
        fields = ['uuid', 'contractsow_name', 'total_contract_amount','doc_contract_amount', 'start_date', 'end_date',  'document', 'payment_term_client', 'payment_term_contract', 'contractsow_type', 'client', 'pricing', 'estimation','doc_start_date','doc_end_date','is_contract_utilized_po','username_created','username_updated','extension_sow_contract','parent_contract_name']

    def get_is_contract_utilized_po(self, obj):
        return UtilizedAmount.objects.filter(sow_contract=obj).exists()

    def get_document(self, obj):
        files = FileModel.objects.filter(document_id=obj.uuid,status='active').values('uuid', 'blob_name')
        return list(files)
    
    def get_parent_contract_name(self, obj):
        if obj.extension_sow_contract:
            try:
                # Validate if extension_sow_contract is a valid UUID
                uuid_obj = uuid.UUID(obj.extension_sow_contract, version=4)
                # If valid, fetch the parent contract
                parent_contract = SowContract.objects.filter(uuid=uuid_obj).first()
                return parent_contract.contractsow_name if parent_contract else None
            except ValueError:
                # Return None if extension_sow_contract is not a valid UUID
                return None
        return None

class ContractSowUpdateSerializer(serializers.ModelSerializer):
    pricing_name = serializers.ReadOnlyField(source='pricing.name')
    estimation_name = serializers.ReadOnlyField(source=EST_NAME)
    total_contract_amount = serializers.DecimalField(max_digits=10, decimal_places=2, coerce_to_string=False, default=Decimal('0.00'))  # Set the appropriate default value
    doc_contract_amount = serializers.DecimalField(max_digits=10, decimal_places=2, default=0)
    document = serializers.SerializerMethodField()
    parent_contract_name = serializers.SerializerMethodField()

    class Meta:
        model = SowContract
        fields = ['uuid', 'contractsow_name', 'total_contract_amount','doc_contract_amount', 'start_date', 'end_date', 'document', 'payment_term_client', 'payment_term_contract', 'contractsow_type', 'pricing_name', 'estimation_name','doc_start_date','doc_end_date','username_updated','extension_sow_contract','parent_contract_name']

    def get_document(self, obj):
        files = FileModel.objects.filter(document_id=obj.uuid,status='active').values('uuid', 'blob_name')
        return list(files)
    
    def get_parent_contract_name(self, obj):
        if obj.extension_sow_contract:
            try:
                # Validate if extension_sow_contract is a valid UUID
                uuid_obj = uuid.UUID(obj.extension_sow_contract, version=4)
                # If valid, fetch the parent contract
                parent_contract = SowContract.objects.filter(uuid=uuid_obj).first()
                return parent_contract.contractsow_name if parent_contract else None
            except ValueError:
                # Return None if extension_sow_contract is not a valid UUID
                return None
        return None
#   ================================================================


class EstimationSerializer(serializers.ModelSerializer):
    is_utilized = serializers.SerializerMethodField()
    client_name = serializers.CharField(source='client.name', read_only=True)
    class Meta:
        model = Estimation
        fields = "__all__"

    def get_is_utilized(self, obj):
        return SowContract.objects.filter(estimation=obj).exists()


class EstimationUpdateSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source=CLIENT_NAME, read_only=True)
    class Meta:
        model = Estimation
        fields = ['name', 'market_cost', 'market_price', 'market_gm', 'company_avg_cost', 'company_avg_price', 'company_avg_gm', 'resource', 'estimation_archived', 'contract_start_date', 'contract_end_date', 'billing', 'client_name','username_updated']


class MainMilestoneCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MainMilestone
        fields = ['uuid','name', 'contract_sow_uuid', 'client_uuid', 'milestone_total_amount', 'milestones','username_created','username_updated']


class MainMilestoneSerializer(serializers.ModelSerializer):
    contractsow_name = serializers.CharField(source='contract_sow_uuid.contractsow_name')

    class Meta:
        model = MainMilestone
        fields = ['uuid','name','contract_sow_uuid', 'client_uuid', 'milestone_total_amount', 'milestones', 'contractsow_name','username_created','username_updated']
class MilestoneUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = MainMilestone
        fields = ['milestone_total_amount', 'milestones','username_updated']

#   ================================================================


class SkillPayRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SkillPayRate
        fields = "__all__"

#   ================================================================
class PricingSerializer(serializers.ModelSerializer):
    estimation_name = serializers.CharField(source=EST_NAME)
    is_price_utilized = serializers.SerializerMethodField()

    class Meta:
        model = Pricing
        fields = '__all__'

    def get_is_price_utilized(self, obj):
        # Check if a Sow_Contract exists that links the given Pricing and Estimation
        return SowContract.objects.filter(pricing=obj, estimation=obj.estimation).exists()

#   ================================================================

class PurchaseOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrder
        fields = '__all__'


class PurchaseOrderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PurchaseOrder
        fields = '__all__'


#   ================================================================

class AllocationSerializer(serializers.ModelSerializer):
    contractsow_name = serializers.CharField(source=SOW_NAME, read_only=True)
    estimation_name = serializers.CharField(source=EST_NAME, read_only=True)
    start_date = serializers.CharField(source='contract_sow.start_date', read_only=True)
    end_date = serializers.CharField(source='contract_sow.end_date', read_only=True)

    class Meta:
        model = Allocation
        fields = "__all__"

    def validate(self, data):
        contract_sow = data.get('contract_sow')
        estimation = data.get('estimation')
        client = data.get('client')

        if Allocation.objects.filter(
            contract_sow=contract_sow,
            estimation=estimation,
            client=client
        ).exclude(pk=self.instance.pk if self.instance else None).exists():
            raise serializers.ValidationError(
                "An allocation with this contract_sow, estimation, and client already exists."
            )

        return data

class FileSerializer(serializers.ModelSerializer):
     class Meta:
        model = FileModel
        fields = "__all__"

class UtilizedAmountSerializer(serializers.ModelSerializer):
    contractsow_name = serializers.CharField(source='sow_contract.contractsow_name', read_only=True)
    purchase_order_name = serializers.CharField(source='purchase_order.purchase_order_name', read_only=True)
    class Meta:
        model = UtilizedAmount
        fields = ['id', 'purchase_order','purchase_order_name', 'sow_contract','contractsow_name', 'utilized_amount','username_created','username_updated']

class PurchaseOrderWithUtilizationSerializer(serializers.ModelSerializer):
    utilized_amounts = UtilizedAmountSerializer(many=True)
    remaining_amount = serializers.SerializerMethodField()
    purchase_order_documents = serializers.SerializerMethodField()

    class Meta:
        model = PurchaseOrder
        fields = ['id', 'purchase_order_name', 'client', 'account_number', 'po_amount', 'start_date', 'end_date', 'purchase_order_documents', 'po_creation_date', 'utilized_amounts', 'remaining_amount']

    def get_remaining_amount(self, obj):
        utilized_total = sum([ua.utilized_amount for ua in obj.utilized_amounts.all()])
        return obj.po_amount - utilized_total

    def get_purchase_order_documents(self, obj):
        files = FileModel.objects.filter(document_id=obj.id,status='active').values('uuid', 'blob_name')
        return list(files)

class POSowContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = SowContract
        fields = '__all__'




class SowContractSerializer(serializers.ModelSerializer):
    estimation_name = serializers.CharField(source=EST_NAME)
    estimation_uuid = serializers.UUIDField(source='estimation.uuid')

    class Meta:
        model = SowContract
        fields = ['uuid', 'contractsow_name', 'estimation_name', 'estimation_uuid']


class EstResourceSerializer(serializers.Serializer):
    role = serializers.CharField()
    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    num_of_resources = serializers.SerializerMethodField()
    billable_hours = serializers.SerializerMethodField()
    cost_hours = serializers.SerializerMethodField()
    resource_data = serializers.ListField(child=serializers.JSONField())
    unplanned_hours = serializers.SerializerMethodField()

    def get_billable_hours(self, obj):
        hours = obj.get('total_estimation_hour', 0)
        if hours:
            hours =  hours / int(obj.get('num_of_resources', 1))
        return int(hours)

    def get_cost_hours(self, obj):
        return obj.get('total_available_hour', 0)

    def get_unplanned_hours(self, obj):
        total_available_hour = obj.get('total_available_hour') or 0
        total_estimation_hour = obj.get('total_estimation_hour') or 0
        try:
            total_available_hour = int(total_available_hour)
            total_estimation_hour = int(total_estimation_hour)
            return max(total_available_hour - total_estimation_hour, 0)
        except ValueError:
            info("Invalid data: Hours should be numeric")
            return 0

    def get_start_date(self, obj):
        return obj.get('start_date')

    def get_end_date(self, obj):
        return obj.get('end_date')
    
    def get_num_of_resources(self, obj):
        return obj.get('num_of_resources')

class EstimationResourceSerializer(serializers.ModelSerializer):
    resource = EstResourceSerializer(many=True)

    class Meta:
        model = Estimation
        fields = ['resource']


class TimesheetOverviewSerializer(serializers.Serializer):
    resource_id = serializers.CharField()
    employee_full_name = serializers.CharField()
    employee_number = serializers.CharField()
    resource_role = serializers.CharField(allow_null=True)
    ongoing_projects = serializers.IntegerField()
    completed_projects = serializers.IntegerField()
    future_projects = serializers.IntegerField()
    incomplete_projects = serializers.IntegerField()
    total_planned_hours = serializers.IntegerField()


def extract_date(date_str):
    """ Extracts only the date part from a datetime string """
    date_pattern = re.compile(r"\d{4}-\d{2}-\d{2}")
    if date_str:
        match = date_pattern.search(date_str)
        if match:
            return match.group()
    return None

def format_hours(hours):
    """Convert decimal hours to HH:MM format."""
    if hours is None:
        hours = 0
    total_minutes = int(hours * 60)
    hours, minutes = divmod(total_minutes, 60)
    return f"{hours:02}:{minutes:02}"

class TimesheetSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source=CLIENT_NAME, read_only=True)
    contractsow_name = serializers.CharField(source=SOW_NAME, read_only=True)
    resource_name = serializers.CharField(source='employee.full_name',read_only=True)
    project_role = serializers.CharField(source='resource_role', read_only=True, allow_null=True)
    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    allocated_hours = serializers.IntegerField(source='cost_hours', read_only=True, allow_null=True)
    planned_hours = serializers.SerializerMethodField()
    recall_count = serializers.SerializerMethodField()

    class Meta:
        model = Timesheet
        fields = ['client_name', 'contractsow_name', 'project_role','resource_name', 'start_date', 'end_date','allocated_hours', 'planned_hours', 'recall_count']
    
    def get_planned_hours(self, obj):
        employee = self.context.get('employee')
        if employee:
            total_billable_hours = EmployeeEntryTimesheet.objects.filter(
                employee_id=employee, timesheet_id=obj
            ).aggregate(total_billable=Sum('billable_hours'))['total_billable'] or 0
            total_billable_hours = format_hours(total_billable_hours)
            return total_billable_hours
        return 0
    

    def get_start_date(self, obj):
        return extract_date(obj.contract_sow.start_date)

    def get_end_date(self, obj):
        return extract_date(obj.contract_sow.end_date)

    def get_recall_count(self, obj):
        timesheet_id = obj.id
        recall_count = EmployeeEntryTimesheet.objects.filter(
        timesheet_id=timesheet_id,
        ts_approval_status="recall").count()
        return recall_count


def get_current_month_weeks():
    today = date.today()
    year, month = today.year, today.month
    weeks = []
    for day in range(1, calendar.monthrange(year, month)[1] + 1):
        date_ = date(year, month, day)
        week_number = date_.isocalendar()[1]
        if (week_number, year) not in weeks:
            weeks.append((week_number, year))
    return weeks


class InvoicesSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invoices
        fields = '__all__'

class InvoicesClientSerializer(serializers.ModelSerializer):
    c2c_invoice_contract_name = serializers.CharField(source='c2c_contract_id.contractsow_name', read_only=True)
    client_name = serializers.CharField(source='c2c_contract_id.client.name', read_only=True)
    purchase_order_number = serializers.SerializerMethodField()

    class Meta:
        model = Invoices
        fields = [
            'c2c_invoice_id',
            'c2c_invoice_contract_name',
            'client_name',
            'purchase_order_number',
            'c2c_invoice_type',
            'c2c_total_hours_count',
            'c2c_resource_count',
            'c2c_invoice_amount',
            'c2c_invoice_generated_on',
            'c2c_invoice_status'
        ]

    def get_purchase_order_number(self, obj):
        utilized_amount = obj.c2c_contract_id.utilized_amounts.first()
        if utilized_amount:
            return utilized_amount.purchase_order.account_number
        return None

class ContractSowIdListSerializer(serializers.Serializer):
    contractsow_ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=True
    )

class EmployeeEntryTimesheetSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source=CLIENT_NAME, read_only=True)
    contract_name = serializers.CharField(source='contract_sow.name', read_only=True)
    start_date = serializers.DateField(source='contract_sow.start_date', read_only=True)
    end_date = serializers.DateField(source='contract_sow.end_date', read_only=True)

    class Meta:
        model = EmployeeEntryTimesheet
        fields = [
            'employee_id',
            'year',
            'week_number',
            'client_name',
            'contract_name',
            'start_date',
            'end_date',
            'billable_hours',
            'non_billable_hours',
            'unplanned_hours',
            'total_hours',
            'non_billable_hours_comments',
            'unplanned_hours_comments'
        ]
        read_only_fields = ['total_hours']


class TimesheetEstimationSerializer(serializers.ModelSerializer):
    client_name = serializers.CharField(source=CLIENT_NAME)
    contract_name = serializers.CharField(source=SOW_NAME)
    start_date = serializers.SerializerMethodField()
    end_date = serializers.SerializerMethodField()
    estimated_hours_by_week = serializers.SerializerMethodField()

    class Meta:
        model = Timesheet
        fields = [
            'client_name',
            'contract_name',
            'billable_hours',
            'start_date',
            'end_date',
            'estimated_hours_by_week'
        ]

    def get_estimated_hours_by_week(self, obj):
        weekly_hours = defaultdict(int)
        estimation_data = obj.resource_estimation_data["Estimation_Data"].get('daily', [])

        for entry in estimation_data:
            date_str = entry.get("date")
            hours = entry.get("hours", 0)
            date_obj = datetime.strptime(date_str, "%d/%m/%Y")
            week_number = date_obj.isocalendar()[1]  # Get ISO week number
            weekly_hours[week_number] += hours

        return dict(weekly_hours)

    def get_start_date(self, obj):
        return obj.resource_estimation_data.get("start_date","")

    def get_end_date(self, obj):
        return obj.resource_estimation_data.get("end_date","")


class GuestUserSerializer(serializers.ModelSerializer):
    approver_type = serializers.CharField(default="Guest", read_only=True)
    approver_id = serializers.CharField(source='guest_user_id', read_only=True)
    approver_name = serializers.CharField(source='guest_user_name', read_only=True)

    class Meta:
        model = GuestUser
        fields = ['approver_id', 'approver_name', 'approver_type']

class EmployeeSerializer(serializers.ModelSerializer):
    approver_type = serializers.CharField(default="Employee", read_only=True)
    approver_id = serializers.CharField(source='employee_source_id', read_only=True)
    approver_name = serializers.CharField(source='employee_full_name', read_only=True)

    class Meta:
        model = Employee
        fields = ['approver_id', 'approver_name', 'approver_type']

def get_week_date_range(year, week_number):
    week_start_date = datetime.fromisocalendar(year, week_number, 1)
    week_end_date = week_start_date + timedelta(days=4)
    formatted_start_date = week_start_date.strftime('%d/%m/%Y')
    formatted_end_date = week_end_date.strftime('%d/%m/%Y')

    return f"{formatted_start_date} - {formatted_end_date}", week_start_date.date(), week_end_date.date()

from datetime import date, timedelta
def get_week_start_end_dates(year, week_number):
    today = date.today()
    if year == today.year:
        current_year, current_week_number, _ = today.isocalendar()
        current_monday = today - timedelta(days=today.weekday())
        week_diff = week_number - current_week_number
        monday = current_monday + timedelta(weeks=week_diff)
    else:
        monday = datetime.strptime(f'{year}-W{week_number}-1', "%Y-W%U-%w").date()
    friday = monday + timedelta(days=4)
    formatted_start_date = monday.strftime('%d/%m/%Y')
    formatted_end_date = friday.strftime('%d/%m/%Y')
    date_str = f"{formatted_start_date} - {formatted_end_date}"
    return date_str , monday, friday

class ApprovalPendingSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee_id.employee_full_name', read_only=True)
    employee_id = serializers.CharField(source='employee_id.employee_source_id', read_only=True)
    pending_timesheets = serializers.SerializerMethodField()
    timesheet_id = serializers.CharField(source='timesheet_id.id', read_only=True)  # Add this line

    class Meta:
        model = EmployeeEntryTimesheet
        fields = ['employee_name', 'employee_id', 'pending_timesheets', 'timesheet_id']
    
    def get_unplanned_hours(self, obj):
        week_number = obj.week_number
        employee_id = obj.employee_id
        year = obj.year
        unplanned_hours_queryset = EmployeeUnplannedNonbillableHours.objects.filter(
            week_number=week_number,
            year = year,
            employee_id=employee_id
        )
        total_unplanned_hours = unplanned_hours_queryset.aggregate(
            total=Sum('unplanned_hours')
        )['total'] or 0.0
        return total_unplanned_hours
    
    def get_timeoff_hours(self, obj):
        week_number = obj.week_number
        employee_id = obj.employee_id
        year = obj.year
        non_billable_hours_queryset = EmployeeUnplannedNonbillableHours.objects.filter(
            week_number=week_number,
            employee_id=employee_id,
            year = year,
        )
        total_non_billable_hours = non_billable_hours_queryset.aggregate(
            total=Sum('non_billable_hours')
        )['total'] or 0.0
        return total_non_billable_hours
    
    def get_unplanned_timesheet_id(self, obj):
        week_number = obj.week_number
        employee_id = obj.employee_id
        year = obj.year
        non_billable_hours_queryset = EmployeeUnplannedNonbillableHours.objects.filter(
            week_number=week_number,
            employee_id=employee_id,
            year = year,
        ).first()
        if non_billable_hours_queryset:
            return non_billable_hours_queryset.id
        return None
    
    def get_pending_timesheets(self, obj):
        year = obj.year
        week_number = obj.week_number
        date_str, week_start_date, week_end_date = get_week_date_range(year, week_number)
        daily_data = obj.timesheet_id.resource_estimation_data.get("Estimation_Data", {}).get("daily", [])
        filtered_data = [
            day for day in daily_data
            if week_start_date <= datetime.strptime(day["date"], "%d/%m/%Y").date() <= week_end_date
        ]
        allocated_hours = sum(day["hours"] for day in filtered_data)

        contract_data = {
            "timesheet_id": obj.id,
            "client_name": obj.client.name if obj.client else "Unknown Client",
            "contract_sow_name": obj.contract_sow.contractsow_name if obj.contract_sow else "Unknown Contract",
            "allocated_hours": allocated_hours,
            "timesheet_hours": format_hours(obj.billable_hours),
        }
        return {
            "week_number": date_str,
            "week": week_number,
            "contracts": [contract_data],
            "unplanned_hours": format_hours(self.get_unplanned_hours(obj)),
            "timeoff_hours": format_hours(self.get_timeoff_hours(obj)),
            "unplanned_timesheet_id": self.get_unplanned_timesheet_id(obj),
        }
        

class EmployeeUnplannedNonbillableHoursSerializer(serializers.ModelSerializer):
    timesheet_id = serializers.CharField(source='id', read_only=True)
    timeoff_hours = serializers.FloatField(source = "non_billable_hours", read_only=True)
    timeoff_hours_comments = serializers.CharField(source = "non_billable_hours_comments", read_only=True)
    week_number = serializers.SerializerMethodField()
    week = serializers.CharField(source = "week_number", read_only=True)
    employee_name = serializers.CharField(source='employee_id.employee_full_name', read_only=True)
    class Meta:
        model = EmployeeUnplannedNonbillableHours
        fields = [
            "timesheet_id",
            "employee_id",
            "employee_name",
            "year",
            'week',
            "week_number",
            "timeoff_hours",
            "unplanned_hours",
            "timeoff_hours_comments",
            "unplanned_hours_comments",
            "ts_approval_status",
            "approver_comments",
        ]

    def get_week_number(self, obj):
        year = obj.year
        week_number = obj.week_number
        date_str, week_start_date, week_end_date = get_week_date_range(year, week_number)
        return date_str
    
class C2CRateCardConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = C2CRateCardConfig
        fields = ['unique_id','dollar_conversion_rate','overhead_percentage','non_billable_days_per_year','desired_gross_margin_percentage','overhead_percentage_usa','non_billable_days_per_year_usa','desired_gross_margin_percentage_usa','minimum_sellrate_usa','minimum_sell_rate','status']


class AdminApprovalPendingSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source='employee_id.employee_full_name', read_only=True)
    employee_id = serializers.CharField(source='employee_id.employee_source_id', read_only=True)
    pending_timesheets = serializers.SerializerMethodField()
    timesheet_id = serializers.CharField(source='timesheet_id.id', read_only=True)

    class Meta:
        model = EmployeeEntryTimesheet
        fields = ['employee_name', 'employee_id', 'pending_timesheets', 'timesheet_id']

    def get_unplanned_hours(self, obj):
        unplanned_hours_queryset = EmployeeUnplannedNonbillableHours.objects.filter(
            week_number=obj.week_number,
            year=obj.year,
            employee_id=obj.employee_id
        )
        total_unplanned_hours = unplanned_hours_queryset.aggregate(
            total=Sum('unplanned_hours')
        ).get('total', 0.0)
        return total_unplanned_hours or 0.0

    def get_timeoff_hours(self, obj):
        non_billable_hours_queryset = EmployeeUnplannedNonbillableHours.objects.filter(
            week_number=obj.week_number,
            year=obj.year,
            employee_id=obj.employee_id
        )
        total_non_billable_hours = non_billable_hours_queryset.aggregate(
            total=Sum('non_billable_hours')
        ).get('total', 0.0)
        return total_non_billable_hours or 0.0
    
    def get_unplanned_hours_comments(self, obj):
        unplanned_entry = EmployeeUnplannedNonbillableHours.objects.filter(
            week_number=obj.week_number,
            year=obj.year,
            employee_id=obj.employee_id
        ).first()
        return unplanned_entry.unplanned_hours_comments if unplanned_entry else ""
        
    def get_timeoff_hours_comments(self, obj):
        timeoff_entry = EmployeeUnplannedNonbillableHours.objects.filter(
            week_number=obj.week_number,
            year=obj.year,
            employee_id=obj.employee_id
        ).first()
        return timeoff_entry.non_billable_hours_comments if timeoff_entry else ""
        

    def get_unplanned_timesheet_id(self, obj):
        """Retrieve the unplanned timesheet ID if available."""
        unplanned_entry = EmployeeUnplannedNonbillableHours.objects.filter(
            week_number=obj.week_number,
            year=obj.year,
            employee_id=obj.employee_id
        ).first()
        return unplanned_entry.id if unplanned_entry else None

    def get_unplanned_status(self, obj):
        """Retrieve the unplanned timesheet status if available."""
        unplanned_entry = EmployeeUnplannedNonbillableHours.objects.filter(
            week_number=obj.week_number,
            year=obj.year,
            employee_id=obj.employee_id
        ).first()
        return unplanned_entry.ts_approval_status if unplanned_entry else ""

    def get_pending_timesheets(self, obj):
        """Get pending timesheets, including employees who only have unplanned hours."""
        year, week_number = obj.year, obj.week_number
        date_str, week_start_date, week_end_date = get_week_date_range(year, week_number)

        if hasattr(obj, 'timesheet_id') and obj.timesheet_id:
            daily_data = obj.timesheet_id.resource_estimation_data.get("Estimation_Data", {}).get("daily", [])
            filtered_data = [
                day for day in daily_data
                if week_start_date <= datetime.strptime(day["date"], "%d/%m/%Y").date() <= week_end_date
            ]
            allocated_hours = sum(day["hours"] for day in filtered_data)

            contracts = [{
                "timesheet_id": obj.id,
                "client_name": obj.client.name if obj.client else "Unknown Client",
                "contract_sow_name": obj.contract_sow.contractsow_name if obj.contract_sow else "Unknown Contract",
                "allocated_hours": allocated_hours,
                "timesheet_hours": format_hours(obj.billable_hours),
                "timesheet_status": obj.ts_approval_status,
            }]
        else:
            # If no planned timesheet exists, contracts should be empty.
            contracts = []

        return {
            "week_number": date_str,
            "week": week_number,
            "year": year,
            "contracts": contracts,
            "unplanned_hours": format_hours(self.get_unplanned_hours(obj)),
            "timeoff_hours": format_hours(self.get_timeoff_hours(obj)),
            "unplanned_hours_comments": self.get_unplanned_hours_comments(obj),
            "timeoff_hours_comments": self.get_timeoff_hours_comments(obj),
            "unplanned_timesheet_id": self.get_unplanned_timesheet_id(obj),
            "unplanned_timesheet_status": self.get_unplanned_status(obj),
        }
    

class UnplannedHoursSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee_id.employee_full_name", read_only=True)
    pending_timesheets = serializers.SerializerMethodField()

    class Meta:
        model = EmployeeUnplannedNonbillableHours
        fields = ["employee_id", "employee_name", "pending_timesheets"]

    def get_contracts(self, obj):
        records = EmployeeEntryTimesheet.objects.filter(week_number=obj.week_number, year=obj.year, employee_id=obj.employee_id)
        year, week_number = obj.year, obj.week_number
        date_str, week_start_date, week_end_date = get_week_date_range(year, week_number)
        if records:
            contracts = []
            for record in records:

                daily_data = record.timesheet_id.resource_estimation_data.get("Estimation_Data", {}).get("daily", [])
                filtered_data = [
                    day for day in daily_data
                    if week_start_date <= datetime.strptime(day["date"], "%d/%m/%Y").date() <= week_end_date
                ]
                allocated_hours = sum(day["hours"] for day in filtered_data)
                contracts.append({
                    "timesheet_id": record.id,
                    "client_name": record.client.name if record.client else "Unknown Client",
                    "contract_sow_name": record.contract_sow.contractsow_name if record.contract_sow else "Unknown Contract",
                    "allocated_hours": allocated_hours,
                    "timesheet_hours": format_hours(record.billable_hours),
                    "timesheet_status": record.ts_approval_status,
                })
            return contracts

    def get_pending_timesheets(self, obj):
        """Custom representation to group timesheets by employee_id."""
        year, week_number = obj.year, obj.week_number
        date_str, _, _ = get_week_date_range(year, week_number)  # Format the date range
        pending_timesheet = {
            "week_number": date_str,
            "week": obj.week_number,
            "year": obj.year,
            "contracts": self.get_contracts(obj),
            "unplanned_hours": format_hours(obj.unplanned_hours),
            "timeoff_hours": format_hours(obj.non_billable_hours),
            "unplanned_comments": obj.unplanned_hours_comments,
            "timeoff_comments": obj.non_billable_hours_comments,
            "unplanned_timesheet_id": obj.id,
            "unplanned_timesheet_status": obj.ts_approval_status,
        }
        return pending_timesheet
    
class ReportSowContractSerializer(serializers.ModelSerializer):
    class Meta:
        model = SowContract
        fields = '__all__'