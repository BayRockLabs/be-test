from config import AZURE_CONNECTION_STRING, AZURE_CONTAINER_NAME
from drf_yasg.utils import swagger_auto_schema
from django.utils.dateparse import parse_date
from rest_framework.generics import GenericAPIView
from rest_framework.mixins import ListModelMixin, CreateModelMixin
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework import status
from django.http import HttpResponse, JsonResponse
from c2c_modules.models import Contract, FileModel
from c2c_modules.serializer import ContractSerializer, ContractCreateSerializer, ContractUpdateSerializer, FileSerializer
from azure.storage.blob import BlobServiceClient
from rest_framework.generics import RetrieveUpdateDestroyAPIView
from rest_framework.parsers import MultiPartParser, FormParser
from c2c_modules.utils import has_permission, upload_file_to_blob
from rest_framework import generics
from django_filters.rest_framework import DjangoFilterBackend
from datetime import datetime
#   ================================================================
class Pagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 1000
class ContractGetAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    queryset = Contract.objects.all()
    serializer_class = ContractSerializer
    pagination_class = Pagination
    lookup_field = 'uuid'

    @swagger_auto_schema(tags=["Contract"])
    def get(self, request, client_id, *args, **kwargs):
        required_roles = ["c2c_viewer","mps_c2c_admin","mps_c2c_contract_admin","mps_c2c_contract_view","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            contract_creation_date_str = request.query_params.get('contract_creation_date')
            contract_creation_date = parse_date(contract_creation_date_str) if contract_creation_date_str else None
            queryset = self.get_queryset()

            if contract_creation_date:
                queryset = queryset.filter(contract_creation_date__gte=contract_creation_date)

            if client_id:
                queryset = queryset.filter(client=client_id)
            queryset = queryset.order_by('-contract_creation_date')
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

class ContractPostAPIView(ListModelMixin, CreateModelMixin, GenericAPIView):
    queryset = Contract.objects.all()
    serializer_class = ContractCreateSerializer
    pagination_class = Pagination
    lookup_field = 'uuid'
    parser_classes = (MultiPartParser, FormParser)

    def get_serializer_class(self):
        if self.request.method == "POST":
            return ContractCreateSerializer
        return super().get_serializer_class()

    @swagger_auto_schema(tags=["Contract"])
    def post(self, request, *args, **kwargs):
        required_roles = ["mps_c2c_admin","mps_c2c_contract_admin","c2c_super_admin","c2c_client_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            uploaded_files_info = []
            username = result['username']
            request_data = request.data.copy()
            request_data['username_created'] = username
            request_data['username_updated'] = username
            start_date = request_data.get("start_date")
            end_date = request_data.get("end_date")
            if start_date:
                try:
                    start_date_obj = datetime.strptime(start_date.split("T")[0], "%Y-%m-%d")
                except ValueError:
                    return Response({"error": "Invalid start_date format. Use 'YYYY-MM-DDTHH:MM:SS.sssZ'."}, 
                                    status=status.HTTP_400_BAD_REQUEST)
                if end_date:
                    try:
                        end_date_obj = datetime.strptime(end_date.split("T")[0], "%Y-%m-%d")
                    except ValueError:
                        return Response({"error": "Invalid end_date format. Use 'YYYY-MM-DDTHH:MM:SS.sssZ'."}, 
                                        status=status.HTTP_400_BAD_REQUEST)
                    if end_date_obj <= start_date_obj:
                        return Response({"error": "end_date must be greater than start_date."}, 
                                        status=status.HTTP_400_BAD_REQUEST)
            serializer = self.get_serializer(data=request_data)
            serializer.is_valid(raise_exception=True)
            self.perform_create(serializer)
            response_data = serializer.data
            client_id = response_data['client']
            uploaded_files = request.FILES.getlist('file')
            if not uploaded_files:
                uploaded_file = request.FILES.get('file')
                if uploaded_file:
                    uploaded_files = [uploaded_file]
            if uploaded_files:
                document_id=response_data['uuid']
                document_type = "CLIENT"
                uploaded_files_info = upload_file_to_blob(client_id,document_type,document_id,uploaded_files,username)
            response_data["files"] = uploaded_files_info
            response_data["result"] = result
            return Response(response_data, status=status.HTTP_200_OK)
        else:
            return Response({"result":result})

    @swagger_auto_schema(tags=["Contract"])
    def get(self, request, *args, **kwargs):
        """List of contracts"""
        required_roles = ["mps_c2c_admin","mps_c2c_contract_admin","mps_c2c_contract_view","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"result":result})
            return response
        else:
            return Response({"result":result})
class ContractPatchAPIView(RetrieveUpdateDestroyAPIView):
    queryset = Contract.objects.all()
    serializer_class = ContractUpdateSerializer
    pagination_class = Pagination
    lookup_field = 'uuid'

    def get_object(self):
        try:
            return Contract.objects.get(uuid=self.kwargs['uuid'])
        except Contract.DoesNotExist:
            return None

    @swagger_auto_schema(tags=["Contract"])
    def get(self, request, uuid, *args, **kwargs):
        required_roles = ["c2c_viewer","mps_c2c_admin","mps_c2c_contract_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            instance = self.get_object()
            if instance is None:
                return Response({'detail': 'Contract not found.'}, status=status.HTTP_404_NOT_FOUND)
            serializer = self.get_serializer(instance)
            data = serializer.data
            data.update({"result":result})
            return Response(data, status=status.HTTP_200_OK)
        else:
            return Response({"result":result})

    @swagger_auto_schema(tags=["Contract"])
    def patch(self, request, uuid, *args, **kwargs):
        required_roles = ["mps_c2c_admin", "mps_c2c_contract_admin","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            username = result['username']
            try:
                instance = self.get_object()
                if instance is None:
                    return Response({'detail': 'Contract not found.'}, status=status.HTTP_404_NOT_FOUND)
                request_data = request.data.copy()
                request_data['username_updated'] = username
                serializer = self.get_serializer(instance, data=request_data, partial=True)
                serializer.is_valid(raise_exception=True)
                self.perform_update(serializer)
                response_data = serializer.data
                uploaded_files_info = []
                client_id = response_data['client']
                uploaded_files = request.FILES.getlist('file')
                if not uploaded_files:
                    uploaded_file = request.FILES.get('file')
                    if uploaded_file:
                        uploaded_files = [uploaded_file]
                if uploaded_files:
                    document_id = response_data['uuid']
                    document_type = "CLIENT"
                    uploaded_files_info = upload_file_to_blob(client_id, document_type, document_id, uploaded_files, username)
                response_data["files"] = uploaded_files_info
                response_data["result"] = result
                return Response(response_data, status=status.HTTP_200_OK)
            except Exception as e:
                return Response({"error": str(e), "details": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"result": result})

    @swagger_auto_schema(tags=["Contract"])
    def delete(self, request, uuid, *args, **kwargs):
        required_roles = ["mps_c2c_admin","mps_c2c_contract_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            instance = self.get_object()
            self.perform_destroy(instance)
            return Response({"message": "Contract deleted successfully","result":result})
        else:
            return Response({"result":result})

class FileView(ListModelMixin, GenericAPIView):
    serializer_class = FileSerializer
    lookup_field = 'uuid'
    pagination_class = Pagination
    filter_backends = [DjangoFilterBackend]

    def get_queryset(self):
        return FileModel.objects.filter(status='active').order_by('uuid')

    @swagger_auto_schema(tags=["Contract"])
    def get(self, request, *args, **kwargs):
        """List of Files"""
        required_roles = ["mps_c2c_admin","mps_c2c_contract_admin","mps_c2c_contract_view","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            response = self.list(request, *args, **kwargs)
            response.data.update({"result":result})
            return response
        else:
            return Response({"result":result})

class AzurBlobFileDownload(APIView):
    queryset = FileModel.objects.filter(status='active').order_by('uuid')
    serializer_class = FileSerializer
    lookup_field = 'uuid'
    pagination_class = Pagination

    @swagger_auto_schema(tags=["Contract"])
    def get(self, request, file_uuid):
        required_roles = ["mps_c2c_admin","mps_c2c_contract_admin","c2c_super_admin"]
        result = has_permission(request,required_roles)
        if result["status"] == 200:
            try:
                blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
                query_set = FileModel.objects.get(uuid=file_uuid)
                serializer = FileSerializer(query_set)
                data = serializer.data
                file_name = data["blob_name"]
                blob_client = blob_service_client.get_blob_client(container=AZURE_CONTAINER_NAME, blob=data["blob_name"])
                download_stream = blob_client.download_blob()
                file_data = download_stream.readall()
                response = HttpResponse(content_type='application/octet-stream')
                response['Content-Disposition'] = f'attachment; filename="{file_name}"'
                response.write(file_data)
                response = HttpResponse(file_data, content_type='application/octet-stream')
                response['Content-Disposition'] = f'attachment; filename="{file_name}"'
                return response
            except Exception as e:
                print(str(e))
                return Response(data={'status': str(e),"result":result}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        else:
            return Response({"result":result})
class AzurBlobFileDeleter(APIView):
    @swagger_auto_schema(tags=["Contract"])
    def post(self, request, file_uuid):
        required_roles = ["mps_c2c_admin", "mps_c2c_contract_admin","c2c_super_admin"]
        result = has_permission(request, required_roles)
        if result["status"] == 200:
            try:
                query_set = FileModel.objects.get(uuid=file_uuid)
                serializer = FileSerializer(query_set)
                data = serializer.data
                if data["blob_name"]:
                    file_name = data["blob_name"]
                    query_set.status = 'inactive'
                    query_set.save(update_fields=['status'])
                    updated_file_info = {
                        'file_uuid': file_uuid,
                        'file_name': file_name,
                        'blob_name': data["blob_name"],
                        'status': 'inactive'
                    }
                    return JsonResponse({"message": "success", "result": result, "updated_file": updated_file_info, "status": True}, status=200)
                else:
                    return JsonResponse({"message": "blob_name is Null", "result": result, "status": False}, status=200)
            except Exception as error:
                return JsonResponse({"message": str(error), "result": result, "status": False}, status=500)
        else:
            return Response({"result": result})

class FileListByClientView(generics.ListAPIView):
    serializer_class = FileSerializer

    def get_queryset(self):
        client_id = self.kwargs['client_id']
        return FileModel.objects.filter(client_id=client_id).order_by('uuid')

class FileListByContractView(generics.ListAPIView):
    serializer_class = FileSerializer

    def get_queryset(self):
        contract_id = self.kwargs['contract_id']
        return FileModel.objects.filter(contract_id=contract_id).order_by('uuid')