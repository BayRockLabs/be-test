from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db.models import Sum, Q, F, Count
from django.utils import timezone
from c2c_modules.models import SowContract, PurchaseOrder,MainMilestone, Invoices
from concurrent.futures import ThreadPoolExecutor
class DashboardAPIView(APIView):
    def get(self, request):
        functions = {
            "active_sows": self.get_active_sows,
            "unutilized_purchase_orders": self.get_unutilized_purchase_orders,
            "active_invoices": self.get_active_invoices,
            "pending_allocations": self.get_sow_contracts_with_utilized_amount_but_no_allocation,
            "sow_vs_milestones_comparison": self.get_sow_vs_milestones_comparison,
            "sow_po_status": self.get_sow_po_status
        }

        results = {}
        with ThreadPoolExecutor() as executor:
            future_to_key = {executor.submit(func): key for key, func in functions.items()}
            for future in future_to_key:
                key = future_to_key[future]
                try:
                    results[key] = future.result()
                except Exception as e:
                    results[key] = str(e)
        data = {"dashboard": results}
        return Response(data, status=status.HTTP_200_OK)

    def get_active_sows(self):
        now = timezone.now().date()
        now_str = now.strftime('%Y-%m-%d')
        total_sows = SowContract.objects.all()
        total_sow_count = total_sows.count()
        active_sows = SowContract.objects.filter(
            Q(end_date__gte=now_str) | Q(end_date__isnull=True)
        )
        total_active_sow_amount = active_sows.aggregate(total_amount=Sum('total_contract_amount'))['total_amount'] or 0.0
        active_sow_count = active_sows.count()
        return {
            "active_sow_count": active_sow_count,
            "total_active_sow_amount": total_active_sow_amount,
            "total_sow_count" : total_sow_count
        }

    def get_unutilized_purchase_orders(self):
        unutilized_pos = PurchaseOrder.objects.annotate(
            total_utilized_amount=Sum('utilized_amounts__utilized_amount')
        ).select_related('client')
        unutilized_pos = unutilized_pos.filter(
            Q(total_utilized_amount__lt=F('po_amount')) | Q(total_utilized_amount__isnull=True)
        )
        unutilized_po_count = unutilized_pos.count()
        total_unutilized_po_amount = unutilized_pos.annotate(
            remaining_amount=F('po_amount') - F('total_utilized_amount')
        ).aggregate(total_amount=Sum('remaining_amount'))['total_amount'] or 0.0

        total_po = PurchaseOrder.objects.all()
        total_po_count = total_po.count()

        return {
            "unutilized_po_count": unutilized_po_count,
            "total_unutilized_po_amount": total_unutilized_po_amount,
            "total_po_count": total_po_count
        }

    def get_active_invoices(self):
        active_invoices = Invoices.objects.filter(c2c_invoice_status='Active')
        active_invoice_count = active_invoices.count()
        total_active_invoice_amount = active_invoices.aggregate(total_amount=Sum('c2c_invoice_amount'))['total_amount'] or 0.0
        total_invoices = Invoices.objects.all()
        total_invoices_count = total_invoices.count()
        return {
            "active_invoice_count": active_invoice_count,
            "total_active_invoice_amount": total_active_invoice_amount,
            "total_invoices_count": total_invoices_count
        }


    def get_sow_contracts_with_utilized_amount_but_no_allocation(self):
        sow_contracts_with_utilized_amount = SowContract.objects.filter(
            utilized_amounts__isnull=False
        ).annotate(
            allocation_count=Count('contractsow_allocation')
        ).filter(allocation_count=0)
        pending_allocation_count = sow_contracts_with_utilized_amount.count()
        total_allocation_count = SowContract.objects.annotate(
            allocation_count=Count('contractsow_allocation')
            ).aggregate(total_allocations=Sum('allocation_count'))['total_allocations'] or 0
        return {
            "pending_allocation_count": pending_allocation_count,
            "total_allocation_count": total_allocation_count
        }

    def get_sow_vs_milestones_comparison(self):
        now = timezone.now().date()
        now_str = now.strftime('%Y-%m-%d')
        active_sow_contracts = SowContract.objects.filter(Q(end_date__gte=now_str) | Q(end_date__isnull=True))
        total_active_sow_amount = active_sow_contracts.aggregate(
            total_amount=Sum('total_contract_amount')
        )['total_amount'] or 0.0
        active_sow_ids = active_sow_contracts.values_list('uuid', flat=True)
        total_milestone_amount = MainMilestone.objects.filter(
            contract_sow_uuid__in=active_sow_ids
        ).aggregate(total_amount=Sum('milestone_total_amount'))['total_amount'] or 0.0

        return {
            "total_active_sow_amount": total_active_sow_amount,
            "total_milestone_amount": total_milestone_amount
        }


    def get_sow_po_status(self):
        total_sow_count = SowContract.objects.count()
        sows_with_utilized_amount = SowContract.objects.annotate(
            utilized_count=Count('utilized_amounts')
        ).filter(utilized_count__gt=0).count()

        sows_without_utilized_amount = SowContract.objects.annotate(
            utilized_count=Count('utilized_amounts')
        ).filter(utilized_count=0).count()

        return {
            "total_sow_count": total_sow_count,
            "sows_with_po_attached": sows_with_utilized_amount,
            "sows_with_po_pending": sows_without_utilized_amount
        }
