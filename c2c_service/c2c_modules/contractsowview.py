from drf_yasg.utils import swagger_auto_schema
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin, CreateModelMixin
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework import status
from c2c_modules.models import SowContract
from c2c_modules.serializer import ContractSowSerializer, ContractSowCreateSerializer, ContractSowUpdateSerializer
from rest_framework.generics import RetrieveUpdateDestroyAPIView
from c2c_modules.utils import has_permission, upload_file_to_blob
from rest_framework.parsers import MultiPartParser, FormParser
from datetime import datetime
#   ================================================================
class Pagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 1000
class ContractSowGetAPIView(ListModelMixin, GenericAPIView):
    queryset = SowContract.objects.all()
    serializer_class = ContractSowSerializer
    pagination_class = Pagination
    lookup_field = 'uuid'

    @swagger_auto_schema(tags=["Contract Sow"])
    def get(self, request, client_uuid, *args, **kwargs):
        required_roles = ["c2c_po_admin","c2c_sow_admin","c2c_sow_viewer","c2c_viewer","c2c_super_admin","c2c_milestone_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            queryset = self.get_queryset().filter(client=client_uuid)
            queryset = queryset.order_by('-contractsow_creation_date')
            page = self.paginate_queryset(queryset)
            if page is not None:
                serializer = self.get_serializer(page, many=True)
                return self.get_paginated_response(serializer.data)
            serializer_class = self.get_serializer_class()
            serializer = serializer_class(queryset, many=True)
            data = serializer.data
            data.update({"result":result})
            return Response(data, status=status.HTTP_200_OK)
        else:
            return Response({"result":result})


class ContractSowPostAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    queryset = SowContract.objects.all()
    serializer_class = ContractSowCreateSerializer
    pagination_class = Pagination
    lookup_field = 'uuid'
    parser_classes = (MultiPartParser, FormParser)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ContractSowCreateSerializer
        return super().get_serializer_class()

    @swagger_auto_schema(tags=["Contract Sow"])
    def get(self, request, *args, **kwargs):
        """List of contract sow"""
        required_roles = ["c2c_sow_admin","c2c_sow_viewer","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"result":result})
            return response
        else:
            return Response({"result":result})

    @swagger_auto_schema(tags=["Contract Sow"])
    def post(self, request, *args, **kwargs):
        required_roles = ["c2c_sow_admin","c2c_super_admin","c2c_client_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            username = result['username']
            request_data = request.data.copy()
            request_data['username_created'] = username
            request_data['username_updated'] = username
            start_date = request_data.get("start_date")
            end_date = request_data.get("end_date")
            if start_date:
                try:
                    start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
                except ValueError:
                    return Response({"error": "Invalid start_date format. Use 'YYYY-MM-DD'."}, 
                                    status=status.HTTP_400_BAD_REQUEST)
                if end_date:
                    try:
                        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
                    except ValueError:
                        return Response({"error": "Invalid end_date format. Use 'YYYY-MM-DD'."}, 
                                        status=status.HTTP_400_BAD_REQUEST)
                    if end_date_obj <= start_date_obj:
                        return Response({"error": "end_date must be greater than start_date."}, 
                                        status=status.HTTP_400_BAD_REQUEST)
            serializer = self.get_serializer(data=request_data)
            serializer.is_valid(raise_exception=True)
            uploaded_file = request.FILES.get('file')
            if not uploaded_file:
                return Response({"error": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST)
            self.perform_create(serializer)
            data = serializer.data
            contractsow_id = data['uuid']
            client_id = data['client']
            uploaded_files = [uploaded_file]
            uploaded_files_info = upload_file_to_blob(client_id,"SOW",contractsow_id,uploaded_files,username)
            data["document"] = uploaded_files_info
            data["result"] = result
            return Response(data, status=status.HTTP_201_CREATED)
        else:
            return Response({"result":result})

class ContractSowDetailView(RetrieveUpdateDestroyAPIView):
    queryset = SowContract.objects.all()
    serializer_class = ContractSowUpdateSerializer
    pagination_class = Pagination
    lookup_field = 'uuid'

    def get_object(self):
        try:
            return SowContract.objects.get(uuid=self.kwargs['uuid'])
        except SowContract.DoesNotExist:
            return None

    @swagger_auto_schema(tags=["Contract Sow"])
    def get(self, request, uuid, *args, **kwargs):
        required_roles = ["c2c_sow_admin","c2c_sow_viewer","c2c_viewer","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            instance = self.get_object()
            if instance is None:
                return Response({'detail': 'Contract not found.'}, status=status.HTTP_404_NOT_FOUND)
            serializer = self.get_serializer(instance)
            data = serializer.data
            data.update({"result":result})
            return Response(data, status=status.HTTP_201_CREATED)
        else:
            return Response({"result":result})

    @swagger_auto_schema(tags=["Contract Sow"])
    def patch(self, request, uuid, *args, **kwargs):
        required_roles = ["c2c_sow_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            username = result['username']
            instance = self.get_object()
            if instance is None:
                return Response({'detail': 'Contract not found.'}, status=status.HTTP_404_NOT_FOUND)
            request_data = request.data.copy()
            request_data['username_updated'] = username
            serializer = self.get_serializer(instance, data=request_data, partial=True)
            serializer.is_valid(raise_exception=True)
            self.perform_update(serializer)
            response_data = serializer.data
            client_id = instance.client.uuid
            contractsow_id = response_data['uuid']
            uploaded_files_info = []
            uploaded_file = request.FILES.get('file')
            if uploaded_file:
                uploaded_files = [uploaded_file]
                uploaded_files_info = upload_file_to_blob(client_id, "SOW", contractsow_id, uploaded_files, username)
                response_data["document"] = uploaded_files_info
            response_data.update({"result": result})
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            return Response({"result":result})

    @swagger_auto_schema(tags=["Contract Sow"])
    def delete(self, request, uuid, *args, **kwargs):
        required_roles = ["c2c_sow_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response({"message": "contractsow deleted successfully","result":result})
        else:
            return Response({"result":result})

class ContractSowDetailCheckView(GenericAPIView):
    def post(self, request):
        estimation_id = request.data.get('estimation_id')
        pricing_id = request.data.get('pricing_id')
        
        if not estimation_id or not pricing_id:
            return Response({'error': 'Both estimation_id and pricing_id are required.'}, status=400)
        
        exists = SowContract.objects.filter(estimation_id=estimation_id, pricing_id=pricing_id).exists()
        
        try:
            contract_sow = SowContract.objects.get(estimation_id=estimation_id, pricing_id=pricing_id)
            serializer_data = ContractSowSerializer(contract_sow)
            return Response({'exists': exists, 'data': serializer_data.data})
        except SowContract.DoesNotExist:
            return Response({'exists': exists, 'data': {}})