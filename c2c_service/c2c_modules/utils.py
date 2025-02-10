import os
import json
from datetime import datetime, timedelta
import requests
import jwt
from tika import parser
import re
from django.http import JsonResponse
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator
from rest_framework.response import Response
from rest_framework import status
from c2c_modules.models import Client, Contract, Allocation, Estimation, SowContract, PurchaseOrder, MainMilestone, FileModel, Pricing
from c2c_modules.serializer import FileSerializer
from django.core.cache import cache
from azure.storage.blob import BlobServiceClient
from rest_framework.generics import GenericAPIView
from config import AZURE_CONNECTION_STRING, AZURE_CONTAINER_NAME, AUTH_API, OPENAI_API, MPS_DOCUMENT_PARSER_API, PROFILE
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from c2c_modules.tasks import start_invoice_scheduler
from datetime import datetime
from c2c_modules.custom_logger import info, error, warning
import pytz
import portalocker
start_invoice_scheduler()


CACHE_FILE = 'user_roles_cache.json'
CACHE_EXPIRY = timedelta(minutes=10)
REGISTER_CALL = "register/"

def compare_timestamp(unix_timestamp):
    current_timestamp = int(datetime.now().timestamp())
    return current_timestamp - unix_timestamp < 900

def get_user_roles(access_token):
    payload = {"auth_token": access_token}
    try:
        response = requests.post(AUTH_API + REGISTER_CALL, data=payload)
        return response.json().get('user_roles')
    except Exception as e:
        info(f"Error fetching user roles: {e}")
        return []

def load_user_roles_from_cache():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as file:
                portalocker.lock(file, portalocker.LOCK_SH)
                content = file.read().strip()
                portalocker.unlock(file)
                if not content:
                    return []
                return json.loads(content)
        except json.JSONDecodeError:
            print("Warning: Cache file contains invalid JSON. Resetting cache.")
            return reset_cache()
    else:
        return reset_cache()

def reset_cache():
    """ Resets the cache by writing an empty list to the file. """
    
    with open(CACHE_FILE, 'w') as file:
        portalocker.lock(file, portalocker.LOCK_EX)
        json.dump([], file)
        portalocker.unlock(file)
    return []

def save_user_roles_to_cache(cache):
    """Save a new entry to the user roles cache."""
    with open(CACHE_FILE, 'w') as file:
        portalocker.lock(file, portalocker.LOCK_EX)
        json.dump(cache, file, indent=4)
        portalocker.unlock(file)

def clean_expired_entries():
    """
    Remove expired entries from the cache file based on the 'exp' timestamp.
    """
    cache = load_user_roles_from_cache()
    current_timestamp = int(datetime.now().timestamp())
    filtered_cache = [
        entry for entry in cache
        if isinstance(entry, dict) and 'exp' in entry and entry['exp'] > current_timestamp
    ]
    save_user_roles_to_cache(filtered_cache)


def decode_token(access_token):
    """Decode the JWT token without verifying the signature and handle expiration errors."""
    try:
        return jwt.decode(access_token, options={"verify_signature": False}, algorithms=["HS256"])
    except ExpiredSignatureError:
        raise ExpiredSignatureError("Expired access token")
    except InvalidTokenError as e:
        raise ValueError(f"Invalid access token: {str(e)}")

def get_token_from_header(request):
    """Extract the Bearer token from the Authorization header."""
    return request.headers.get('Authorization', '').split('Bearer ')[-1].strip()

def get_user_roles_with_cache(access_token, username):
    """
    Retrieve user roles from the cache or fetch them from the API if not cached or expired.
    """
    clean_expired_entries()
    cache = load_user_roles_from_cache()
    for entry in cache:
        if isinstance(entry, dict) and entry.get('username') == username:
            exp = entry.get('exp')
            current_timestamp = int(datetime.now().timestamp())
            if exp and exp > current_timestamp:
                return entry['user_roles'], entry['username'], entry.get('user_email')
    decoded_token = decode_token(access_token)
    exp = decoded_token.get('exp')
    user_email = decoded_token.get("unique_name")
    user_roles = [role.lower() for role in get_user_roles(access_token)]
    new_entry = {
        'access_token': access_token,
        'user_roles': user_roles,
        'username': username,
        'exp': exp,
        'user_email': user_email
    }
    cache.append(new_entry)
    save_user_roles_to_cache(cache)
    return user_roles, username, user_email

def has_permission(request, required_roles):
    """Check if the user has the required roles based on their JWT token."""
    try:
        if PROFILE != "PROD":
            required_roles = [role + "_demo" for role in required_roles]
        access_token = get_token_from_header(request)
        if not access_token:
            return {'error': 'Access token not provided', "status": 403, "user_roles": [], "username": None}

        try:
            decoded_token = decode_token(access_token)
        except ExpiredSignatureError:
            return {'error': 'Expired access token', "status": 401, "user_roles": [], "username": None}
        except ValueError as e:
            return {'error': 'Invalid access token', "status": 403, "user_roles": [], "username": None, 'message': str(e)}
        except Exception as e:
            return {'error': 'Unexpected error', "status": 500, 'message': str(e)}
        username = decoded_token.get('name')
        user_roles, username, user_email = get_user_roles_with_cache(access_token, username)
        if any(role in user_roles for role in required_roles):
            return {
                'success': 'Valid access token',
                "status": 200,
                "user_roles": user_roles,
                "username": username,
                "user_email": user_email
            }
        else:
            print(f"Access denied for user {username} with roles {user_roles}")
        
        return {
            'error': 'Access Denied',
            "status": 401,
            "user_roles": user_roles,
            "username": username,
            "user_email": user_email
        }

    except Exception as e:
        return {'error': 'Unexpected error', "status": 500, "user_roles": [], "username": None,"user_email": None, 'message': str(e)}


def clean_json_string(json_string):
    if not isinstance(json_string, str):
        return json_string
    json_string = re.sub(r'```json\s*|\s*```', '', json_string)
    cleaned = json_string.replace('\\n', '\n').strip()
    return cleaned

def safe_json_loads(json_string):
    if isinstance(json_string, dict):
        return json_string
    cleaned_string = clean_json_string(json_string)
    try:
        parsed_json = json.loads(cleaned_string)
        if 'sow_details' in parsed_json:
            return parsed_json['sow_details']
        elif 'po_details' in parsed_json:
            return parsed_json['po_details']
        else:
            return parsed_json
    except json.JSONDecodeError:
        pattern = r'"(\w+)":\s*"([^"]*)"'
        matches = re.findall(pattern, cleaned_string)
        return dict(matches)

def count_occurrences(text, terms, case_sensitive_terms):
    count = 0
    for term in terms:
        if term in case_sensitive_terms:
            count += text.count(term)
        else:
            count += text.lower().count(term.lower())
    return count

def extract_text_from_file(file_path):
    raw = parser.from_file(file_path)
    return raw['content']


def extract_document_type(file_path):
    sow_keywords = ["Statement of Work", "SOW"]
    po_keywords = ["Purchase Order", "PO", "P.O"]
    case_sensitive_terms = ["PO", "P.O", "SOW"]

    text = extract_text_from_file(file_path)

    sow_count = count_occurrences(text, sow_keywords, case_sensitive_terms)
    po_count = count_occurrences(text, po_keywords, case_sensitive_terms)

    if sow_count > po_count:
        result = "SOW"
    elif po_count > sow_count:
        result = "PO"
    else:
        result = "Unknown"
    return result

@method_decorator(csrf_exempt, name='dispatch')
class RedirectWithAuthTokenView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON payload'}, status=400)
        auth_token = data.get('auth_token')
        if not auth_token:
            return JsonResponse({'error': 'Authorization token not provided'}, status=400)
        payload = {'auth_token': auth_token}
        try:
            response = requests.post(AUTH_API + REGISTER_CALL, json=payload)
            return JsonResponse(response.json(), status=response.status_code)
        except requests.RequestException as e:
            return JsonResponse({'error': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class RedirectWithRefreshTokenView(View):
    def post(self, request):
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({'error': 'Invalid JSON payload'}, status=400)
        refresh_token = data.get('refresh_token')
        if not refresh_token:
            return JsonResponse({'error': 'Refresh token not provided'}, status=400)
        payload = {'refresh_token': refresh_token}
        try:
            response = requests.post(AUTH_API + "token/refresh/", json=payload)
            return JsonResponse(response.json(), status=response.status_code)
        except requests.RequestException as e:
            return JsonResponse({'error': str(e)}, status=500)

@method_decorator(csrf_exempt, name='dispatch')
class RedirectOpenAIView(View):
    def post(self, request):
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'No file part in the request'}, status=400)

        file_ = request.FILES['file']
        files = {'file': (file_.name, file_.read())}
        try:
            if PROFILE == "PROD":
                response = requests.post(f"{OPENAI_API}upload", files=files)
            else:
                upload_dir = os.path.join('uploaded_files')
                os.makedirs(upload_dir, exist_ok=True)
                file_path = os.path.join(upload_dir, file_.name)
                with open(file_path, 'wb+') as destination:
                    for chunk in file_.chunks():
                        destination.write(chunk)
                document_type = extract_document_type(file_path)
                endpoint_url = f"{MPS_DOCUMENT_PARSER_API}extract-information/?document_type={document_type}"
                response = requests.post(endpoint_url, files=files)
            return JsonResponse(response.json(), status=200)
        except requests.RequestException as e:
            return JsonResponse({'error': str(e)}, status=200)


def upload_file_to_blob(client_id, document_type, document_id, uploaded_files, username):
    uploaded_files_info = list()
    blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
    # Check for existing files with the same client_id, document_id, and document_type
    existing_files = FileModel.objects.filter(
        client_id=client_id,
        document_id=document_id,
        document_type=document_type,
        status='active'
    )

    if existing_files.exists():
        existing_files.update(status='inactive')

    for file in uploaded_files:
        blob_name = f"{file.name}"
        blob_client = blob_service_client.get_blob_client(container=AZURE_CONTAINER_NAME, blob=blob_name)
        try:
            blob_client.upload_blob(file, overwrite=True)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        filedata = {
            "client": client_id,
            "blob_name": blob_name,
            "document_id": document_id,
            "document_type": document_type,
            "username_created": username,
            "username_updated": username,
            "status": "active"
        }
        serializer = FileSerializer(data=filedata)
        if serializer.is_valid():
            serializer.save()
            uploaded_files_info.append(serializer.data)
    return uploaded_files_info



@method_decorator(csrf_exempt, name='dispatch')
class RedirectChatbotOpenAIView(View):
    def post(self, request, file_uuid):
        try:
            query = request.POST.get('query', '')

            blob_service_client = BlobServiceClient.from_connection_string(AZURE_CONNECTION_STRING)
            query_set = FileModel.objects.get(uuid=file_uuid)
            serializer = FileSerializer(query_set)
            data = serializer.data
            blob_name = data["blob_name"]
            file_name = blob_name.split("/")[-1]
            blob_client = blob_service_client.get_blob_client(container=AZURE_CONTAINER_NAME, blob=blob_name)
            download_stream = blob_client.download_blob()
            file_data = download_stream.readall()
            files = {'file': (file_name, file_data, 'application/octet-stream')}
            data = {'query': query}
            try:
                response = requests.post(OPENAI_API + "query_document", files=files, data=data)
                return JsonResponse(response.json(), status=response.status_code)
            except requests.RequestException as e:
                return JsonResponse({'error': str(e)}, status=500)

        except Exception as e:
            return JsonResponse({'error': f"An error occurred: {str(e)}"}, status=500)

class CheckNameView(GenericAPIView):

    def post(self, request, *args, **kwargs):
        name = request.data.get('name', None)
        search_type = request.data.get('search_type', None)
        if name is None:
            return Response({"error": "Name parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        if search_type is None:
            return Response({"error": "search_type parameter is required."}, status=status.HTTP_400_BAD_REQUEST)
        name = name.strip()
        if search_type == 'allocation':
            exists = Allocation.objects.filter(name=name).exists()
        elif search_type == 'client':
            exists = Client.objects.filter(name=name).exists()
        elif search_type == 'estimation':
            exists = Estimation.objects.filter(name=name).exists()
        elif search_type == 'contract_sow':
            exists = SowContract.objects.filter(contractsow_name=name).exists()
        elif search_type == 'contract':
            exists = Contract.objects.filter(name=name).exists()
        elif search_type == 'purchase_order':
            exists = PurchaseOrder.objects.filter(purchase_order_name=name).exists()
        elif search_type == 'pricing':
            exists = Pricing.objects.filter(name=name).exists()
        elif search_type == 'milestone':
            exists = MainMilestone.objects.filter(name=name).exists()
        return Response({"exists": exists}, status=status.HTTP_200_OK)
      
def get_date_from_utc_time(utc_time_str):
    formats = [
        "%Y-%m-%d %H:%M:%S.%f", 
        "%Y-%m-%d %H:%M:%S", 
        "%Y-%m-%dT%H:%M:%S.%fZ",
        "%Y-%m-%dT%H:%M:%SZ"
    ]
    for fmt in formats:
        try:
            utc_datetime = datetime.strptime(utc_time_str, fmt)
            utc_datetime = utc_datetime.replace(tzinfo=pytz.UTC)
            ist_timezone = pytz.timezone('Asia/Kolkata')
            ist_datetime = utc_datetime.astimezone(ist_timezone)
            return ist_datetime.date()
        except ValueError:
            continue
    return None

def check_role(role_name):
    if PROFILE =="DEMO":
        return role_name + "_demo"
    else:
        return role_name

def time_to_hours(time_str):
    if isinstance(time_str, (int, float)):  
        return round(float(time_str), 2)
    if not isinstance(time_str, str) or not time_str.strip():
        return 0.0
    time_str = time_str.strip()
    match = re.match(r"^(\d{1,2}):(\d{2})$", time_str)
    if match:
        hours, minutes = int(match.group(1)), int(match.group(2))
        return round(hours + minutes / 60.0, 2)
    return 0.0
