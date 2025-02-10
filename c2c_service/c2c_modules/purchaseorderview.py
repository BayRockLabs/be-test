from rest_framework.pagination import PageNumberPagination
from drf_yasg.utils import swagger_auto_schema
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin, CreateModelMixin
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status, generics
from rest_framework.views import APIView
from c2c_modules.models import PurchaseOrder, UtilizedAmount, SowContract
from c2c_modules.serializer import PurchaseOrderCreateSerializer, PurchaseOrderSerializer, UtilizedAmountSerializer, PurchaseOrderWithUtilizationSerializer, POSowContractSerializer, ContractSowIdListSerializer
from c2c_modules.utils import has_permission, upload_file_to_blob
from rest_framework.filters import SearchFilter
from django.db.models import Sum, F, ExpressionWrapper, DecimalField, Value
from django.db.models.functions import Coalesce
from decimal import Decimal
from django.db import transaction
#   ================================================================
class Pagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000

class PurchaseOrderCreateView(ListModelMixin,CreateModelMixin, GenericAPIView):
    queryset = PurchaseOrder.objects.all()
    serializer_class = PurchaseOrderCreateSerializer
    lookup_field = 'id'
    pagination_class = Pagination

    @swagger_auto_schema(tags=["Purchase Order"])
    def get(self, request, *args, **kwargs):
        """ list of Purchase Orders """
        required_roles = ["c2c_po_admin","c2c_po_viewer","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"roles_response":result})
            return response
        else:
            return Response({"roles_response":result})

    @swagger_auto_schema(tags=["Purchase Order"])
    def post(self, request, *args, **kwargs):
        """Create Purchase Order"""
        required_roles = ["c2c_po_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            username = result['username']
            request_data = request.data.copy()
            request_data['username_created'] = username
            request_data['username_updated'] = username
            serializer = self.get_serializer(data=request_data)
            serializer.is_valid(raise_exception=True)

            uploaded_file = request.FILES.get('file')
            if not uploaded_file:
                return Response({"error": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST)
            self.perform_create(serializer)
            response_data = serializer.data
            purchaseorder_id = response_data['id']
            client_id = response_data['client']
            uploaded_files = [uploaded_file]
            uploaded_files_info = upload_file_to_blob(client_id,"PO",purchaseorder_id,uploaded_files,username)
            response_data["purchase_order_documents"] = uploaded_files_info
            response_data["roles_response"] = result
            return Response(response_data, status=status.HTTP_201_CREATED)
        else:
            return Response({"roles_response":result})

class PurchaseOrderRetrieveUpdateDeleteView(generics.RetrieveUpdateDestroyAPIView):
    queryset = PurchaseOrder.objects.all().order_by('-po_creation_date')
    serializer_class = PurchaseOrderSerializer

    @swagger_auto_schema(tags=["Purchase Order"])
    def update(self, request, *args, **kwargs):
        required_roles = ["c2c_po_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            username = result['username']
            instance = self.get_object()
            data = request.data
            instance.purchase_order_name =  data.get('purchase_order_name', instance.purchase_order_name)
            instance.account_number =  data.get('account_number', instance.account_number)
            instance.po_amount =  data.get('po_amount', instance.po_amount)
            instance.start_date =  data.get('start_date', instance.start_date)
            instance.end_date =  data.get('end_date', instance.end_date)
            instance.username_updated = username
            instance.save()
            uploaded_files_info = []
            uploaded_file = request.FILES.get('file')
            if uploaded_file:
                uploaded_files = [uploaded_file]
                purchaseorder_id = instance.id
                client_id = instance.client.uuid
                document_type = "PO"
                uploaded_files_info = upload_file_to_blob(client_id, document_type, purchaseorder_id, uploaded_files, username)
            serializer = self.get_serializer(instance)
            response_data = serializer.data
            response_data["purchase_order_documents"] = uploaded_files_info
            response_data["roles_response"] = result

            return Response(response_data, status=status.HTTP_200_OK)
        else:
            return Response({"roles_response": result}, status=status.HTTP_401_UNAUTHORIZED)

class UtilizedAmountListCreateAPIView(generics.ListCreateAPIView):
    queryset = UtilizedAmount.objects.all()
    serializer_class = UtilizedAmountSerializer

    @swagger_auto_schema(tags=["Purchase Orders"])
    def create(self, request, *args, **kwargs):
        required_roles = ["c2c_po_admin","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] != 200:
            return Response({"roles_response": result}, status=status.HTTP_401_UNAUTHORIZED)
        username = result['username']
        data = request.data
        sow_contract = data.get('sow_contract')
        purchase_orders = data.get('purchase_order', [])
        utilized_amounts = []
        try:
            sow_contract = SowContract.objects.get(uuid=sow_contract)
        except SowContract.DoesNotExist:
            return Response({"error": "Sow Contract not found"}, status=status.HTTP_404_NOT_FOUND)
        for order in purchase_orders:
            purchase_order_id = order.get('id')
            utilized_amount_value = Decimal(order.get('utilized_amount', 0))
            try:
                utilized_amount = UtilizedAmount.objects.get(purchase_order=purchase_order_id, sow_contract=sow_contract)
                utilized_amount.utilized_amount = utilized_amount_value
                utilized_amount.username_updated = username
                utilized_amount.save()
            except UtilizedAmount.DoesNotExist:
                utilized_amount = UtilizedAmount.objects.create(purchase_order_id=purchase_order_id,
                                                                sow_contract=sow_contract,
                                                                utilized_amount=utilized_amount_value,
                                                                username_created=username,
                                                                username_updated=username)
            utilized_amounts.append(utilized_amount)
        response_data = {
            "utilized_purchase_orders": UtilizedAmountSerializer(utilized_amounts, many=True).data,
            "roles_response": result
        }
        return Response(response_data, status=status.HTTP_200_OK)

class UtilizedAmountRetrieveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    queryset = UtilizedAmount.objects.all()
    serializer_class = UtilizedAmountSerializer

    @swagger_auto_schema(tags=["Purchase Orders"])
    def update(self, request, *args, **kwargs):
        required_roles = ["c2c_po_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            username = result['username']
            instance = self.get_object()
            data = request.data
            instance.utilized_amount = data.get('utilized_amount', instance.utilized_amount)
            instance.username_updated = username
            instance.save()
            serialized_data = UtilizedAmountSerializer(instance).data
            serialized_data["roles_response"] = result
            return Response(serialized_data, status=status.HTTP_200_OK)
        else:
            return Response({"roles_response":result})

class PurchaseOrderWithUtilizationAPIView(generics.ListAPIView):
    serializer_class = PurchaseOrderWithUtilizationSerializer
    pagination_class = Pagination

    def get_queryset(self):
        queryset = PurchaseOrder.objects.prefetch_related('utilized_amounts').all().order_by('id')
        return queryset

    @swagger_auto_schema(tags=["Purchase Orders"])
    def get(self, request,*args, **kwargs):
        required_roles = ["c2c_po_admin","c2c_po_viewer","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"roles_response": result})
            return response
        else:
            return Response({"roles_response": result})

class PurchaseOrderClientWithUtilizationAPIView(generics.ListAPIView,ListModelMixin):
    pagination_class = Pagination
    serializer_class = PurchaseOrderWithUtilizationSerializer
    filter_backends = [SearchFilter]
    search_fields = ['client']

    def get_queryset(self):
        client_id = self.kwargs['client_id']
        queryset = PurchaseOrder.objects.prefetch_related('utilized_amounts').all().order_by('id')
        if client_id is not None:
            queryset = queryset.filter(client=client_id)
        return queryset

    @swagger_auto_schema(tags=["Purchase Orders"])
    def get(self, request, client_id, *args, **kwargs):
        required_roles = ["c2c_po_admin","c2c_po_viewer","c2c_viewer","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"roles_response": result})
            return response
        else:
            return Response({"roles_response": result})

class PurchaseOrderClientWithUnUtilizationAPIView(generics.ListAPIView):
    serializer_class = PurchaseOrderWithUtilizationSerializer
    filter_backends = [SearchFilter]
    search_fields = ['client']

    def get_queryset(self):
        client_id = self.kwargs['client_id']
        queryset = PurchaseOrder.objects.prefetch_related('utilized_amounts').annotate(
                        total_utilized_amount=Coalesce(Sum('utilized_amounts__utilized_amount'), Value(0), output_field=DecimalField())
                    ).annotate(
                        remaining_amount=ExpressionWrapper(
                            F('po_amount') - F('total_utilized_amount'),
                            output_field=DecimalField()
                        )
                    ).filter(remaining_amount__gt=0.0)

        if client_id is not None:
            queryset = queryset.filter(client=client_id)
        return queryset

    @swagger_auto_schema(tags=["Purchase Orders"])
    def get(self, request, client_id, *args, **kwargs):
        required_roles = ["c2c_po_admin","c2c_po_viewer","c2c_viewer","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            data = dict()
            response = self.list(request, *args, **kwargs)
            data['result'] = response.data
            data.update({"roles_response": result})
            return Response(data)
        else:
            return Response({"roles_response": result})

class PurchaseOrderByIdAPIView(generics.ListAPIView):
    serializer_class = PurchaseOrderWithUtilizationSerializer

    def get_queryset(self):
        purchase_order_id = self.request.query_params.get('purchase_order', None)
        if purchase_order_id is not None:
            return PurchaseOrder.objects.prefetch_related('utilized_amounts').filter(id=purchase_order_id)
        return PurchaseOrder.objects.none()

    @swagger_auto_schema(tags=["Purchase Orders"])
    def get(self, request,*args, **kwargs):
        response = self.list(request, *args, **kwargs)
        return Response(response.data[0])

class UnassignedSowContractsView(generics.ListAPIView):
    serializer_class = POSowContractSerializer

    def get_queryset(self):
        client_id = self.kwargs['client_id']
        assigned_contracts_ids = UtilizedAmount.objects.values_list('sow_contract_id', flat=True).distinct()
        unassigned_sow_contracts = SowContract.objects.filter(
            client=client_id
        ).exclude(uuid__in=list(assigned_contracts_ids))
        return unassigned_sow_contracts

    @swagger_auto_schema(tags=["Purchase Orders"])
    def get(self, request,*args, **kwargs):
        required_roles = ["c2c_po_admin","c2c_po_viewer","c2c_viewer","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            data = dict()
            response = self.list(request, *args, **kwargs)
            data['result'] = response.data
            data.update({"roles_response": result})
            return Response(data)
        else:
            return Response({"roles_response": result})


class CheckPOAccountNumberView(GenericAPIView):
    queryset = PurchaseOrder.objects.all()

    def post(self, request, *args, **kwargs):
        account_number = request.data.get('account_number', None)
        if account_number is None:
            return Response({"error": "account_number parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        account_number = account_number.strip()
        exists = PurchaseOrder.objects.filter(account_number=account_number).exists()
        return Response({"exists": exists}, status=status.HTTP_200_OK)


class DeleteUtilizedAmountView(APIView):
    def post(self, request, purchase_order_id, *args, **kwargs):
        required_roles = ["c2c_po_admin","c2c_po_admin","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            serializer = ContractSowIdListSerializer(data=request.data)
            if serializer.is_valid():
                contractsow_ids = serializer.validated_data['contractsow_ids']
                try:
                    with transaction.atomic():
                        deleted_count, _ = UtilizedAmount.objects.filter(
                            sow_contract__in=contractsow_ids,
                            purchase_order_id=purchase_order_id
                        ).delete()
                    return Response({"detail": f"Records deleted successfully.{deleted_count}"}, status=status.HTTP_200_OK)
                except Exception as e:
                    return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        else:
            return Response({"roles_response": result})