from django.db import models, IntegrityError, transaction
import uuid
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.apps import apps
from config import (ACTIVE, INACTIVE, POTENTIAL_LEAD, ONBOARDED, US, LATAM,
                    IND, EUR, USD, INR, EMPLOYEE, CONTRACTOR, EMPLOYEE_HOURLY, SUB_CONTRACTOR)
from django.utils.translation import gettext_lazy as _

NET15="Net 15"
NET30="Net 30"
NET45="Net 45"
NET60="Net 60"
NET90="Net 90"
NULL = "null"
DUE_ON_RECEIPT="Due on receipt"
PAYMENT_TERMS_CHOICES = [(NET15,"Net 15"),(NET30,"Net 30"),(NET45,"Net 45"),(NET60,"Net 60"),(NET90,"Net 90"),(DUE_ON_RECEIPT,"Due on receipt"),(NULL,"null")]
INVOICE_TERMS_CHOICES = [(ACTIVE, "Active"),(INACTIVE, "Inactive"),(POTENTIAL_LEAD, "Potential Lead"),(ONBOARDED, "ONBOARDED")]
REGION_CHOICES = [(US, "US"),(LATAM, "LATAM"),(IND, "IND"),(EUR, "EUR")]
CURRENCY_CHOICES = [(USD,"USD"),(INR,"INR"),(EUR,"EUR")]
EMPLOYMENT_TYPE = [(EMPLOYEE,"Employee"),(CONTRACTOR,"Contractor"),(EMPLOYEE_HOURLY, "Hourly Employee"),(SUB_CONTRACTOR, "Sub-Contractor")]
START_DATE = "Start_Date"
END_DATE = "End_Date"
TS_APPROVAL_STATUS_CHOICES = [
        ("approved", "Approved"),
        ("not submitted", "Not Submitted"),
        ("submitted", "Submitted"),
        ("recall", "Recall"),
    ]
STATUS_CHOICES = [
        ('active', 'Active'),
        ('inactive', 'Inactive'),
    ]

class AbstractBaseModel(models.Model):
    """
    Base abstract model, that has `uuid` instead of `id` and includes `created_at`, `updated_at` fields.
    """
    uuid = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)
    date_created = models.DateTimeField(_("Date Created"), auto_now_add=True, db_index=True)
    date_updated = models.DateTimeField(_("Date Updated"), auto_now=True, db_index=True)
    username_created = models.CharField(max_length=255,blank=True,null=True)
    username_updated = models.CharField(max_length=255,blank=True,null=True)

    class Meta:
        abstract = True

    def __repr__(self):
        return f'<{self.__class__.__name__} {self.uuid}>'

class Client(AbstractBaseModel):
    name = models.CharField(max_length=255,unique=True)
    address = models.TextField(null=True, blank=True)
    city = models.CharField(max_length=255, null=True, blank=True)
    state = models.CharField(max_length=255, null=True, blank=True)
    country = models.CharField(max_length=255, null=True, blank=True)
    zip_code = models.CharField(max_length=255, null=True, blank=True)
    deleted = models.BooleanField(default=False)
    test = models.BooleanField(default=False)
    client_created_by = models.CharField(max_length=255, null=True)
    client_creation_date = models.DateTimeField(("client_creation_date"), db_index=True, auto_now_add=True,  null=True)
    client_ap_details = models.JSONField(null=True, blank=True)
    client_payment_terms = models.CharField(max_length=20,choices=PAYMENT_TERMS_CHOICES,null=True, blank=True)
    client_invoice_terms = models.CharField(max_length=33,choices=INVOICE_TERMS_CHOICES,default=ACTIVE)
    business_unit = models.CharField(max_length=255, null=True, blank=True)

    class Meta:
        verbose_name = 'Client'
        verbose_name_plural = 'Clients'
        ordering = ('-client_creation_date',)

class Contract(AbstractBaseModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="client_contracts")
    name = models.CharField(max_length=255,unique=True)
    start_date = models.CharField(_(START_DATE),max_length=255, db_index=True)
    end_date = models.CharField(_(END_DATE),max_length=255, null=True, blank=True)
    status = models.BooleanField(default=True)
    files = models.JSONField(default=list)
    contract_name = models.CharField(max_length=255, default="Default Contract Name")
    end_type = models.CharField(max_length=255, default="")
    payment_terms = models.CharField(max_length=20,choices=PAYMENT_TERMS_CHOICES,null=True,blank=True)
    contract_end_type = models.CharField(max_length=255, default="")
    contract_version = models.FloatField(default=1.0)
    contract_creation_date = models.DateTimeField(auto_now_add=True, null=True)
    contract_created_by = models.CharField(max_length=100, null=True)


    class Meta:
        verbose_name = 'Contract'
        verbose_name_plural = 'Contracts'


class FileModel(AbstractBaseModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="client")
    document_id = models.CharField(max_length=255,blank=True, null=True)
    document_type = models.CharField(max_length=30, blank=True, null=True)
    blob_name = models.CharField(max_length=255, null=True,blank=True)
    status = models.CharField(max_length=8, choices=STATUS_CHOICES, default='active')

    def __str__(self):
        return self.blob_name if self.blob_name else str(self.pk)


class Estimation(AbstractBaseModel):
    name = models.CharField(max_length=255,unique=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="client_estimation")
    market_cost = models.FloatField(null=True, blank=True)
    market_price = models.FloatField(null=True, blank=True)
    market_gm = models.FloatField(null=True, blank=True)
    company_avg_cost = models.FloatField(null=True, blank=True)
    company_avg_price = models.FloatField(null=True, blank=True)
    company_avg_gm = models.FloatField(null=True, blank=True)
    contract_start_date = models.CharField(_(START_DATE),max_length=255, db_index=True,null=True,blank=True)
    contract_end_date = models.CharField(_(END_DATE),max_length=255, db_index=True,null=True,blank=True)
    resource = models.JSONField()
    estimation_archived = models.BooleanField(default=False)
    billing = models.CharField(max_length=255, db_index=True,null=True,blank=True)

    def __str__(self):
        return self.name

class SkillPayRate(models.Model):
    role = models.CharField(max_length=500,default='Assign Role')
    experience = models.CharField(max_length=100,default='Assign Experience')
    skill = models.JSONField()
    billrate = models.DecimalField(decimal_places=2, max_digits=10, null=True, blank=True)
    payrate = models.DecimalField(decimal_places=2, max_digits=10, null=True, blank=True)
    companyrate = models.DecimalField(decimal_places=2, max_digits=10, null=True, blank=True)
    marketrate = models.DecimalField(decimal_places=2, max_digits=10, null=True, blank=True)
    location = models.CharField(max_length=500)

    def __str__(self):
        return self.role + " - " + self.experience + " - " + self.location + " - " + str(self.billrate) + " - " + str(self.payrate) + " - " + str(self.companyrate) + " - " + str(self.marketrate)



class Pricing(AbstractBaseModel):
    name = models.CharField(max_length=255,unique=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="client_pricing")
    estimation = models.ForeignKey(Estimation, on_delete=models.CASCADE, related_name="estimation_pricing")
    estimated_market_cost = models.FloatField(null=True, blank=True)
    estimated_market_price = models.FloatField(null=True, blank=True)
    estimated_company_avg_cost = models.FloatField(null=True, blank=True)
    estimated_company_avg_price = models.FloatField(null=True, blank=True)
    market_gm = models.FloatField(null=True, blank=True)
    company_avg_gm = models.FloatField(null=True, blank=True)
    final_offer_price = models.FloatField(null=True, blank=True)
    final_offer_gross_margin_percentage = models.FloatField(null=True, blank=True)
    final_offer_margin = models.FloatField(null=True, blank=True)
    discount = models.FloatField(null=True, blank=True)
    pricing_creation_date = models.DateTimeField(("pricing_creation_date"), db_index=True, auto_now_add=True,  null=True)

    def __str__(self):
        return self.name

class SowContract(AbstractBaseModel):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="client_contractsow")
    pricing = models.ForeignKey(Pricing, on_delete=models.CASCADE, related_name="pricing_contractsow")
    estimation = models.ForeignKey(Estimation, on_delete=models.CASCADE, related_name="estimation_contractsow")
    contractsow_name = models.CharField(max_length=255,unique=True)
    total_contract_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    start_date = models.CharField(_(START_DATE),max_length=255, db_index=True,blank=True, null=True)
    contractsow_creation_date = models.DateField(("contractsow_creation_date"), db_index=True, auto_now_add=True)
    end_date = models.CharField(_(END_DATE),max_length=255, db_index=True,blank=True, null=True)
    document = models.JSONField(default=list)
    payment_term_client = models.CharField(max_length=255, default="Default Payment term")
    payment_term_contract = models.CharField(max_length=20,choices=PAYMENT_TERMS_CHOICES,default=NET30,)
    contractsow_type = models.CharField(max_length=255, default="")
    doc_contract_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    doc_start_date = models.CharField(_("Doc Start Date"),max_length=255, db_index=True,blank=True, null=True)
    doc_end_date = models.CharField(_("Doc End Date"),max_length=255, db_index=True,blank=True, null=True)
    extension_sow_contract = models.CharField(default=None, null=True, blank=True)

    class Meta:
        verbose_name = 'Sow_Contract'
        verbose_name_plural = 'Sow_Contracts'



class PurchaseOrder(models.Model):
    id = models.AutoField(primary_key=True, unique=True, editable=False)
    purchase_order_name = models.CharField(max_length=255,unique=True)
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='client_po')
    account_number = models.CharField(max_length=50)
    po_amount = models.DecimalField(max_digits=30, decimal_places=2)
    start_date = models.CharField(_(START_DATE),max_length=255, db_index=True,blank=True, null=True)
    end_date = models.CharField(_(END_DATE),max_length=255, db_index=True,blank=True, null=True)
    purchase_order_documents = models.JSONField(default=list)
    po_creation_date = models.DateTimeField(("po_creation_date"), db_index=True, auto_now_add=True,  null=True)
    username_created = models.CharField(max_length=255,null=True,blank=True)
    username_updated = models.CharField(max_length=255,null=True,blank=True)

class UtilizedAmount(models.Model):
    id = models.AutoField(primary_key=True)
    purchase_order = models.ForeignKey(PurchaseOrder, on_delete=models.CASCADE, related_name='utilized_amounts')
    sow_contract = models.ForeignKey(SowContract, on_delete=models.CASCADE, related_name='utilized_amounts')
    utilized_amount = models.DecimalField(max_digits=30, decimal_places=2)
    username_created = models.CharField(max_length=255,null=True,blank=True)
    username_updated = models.CharField(max_length=255,null=True,blank=True)

    class Meta:
        # Define unique constraint for sow_contract and purchase_order combination
        unique_together = ['sow_contract', 'purchase_order']

    def save(self, *args, **kwargs):
        with transaction.atomic():
            if not self.pk:
                try:
                    existing_record = UtilizedAmount.objects.get(sow_contract=self.sow_contract, purchase_order=self.purchase_order)
                    existing_record.utilized_amount = self.utilized_amount
                    existing_record.save()
                    self.pk = existing_record.pk
                except UtilizedAmount.DoesNotExist:
                    super().save(*args, **kwargs)
            else:
                super().save(*args, **kwargs)


class MainMilestone(AbstractBaseModel):
    name = models.CharField(max_length=255, unique=True)
    contract_sow_uuid = models.OneToOneField(SowContract, on_delete=models.CASCADE, related_name="contractsow_milestones")
    client_uuid = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="milestones")
    milestone_total_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    milestones = models.JSONField()


class Employee(models.Model):
    employee_source_id = models.CharField(primary_key=True)
    employee_full_name = models.CharField(max_length=100,blank=True)
    employee_email = models.EmailField(null=True,blank=True)
    employee_skills = models.CharField(max_length=225, blank=True, null=True)
    employee_work_authorization = models.CharField(max_length=100, blank=True, null=True)
    employee_location = models.CharField(max_length=100, blank=True, null=True)
    employee_category = models.CharField(max_length=100, null=True,blank=True)
    employee_reporting_manager = models.CharField(max_length=225, blank=True, null=True)
    employee_department = models.CharField(max_length=100, blank=True, null=True)
    employee_designation = models.CharField(max_length=100, blank=True, null=True)
    employee_assigned_role = models.CharField(max_length=200, null=True,blank=True)
    employee_account_type = models.CharField(max_length=200, null=True, blank=True)
    employee_joined_date = models.CharField(null=True, blank=True, default="01-01-2025")
    employee_status = models.CharField(max_length=200, null=True,blank=True)


    def __str__(self):
        return f"{self.employee_full_name}"
    

class Allocation(AbstractBaseModel):
    name = models.CharField(max_length=255, unique=True,null=True)
    contract_sow = models.ForeignKey(SowContract, on_delete=models.CASCADE,related_name="contractsow_allocation")
    estimation = models.ForeignKey(Estimation, on_delete=models.CASCADE,related_name="estimation_allocation")
    client = models.ForeignKey(Client, on_delete=models.CASCADE,related_name="client_allocation",null=True)
    total_billable_hours = models.FloatField(null=True,blank=True)
    total_cost_hours = models.FloatField(null=True,blank=True)
    total_unplanned_hours = models.FloatField(null=True,blank=True)
    allocations_count = models.IntegerField(null=True,blank=True)
    resource_data = models.JSONField(blank=True, null=True,default=list)
    approver = models.JSONField(default=list,null=True,blank=True)

    class Meta:
        unique_together = ['contract_sow', 'estimation', 'client']
        verbose_name = 'Allocation'
        verbose_name_plural = 'Allocations'

    def clean(self):
        # Additional validation logic can be added here
        super().clean()
        if Allocation.objects.filter(
            contract_sow=self.contract_sow,
            estimation=self.estimation,
            client=self.client
        ).exclude(pk=self.pk).exists():
            raise ValidationError("An allocation with this contract_sow, estimation, and client already exists.")


class Timesheet(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="timesheet_client",null=True,blank=True)
    estimation = models.ForeignKey(Estimation, on_delete=models.CASCADE, related_name="timesheet_estimation",null=True,blank=True)
    allocation = models.ForeignKey(Allocation, on_delete=models.CASCADE, related_name="timesheet_allocation",null=True,blank=True)
    resource = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="timesheet_resource")
    resource_role = models.CharField(max_length=100,null=True,blank=True)
    billable_hours = models.IntegerField(null=True,blank=True)
    cost_hours = models.IntegerField(null=True,blank=True)
    resource_estimation_data = models.JSONField(blank=True, null=True,default=dict)
    contract_sow = models.ForeignKey(SowContract, on_delete=models.CASCADE, related_name="timesheet_contractsow",null=True,blank=True)
    username_created = models.CharField(max_length=255,null=True,blank=True)
    username_updated = models.CharField(max_length=255,null=True,blank=True)
    date_created = models.DateTimeField(_("Date Created"), auto_now_add=True, db_index=True)
    date_updated = models.DateTimeField(_("Date Updated"), auto_now=True, db_index=True)
    approver = models.JSONField(default=list,null=True,blank=True)

    def __str__(self):
        return f"{self.resource_id} - {self.resource_role}"

class EmployeeEntryTimesheet(models.Model):
    timesheet_id = models.ForeignKey(Timesheet, on_delete=models.CASCADE,blank=True, null=True, related_name="employee_entry_timesheet")
    employee_id = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="employee_entry_id")
    year = models.PositiveIntegerField()
    week_number = models.PositiveIntegerField()
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="employee_entry_client",null=True,blank=True)
    contract_sow = models.ForeignKey(SowContract, on_delete=models.CASCADE, related_name="employee_entry_contract_sow",null=True,blank=True)
    billable_hours = models.FloatField()
    non_billable_hours = models.FloatField()
    unplanned_hours = models.FloatField()
    total_hours = models.FloatField()
    non_billable_hours_comments = models.TextField(blank=True, null=True)
    unplanned_hours_comments = models.TextField(blank=True, null=True)
    approver = models.JSONField(default=list,null=True,blank=True)
    ts_approval_status = models.CharField(max_length=20,choices=TS_APPROVAL_STATUS_CHOICES,default="submitted")
    approver_comments = models.TextField(blank=True, null=True)
    approved_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField(_("Date Created"), auto_now_add=True, db_index=True)
    date_updated = models.DateTimeField(_("Date Updated"), auto_now=True, db_index=True)
    username_created = models.CharField(max_length=255,blank=True,null=True)
    username_updated = models.CharField(max_length=255,blank=True,null=True)
    def parse_time_string(self, time_input):
        """Convert a time input to a float value and back to 'HH:MM' string format."""
        if isinstance(time_input, int):
            return float(time_input)
        elif isinstance(time_input, str):
            try:
                hours, minutes = map(int, time_input.split(':'))
                return hours + minutes / 60.0
            except ValueError:
                raise ValueError(f"Invalid time format: '{time_input}'")
        raise ValueError("Invalid time input; expected int or str.")

    def clean(self):
        super().clean()
        
        # Allow empty client and contract_sow entries, but ensure uniqueness for employee, year, and week
        if self.client and self.contract_sow and EmployeeEntryTimesheet.objects.filter(
            employee_id=self.employee_id,
            year=self.year,
            week_number=self.week_number,
            client=self.client,
            contract_sow=self.contract_sow
        ).exclude(id=self.id).exists():
            raise ValidationError("An entry with this employee, client, contract SOW, year, and week already exists.")

        if not self.client and not self.contract_sow: 
            # Allow empty client and contract_sow, no conflict here
            return

        if self.client and not self.contract_sow:
            raise ValidationError("Contract SOW is required when client is provided.")

        if self.contract_sow and not self.client:
            raise ValidationError("Client is required when contract SOW is provided.")

    def set_hours_as_float(self):
        for field in ['billable_hours', 'non_billable_hours', 'unplanned_hours']:
            value = getattr(self, field)
            if isinstance(value, str):
                setattr(self, field, self.parse_time_string(value))
            elif isinstance(value, int):
                setattr(self, field, float(value))

    def calculate_total_hours(self):
        self.total_hours = self.billable_hours + self.non_billable_hours + self.unplanned_hours

    @transaction.atomic
    def save(self, *args, **kwargs):
        self.set_hours_as_float()
        self.calculate_total_hours()
        self.clean()
        super().save(*args, **kwargs)


class EmployeeUnplannedNonbillableHours(models.Model):
    employee_id = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="employee_unplanned_non_billable_entry_id")
    year = models.PositiveIntegerField()
    week_number = models.PositiveIntegerField()
    non_billable_hours = models.FloatField(blank=True, null=True)
    unplanned_hours = models.FloatField(blank=True, null=True)
    non_billable_hours_comments = models.TextField(blank=True, null=True)
    unplanned_hours_comments = models.TextField(blank=True, null=True)
    approver = models.JSONField(default=list,null=True,blank=True)
    ts_approval_status = models.CharField(max_length=20,choices=TS_APPROVAL_STATUS_CHOICES,default="submitted")
    approver_comments = models.TextField(blank=True, null=True)
    approved_by = models.CharField(max_length=255, blank=True, null=True)
    date_created = models.DateTimeField(_("Date Created"), auto_now_add=True, db_index=True)
    date_updated = models.DateTimeField(_("Date Updated"), auto_now=True, db_index=True)
    username_created = models.CharField(max_length=255,blank=True,null=True)
    username_updated = models.CharField(max_length=255,blank=True,null=True)
    def parse_time_string(self, time_input):
        """Convert a time input to a float value and back to 'HH:MM' string format."""
        if isinstance(time_input, int):
            return float(time_input)
        elif isinstance(time_input, str):
            try:
                hours, minutes = map(int, time_input.split(':'))
                return hours + minutes / 60.0
            except ValueError:
                raise ValueError(f"Invalid time format: '{time_input}'")
        raise ValueError("Invalid time input; expected int or str.")
    
    def set_hours_as_float(self):
        for field in ['non_billable_hours', 'unplanned_hours']:
            value = getattr(self, field)
            if isinstance(value, str):
                setattr(self, field, self.parse_time_string(value))
            elif isinstance(value, int):
                setattr(self, field, float(value))
    
    @transaction.atomic
    def save(self, *args, **kwargs):
        self.set_hours_as_float()
        self.clean()
        super().save(*args, **kwargs)

class Invoices(models.Model):
    STATUS_CHOICES = [
        ('Active', 'Active'),
        ('Email Sent', 'Email Sent'),
        ('Paid', 'Paid')
    ]

    c2c_invoice_id = models.CharField(max_length=255, unique=True, primary_key=True)
    c2c_client_id = models.ForeignKey(Client, on_delete=models.CASCADE)
    c2c_contract_id = models.ForeignKey(SowContract, on_delete=models.CASCADE)
    c2c_invoice_type = models.CharField(max_length=50)
    c2c_invoice_type_id = models.CharField(max_length=50)
    c2c_invoice_amount = models.DecimalField(max_digits=100, decimal_places=2)
    c2c_old_invoice_amount = models.DecimalField(max_digits=100, decimal_places=2, null=True, blank=True)
    c2c_invoice_generated_on = models.DateTimeField(default=timezone.now)
    c2c_invoice_status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='Active')
    c2c_invoice_email_sent_by = models.CharField(max_length=100, blank=True, null=True)
    c2c_invoice_payment_marked_by = models.CharField(max_length=100, blank=True, null=True)
    c2c_total_hours_count = models.CharField(max_length=100, blank=True, null=True)
    c2c_resource_count = models.IntegerField(blank=True, null=True)

    def __str__(self):
        return f"{self.c2c_invoice_id} -- {self.c2c_invoice_amount} -- {self.c2c_invoice_status}"

class ProfilingResult(models.Model):
    path = models.CharField(max_length=255)
    function_name = models.CharField(max_length=255)
    cumulative_time = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.path} - {self.function_name} - {self.cumulative_time:.6f}s"
    
class GuestUser(models.Model):
    guest_user_id = models.CharField(max_length=255, primary_key=True)
    guest_user_name = models.CharField(max_length=255, blank=True, null=True)
    guest_user_email_id = models.EmailField(unique=True)
    client_ids = models.JSONField(default=list,null=True,blank=True)
    guest_user_status = models.CharField(
        max_length=10,
        choices=STATUS_CHOICES,
        default='active'
    )
    created_by = models.CharField(max_length=255, blank=True, null=True)
    updated_by = models.CharField(max_length=255, blank=True, null=True)
    created_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.guest_user_id


class C2CRateCardConfig(models.Model):
    unique_id = models.AutoField(primary_key=True)
    dollar_conversion_rate = models.FloatField(help_text="Conversion rate (e.g., 84 INR/USD)")
    overhead_percentage = models.FloatField(help_text="Overhead percentage (e.g., 20%)")
    non_billable_days_per_year = models.IntegerField(help_text="Non-billable days per year (e.g., 20)")
    desired_gross_margin_percentage = models.FloatField(help_text="Desired Gross Margin percentage (e.g., 30%)")
    overhead_percentage_usa = models.FloatField(help_text="Overhead percentage (e.g., 20%)")
    non_billable_days_per_year_usa = models.IntegerField(help_text="Non-billable days per year (e.g., 20)")
    desired_gross_margin_percentage_usa = models.FloatField(help_text="Desired Gross Margin percentage (e.g., 30%)")
    minimum_sellrate_usa = models.FloatField(help_text="Minimum sell rate in USA (e.g., 20.00)")
    minimum_sell_rate = models.FloatField(help_text="Minimum sell rate (e.g., 20.00)")
    status = models.CharField(max_length=10, choices=[("active", "Active"), ("inactive", "Inactive")], default="active")
    date_created = models.DateTimeField(_("Date Created"), auto_now_add=True, db_index=True)
    date_updated = models.DateTimeField(_("Date Updated"), auto_now=True, db_index=True)
    username_created = models.CharField(max_length=255,blank=True,null=True)
    username_updated = models.CharField(max_length=255,blank=True,null=True)

    def __str__(self):
        return f"Rate Card {self.unique_id} - {self.status}"
    