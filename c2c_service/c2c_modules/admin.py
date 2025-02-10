from django.contrib import admin
from import_export.admin import ImportExportModelAdmin
from c2c_modules.models import Client,Contract, FileModel, Estimation, SkillPayRate, Pricing, PurchaseOrder, Allocation, SowContract, MainMilestone, UtilizedAmount, Invoices


admin.site.register(Contract)
admin.site.register(FileModel)
admin.site.register(Estimation)
admin.site.register(SkillPayRate)
class SkillPayRateAdmin(ImportExportModelAdmin):
    pass
admin.site.register(Pricing)
admin.site.register(PurchaseOrder)
admin.site.register(Allocation)
admin.site.register(SowContract)
admin.site.register(Client)
admin.site.register(MainMilestone)
admin.site.register(UtilizedAmount)
admin.site.register(Invoices)


