from drf_yasg.utils import swagger_auto_schema
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin, CreateModelMixin
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from c2c_modules.models import Client, Estimation, Contract, Pricing, PurchaseOrder, Allocation, SowContract, MainMilestone, Invoices, C2CRateCardConfig
from c2c_modules.serializer import ClientSerializer, EstimationSerializer, ContractSerializer, ContractSowSerializer, PricingSerializer, AllocationSerializer, MainMilestoneSerializer, PurchaseOrderWithUtilizationSerializer, Employee, InvoicesClientSerializer, Timesheet, TimesheetSerializer, C2CRateCardConfigSerializer
from c2c_modules.utils import has_permission
from django.db.models import Q
from rest_framework.views import APIView
from django.utils.timezone import now
from django.db.models import Sum
from c2c_modules.resourceview import classify_projects
#   ================================================================
time_lapse = 900
class Pagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000

class ClientAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    queryset = Client.objects.filter(deleted=False).order_by('-client_creation_date')
    serializer_class = ClientSerializer
    lookup_field = 'uuid'
    pagination_class = Pagination

    def get_queryset(self):
        return Client.objects.filter(deleted=False)

    @swagger_auto_schema(tags=["Client"])
    def get(self, request, *args, **kwargs):
        """List of clients"""
        required_roles = ["c2c_skillpayrate_admin","c2c_skillpayrate_viewer","c2c_invoice_admin","c2c_invoice_viewer","c2c_allocation_admin","c2c_allocation_viewer","c2c_po_admin","c2c_po_viewer","c2c_milestone_admin","c2c_milestone_viewer","c2c_sow_admin","c2c_sow_viewer","c2c_pricing_admin","c2c_pricing_viewer","c2c_est_viewer","c2c_est_admin","c2c_viewer","c2c_client_viewer","c2c_client_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"result":result})
            return response
        else:
            return Response({"result":result})

    @swagger_auto_schema(tags=["Client"])
    def post(self, request, *args, **kwargs):
        """Create client"""
        required_roles = ["c2c_client_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            username = result['username']
            request_data = request.data.copy()
            request_data['username_created'] = username
            request_data['username_updated'] = username
            serializer = self.get_serializer(data=request_data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            response = Response(serializer.data, status=status.HTTP_201_CREATED)
            response.data.update({"result": result})
            return response
        else:
            return Response({"result":result})

class ClientDetailsAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Client.objects.all()
    serializer_class = ClientSerializer
    pagination_class = Pagination
    lookup_field = 'uuid'


    @swagger_auto_schema(tags=["Client"])
    def patch(self, request, *args, **kwargs):
        required_roles = ["c2c_client_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            username = result['username']
            instance = self.get_object()
            request_data = request.data.copy()
            request_data['username_updated'] = username
            serializer = self.get_serializer(instance, data=request_data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            data = serializer.data
            data.update({"result": result})
            return Response({"result": data}, status=status.HTTP_200_OK)
        else:
            return Response({"result":result})

    @swagger_auto_schema(tags=["Client"])
    def delete(self, request, *args, **kwargs):
        required_roles = ["c2c_client_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response({"message": "Client deleted successfully","result":result})
        else:
            return Response({"result":result})


class SearchAPIView(APIView):
    def get(self, request):
        search_query = request.GET.get('search_query', '')
        client_id = request.GET.get('client_id', None)
        search_type = request.GET.get('search_type', '')

        if not search_query or not search_type:
            return Response({'error': 'Invalid search query or search type'}, status=status.HTTP_400_BAD_REQUEST)
        if search_type not in ['timesheet', 'client'] and not client_id:
            return Response({'error': 'client_id is mandatory for this search type'}, status=status.HTTP_400_BAD_REQUEST)

        results = []
        if search_type == 'client':
            results = self.search_clients(search_query, client_id)
        elif search_type == 'estimation':
            results = self.search_estimations(search_query, client_id)
        elif search_type == 'contract' :
            results = self.search_contracts(search_query, client_id)
        elif search_type == 'pricing' :
            results = self.search_pricing(search_query, client_id)
        elif search_type == 'contractsow' :
            results = self.search_contractsow(search_query, client_id)
        elif search_type == 'purchase_order' :
            results = self.search_purchase_orders(search_query, client_id)
        elif search_type == 'milestone' :
            results = self.search_milestone(search_query, client_id)
        elif search_type == 'allocation' :
            results = self.search_allocation(search_query, client_id)
        elif search_type == 'timesheet' :
            results = self.search_timesheets(search_query)
        elif search_type == 'invoices' :
            results = self.search_invoices(search_query, client_id)
        return Response({'results': results}, status=status.HTTP_200_OK)

    def search_clients(self, search_query, client_id):
        query = Q(name__icontains=search_query)
        if client_id:
            query &= Q(client_id=client_id)
        records = Client.objects.filter(query)
        serializer = ClientSerializer(records, many=True)
        return serializer.data

    def search_estimations(self, search_query, client_id):
        query = Q(name__icontains=search_query)
        if client_id:
            query &= Q(client__uuid=client_id)
        records = Estimation.objects.filter(query)
        serializer = EstimationSerializer(records, many=True)
        return serializer.data

    def search_contracts(self, search_query, client_id):
        query = Q(name__icontains=search_query)
        if client_id:
            query &= Q(client__uuid=client_id)
        records = Contract.objects.filter(query)
        serializer = ContractSerializer(records, many=True)
        return serializer.data

    def search_pricing(self, search_query, client_id):
        query = Q(name__icontains=search_query)
        if client_id:
            query &= Q(client__uuid=client_id)
        records = Pricing.objects.filter(query)
        serializer = PricingSerializer(records, many=True)
        return serializer.data

    def search_contractsow(self, search_query, client_id):
        query = Q(contractsow_name__icontains=search_query)
        if client_id:
            query &= Q(client__uuid=client_id)
        records = SowContract.objects.filter(query)
        serializer = ContractSowSerializer(records, many=True)
        return serializer.data

    def search_purchase_orders(self, search_query, client_id):
        query = Q(purchase_order_name__icontains=search_query)
        if client_id:
            query &= Q(client__uuid=client_id)

        queryset = PurchaseOrder.objects.prefetch_related('utilized_amounts').all().order_by('id')
        records = queryset.filter(query)
        serializer = PurchaseOrderWithUtilizationSerializer(records, many=True)
        return serializer.data

    def search_milestone(self, search_query, client_id):
        query = Q(name__icontains=search_query)
        if client_id:
            query &= Q(client_uuid__uuid=client_id)
        records = MainMilestone.objects.filter(query)
        serializer = MainMilestoneSerializer(records, many=True)
        return serializer.data

    def search_invoices(self, search_query, client_id):
        query = Q(c2c_invoice_id__icontains=search_query)
        if client_id:
            query &= Q(c2c_client_id__uuid=client_id)
        records = Invoices.objects.filter(query).order_by('c2c_invoice_status')
        serializer = InvoicesClientSerializer(records, many=True)
        return serializer.data

    def search_allocation(self, search_query, client_id):
        query = Q(name__icontains=search_query)
        if client_id:
            query &= Q(client__uuid=client_id)
        records = Allocation.objects.filter(query)
        serializer = AllocationSerializer(records, many=True)
        return serializer.data

    def search_timesheets(self, search_query):
        current_date = now().date()
        try:
            resources = Employee.objects.filter(employee_full_name__icontains=search_query)
            if not resources.exists():
                return Response({'error': 'Resource not found'}, status=status.HTTP_404_NOT_FOUND)
            response_data = []
            for resource in resources:
                timesheets = Timesheet.objects.filter(resource=resource)
                data = self.construct_response_data(resource, timesheets, current_date)
                response_data.append(data)
            return response_data
        except Employee.DoesNotExist:
            return {'error': 'Resource not found'}

    def construct_response_data(self, resource, timesheets, current_date):
        if not timesheets.exists():
            return self.build_empty_timesheet_response(resource)
        total_planned_hours = timesheets.aggregate(Sum('billable_hours'))['billable_hours__sum'] or 0
        ongoing_projects, completed_projects, future_projects, incomplete_projects = classify_projects(timesheets, current_date)

        return self.build_timesheet_response(resource, total_planned_hours, timesheets, ongoing_projects, future_projects, completed_projects, incomplete_projects)

    def build_empty_timesheet_response(self, resource):
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


class NameSearchAPIView(APIView):
    def post(self, request, *args, **kwargs):
        name = request.data.get("name").strip()
        search_type = request.data.get("search_type").strip()

        if not name or not search_type:
            return Response(
                {"error": "Both 'name' and 'search_type' are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        if search_type == "client":
            exists = Client.objects.filter(name=name).exists()
        elif search_type == "contract":
            exists = Contract.objects.filter(name=name).exists()
        else:
            return Response(
                {"error": "Invalid search_type. Use 'client' or 'contract'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        return Response({"exists": exists}, status=status.HTTP_200_OK)
    
class C2CRateCardConfigAPIView(ListModelMixin, GenericAPIView):
    queryset = C2CRateCardConfig.objects.all().order_by('-date_created')
    serializer_class = C2CRateCardConfigSerializer
    pagination_class = Pagination

    def get_queryset(self):
        return C2CRateCardConfig.objects.all()

    @swagger_auto_schema(tags=["C2C Rate Card Configs"])
    def get(self, request, *args, **kwargs):
        """List of C2C Rate Card Configurations"""
        required_roles = ["c2c_estimation_admin", "c2c_pricing_admin", "c2c_super_admin"]
        result = has_permission(request, required_roles)

        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"result": result})
            return response
        else:
            return Response({"result": result}, status=result["status"])