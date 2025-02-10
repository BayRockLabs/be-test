from django.urls import path
from c2c_modules.clientview import ClientAPIView, SearchAPIView, ClientDetailsAPIView, NameSearchAPIView, C2CRateCardConfigAPIView
from c2c_modules.contractview import ContractGetAPIView, ContractPostAPIView, ContractPatchAPIView, FileView, AzurBlobFileDeleter, AzurBlobFileDownload, FileListByClientView, FileListByContractView
from c2c_modules.contractsowview import ContractSowDetailView, ContractSowGetAPIView, ContractSowPostAPIView, ContractSowDetailCheckView
from c2c_modules.estimationview import EstimationGetAPIView, EstimationPostAPIView, SingleEstimationAPIView
from c2c_modules.pricingview import PricingGetAPIView, PricingDetailAPIView, PricingPostAPIView
from c2c_modules.purchaseorderview import PurchaseOrderCreateView, PurchaseOrderRetrieveUpdateDeleteView, UnassignedSowContractsView, UtilizedAmountListCreateAPIView, UtilizedAmountRetrieveUpdateDestroyAPIView, PurchaseOrderClientWithUnUtilizationAPIView, PurchaseOrderClientWithUtilizationAPIView, PurchaseOrderByIdAPIView, CheckPOAccountNumberView, DeleteUtilizedAmountView, PurchaseOrderWithUtilizationAPIView
from c2c_modules.allocationview import AllocationAPIView, AllocationClientGetAPIView, AllocationDetailView, SowContractListView, EstimationDetailByContractView, CheckAllocationView
from c2c_modules.milestoneview import MilestoneDetailAPIView, MilestoneDetailCheckView, MilestoneGetAPIView, MilestonePostAPIView, CheckMilestoneNameView
from c2c_modules.payrateview import SkillPayRateAPIView
from c2c_modules.resourceview import TimesheetOverviewView, ResourceTimesheetsView, ResourceTimesheetsByNameView, TimesheetSubmissionAPIView, TimesheetRetrieveAPIView, TimesheetEstimationView, EmployeeProjectsView, AllEmployeeProjectsView
from c2c_modules.employeeview import RoleCountsView, SkillCountsView, EmployeeSearchAPIView, EmpTypeCountryCountsView, RoleEmployeeListView, SkillEmployeeListView, EmpTypeCountryEmployeeListView,EmployeeTimesheetView, AddTimesheetView, EmployeeTimesheetStatusAPIView, ClientTimesheetView,UnplannedHoursView, TimeOffHoursView, EmployeeHoursView, EmployeeHoursDownloadView, RecallTimesheetView
from c2c_modules.reportview import ContractsEndingReportAPIView, SowContractAPIView, MissingTimesheetView, EmployeeUtilizationView, FinancialDataView, ResourceCountsView, ContractBurndownView
from c2c_modules.invoiceview import create_invoice_view, InvoicesByClientView, UpdateInvoiceView, SendInvoiceView, InvoiceRegenerateAPIView
from c2c_modules.utils import RedirectWithAuthTokenView, RedirectWithRefreshTokenView, RedirectOpenAIView, RedirectChatbotOpenAIView, CheckNameView
from c2c_modules.dashboardview import DashboardAPIView
from c2c_modules.approvalview import ApproveOrRecallTimesheetsView, PendingTimesheetsView,BulkApproveTimesheetsAPIView, TimesheetApproverSearchView, ApprovalPendingListView, ManagerApprovalPendingCountsView, UpdateTimesheetsByManagerView, EmployeeMissingTimesheetAPIView, SubmittedTimesheetsAPIView

urlpatterns = [
    # API routes for Client
    path('client', ClientAPIView.as_view(), name='client-list-create'),
    path('client/<uuid:uuid>', ClientDetailsAPIView.as_view(), name='client-details'),
    path('auto-search/', SearchAPIView.as_view(), name='search-api'),
    path('auto-name-search/', NameSearchAPIView.as_view(), name='search-name-api'),
    path("ratecards/", C2CRateCardConfigAPIView.as_view(), name="ratecard-list"),

    # API routes for Contract Module
    path('contract',ContractPostAPIView.as_view(), name='contract'),
    path('contract/<str:client_id>/', ContractGetAPIView.as_view(), name='contract-api'),
    path('contract/details/<uuid:uuid>/', ContractPatchAPIView.as_view(), name='contract-patch'),
    path('contract/file/list/', FileView.as_view(), name='contract-file-list'),
    path('contract/file-delete/<uuid:file_uuid>/', AzurBlobFileDeleter.as_view(), name='contract-file-delete'),
    path('contract/file-download/<uuid:file_uuid>/', AzurBlobFileDownload.as_view(), name='contract-file-download'),
    path('files/client/<uuid:client_id>/', FileListByClientView.as_view(), name='file-list-by-client'),
    path('files/contract/<uuid:contract_id>/', FileListByContractView.as_view(), name='file-list-by-contract'),

    # API routes for Estimation
    path('estimation',EstimationPostAPIView.as_view(), name='estimation'),
    path('estimation/<str:client>/',EstimationGetAPIView.as_view(), name='estimation'),
    path('estimation/details/<uuid:uuid>',SingleEstimationAPIView.as_view(), name='single_estimation'),

    # API routes for Pricing
    path('pricing', PricingPostAPIView.as_view(), name='pricing-create'),
    path('pricing/<str:client>/', PricingGetAPIView.as_view(), name='pricing-list'),
    path('pricing/details/<uuid:uuid>/', PricingDetailAPIView.as_view(), name='pricing-detail'),

    # API routes for SOW Contract
    path('contractsow/<uuid:client_uuid>/', ContractSowGetAPIView.as_view(), name='contract-sow'),
    path('contractsow/', ContractSowPostAPIView.as_view(), name='contractsow-list'),
    path('contractsow/details/<uuid:uuid>/', ContractSowDetailView.as_view(), name='contractsow-details'),
    path('contractsow-check/', ContractSowDetailCheckView.as_view(), name='contractsow-check'),

    # API routes for Purchase Order
    path('purchase-orders/', PurchaseOrderCreateView.as_view(), name='purchase-order-create'),
    path('purchase-orders/details/<int:pk>/', PurchaseOrderRetrieveUpdateDeleteView.as_view(), name='purchase-order-detail'),
    path('purchase_orders_assign/', UtilizedAmountListCreateAPIView.as_view(), name='utilized_amount-list-create'),
    path('purchase_orders_assign/<int:pk>/', UtilizedAmountRetrieveUpdateDestroyAPIView.as_view(), name='utilized_amount-detail'),
    path('all_purchase_orders/', PurchaseOrderWithUtilizationAPIView.as_view(), name='purchase-order-with-utilization-list'),
    path('purchase_orders_client_all/<uuid:client_id>/', PurchaseOrderClientWithUtilizationAPIView.as_view(), name='purchase-order-client-utilization-list'),
    path('purchase_orders_client_unassigned/<uuid:client_id>/', PurchaseOrderClientWithUnUtilizationAPIView.as_view(), name='purchase-order-client-unutilization-list'),
    path('purchase_orders_by_id/', PurchaseOrderByIdAPIView.as_view(), name='purchase-order-by-id'),
    path('unassigned-sow-contracts/<uuid:client_id>/', UnassignedSowContractsView.as_view(), name='unassigned-sow-contracts'),
    path('purchase-order-check/', CheckPOAccountNumberView.as_view(), name='purchaseorder-account-number-check'),
    path('delete-utilized-amounts/<int:purchase_order_id>/', DeleteUtilizedAmountView.as_view(), name='delete-utilized-amounts'),

    # API routes for Milestone Module
    path('milestones/', MilestonePostAPIView.as_view(), name='milestone-post-api'),
    path('milestones/<str:client_uuid>/', MilestoneGetAPIView.as_view(), name='milestone-get-client-api'),
    path('milestones/details/<uuid:uuid>', MilestoneDetailAPIView.as_view(), name='milestone-detail'),
    path('milestone-check/<uuid:contract_sow_uuid>/',MilestoneDetailCheckView.as_view(), name='milestone-check'),
    path('milestone-name-check/',CheckMilestoneNameView.as_view(), name='milestone-name-check'),

    # API routes for Resource Module
    path('resource/timesheet/', TimesheetOverviewView.as_view(), name='timesheet-overview'),
    path('resource/timesheets/<str:resource_id>/', ResourceTimesheetsView.as_view(), name='resource-timesheets'),
    path('resource-timesheets-by-name/<str:resource_name>/', ResourceTimesheetsByNameView.as_view(), name='resource-timesheets-by-name'),
    path('resource-entry-timesheets/submit/', TimesheetSubmissionAPIView.as_view(), name='timesheet-submit'),
    path('resource-entry-timesheets/', TimesheetRetrieveAPIView.as_view(), name='timesheet-retrieve'),
    path('resource-timesheet/estimation/', TimesheetEstimationView.as_view(), name='timesheet-estimation'),
    path('resource-projects/', EmployeeProjectsView.as_view(), name='employee-project-list'),
    path('resource-manager-view/',AllEmployeeProjectsView.as_view(), name='manager-view'),

    path('skillpayrate',SkillPayRateAPIView.as_view(), name='skillpayrate'),

    # API routes for Allocation
    path('allocation',AllocationAPIView.as_view(), name='allocation'),
    path('allocation/<uuid:client_uuid>/',AllocationClientGetAPIView.as_view(), name='allocation-client'),
    path('allocation/details/<uuid:uuid>/', AllocationDetailView.as_view(), name='allocation-detail'),
    path('allocation/contractsow/client/<uuid:client_uuid>/', SowContractListView.as_view(), name='contracts_by_client'),
    path('allocation/contractsow/<uuid:contractsow_id>/estimation/<uuid:estimation_id>/', EstimationDetailByContractView.as_view(), name='estimation_by_contract'),
    path('check-allocation/<uuid:contract_sow_id>/', CheckAllocationView.as_view(), name='check-allocation'),
    path('name-check/',CheckNameView.as_view(), name='name-check'),

    #API routes for Employee Module
    path('resource-role-counts/', RoleCountsView.as_view(), name='role_counts'),
    path('resource-skill-counts/', SkillCountsView.as_view(), name='skill_counts'),
    path('resource-emptype-country-counts/', EmpTypeCountryCountsView.as_view(), name='emp_type_country_counts'),
    path('resource/search/', EmployeeSearchAPIView.as_view(), name='employee-search'),
    path('get-resources/by-role/', RoleEmployeeListView.as_view(), name='employees_by_role'),
    path('get-resources/by-skill/', SkillEmployeeListView.as_view(), name='employees_by_skill'),
    path('get-resources/by-emptype-country/', EmpTypeCountryEmployeeListView.as_view(), name='employees_by_type_country'),
    
    #API routes for Employee Timesheet Module
    path('employee-timesheets/', EmployeeTimesheetView.as_view(), name='employee-timesheets'),
    path('add-employee-timesheet/', AddTimesheetView.as_view(), name='add-employee-timesheet'),
    path('employee-timesheet-status/',EmployeeTimesheetStatusAPIView.as_view(), name='employee-timesheet-status'),
    path('employee-weekly-status/',ClientTimesheetView.as_view(), name='employee-timesheet-status'),
    path('employee-unplanned-hours/',UnplannedHoursView.as_view(), name='employee-unplanned-hours'),
    path('employee-timeoff-hours/',TimeOffHoursView.as_view(), name='employee-timeoff-hours'),
    path('export-employee-timesheets/',EmployeeHoursView.as_view(), name='export-employee-timesheets'),
    path('download-employee-timesheets/',EmployeeHoursDownloadView.as_view(), name='export-employee-timesheets'),
    path('employees/utilization-by-range/', EmployeeUtilizationView.as_view(), name='get-employee-utilization'),
    path('recall-employee-timesheets/',RecallTimesheetView.as_view(), name='recall-employee-timesheet'),

    #external routes
    path('register/', RedirectWithAuthTokenView.as_view(), name='redirect_with_auth'),
    path('token/refresh/', RedirectWithRefreshTokenView.as_view(), name='redirect_with_auth'),
    path('extract-information/', RedirectOpenAIView.as_view(), name='redirect_with_openai'),
    path('openai-chatbot/<uuid:file_uuid>/', RedirectChatbotOpenAIView.as_view(), name='openai-chatbot'),

    #API routes for Invoice Module
    path('generate-invoice/', create_invoice_view, name='create_invoice_view'),
    path('invoices/client/<uuid:client_id>/', InvoicesByClientView.as_view(), name='invoices-by-client'),
    path('update_invoices/', UpdateInvoiceView.as_view(), name='update_invoices'),
    path('send_invoices/', SendInvoiceView.as_view(), name='send_invoices'),
    path('regenerate-invoice/<str:invoice_id>/', InvoiceRegenerateAPIView.as_view(), name='invoice-regenerate'),

    #API routes for Timesheet Approvals
    path('timesheet-approver-search/',TimesheetApproverSearchView.as_view(), name='timesheet-approver-search'),
    path('timesheet-approval-pending/',ApprovalPendingListView.as_view(), name='timesheet-approval-pending'),
    path('ts-manager-notification-count/',ManagerApprovalPendingCountsView.as_view(), name='manager-pending'),
    path('timesheets/missing-submissions/previous-week/',MissingTimesheetView.as_view(), name='missing-timesheet'),
    path('update-timesheets-by-manager/',UpdateTimesheetsByManagerView.as_view(), name='update-timesheets-by-manager'),
    path('timesheet-approval-pending-hr-manager/',PendingTimesheetsView.as_view(), name='update-unplanned-timeoff-timesheets-by-manager'),
    path('update-timesheets-by-hr-manager/',ApproveOrRecallTimesheetsView.as_view(), name='update-timesheets-by-hr-manager'),
    path('employee-missing-timesheets/',EmployeeMissingTimesheetAPIView.as_view(), name='update-timesheets-by-hr-manager'),
    path('timesheet-admin-list-view/', SubmittedTimesheetsAPIView.as_view(), name='admin-submitted-timesheets'),
    path('timesheet-admin-bulk-approval/',BulkApproveTimesheetsAPIView.as_view(), name='admin-bulk-approve-timesheets'),
    #Dashboard routes
    path('dashboard/', DashboardAPIView.as_view(), name='dashboard-api'),
    path('finance/financial-data/', FinancialDataView.as_view(), name='financial-data'),
    path('projects/resource-counts/', ResourceCountsView.as_view(), name='resource-count'),
    path('contracts/<uuid:contract_id>/burndown/', SowContractAPIView.as_view(), name='contract-burndown'),
    path('contracts-ending-report/', ContractsEndingReportAPIView.as_view(), name='contracts-ending-report'),
]