"""Composed ERPService — domain logic lives in mixins, base infrastructure in base.py."""
from app.Services.erp.base import ERPServiceBase
from app.Services.erp.picks import PicksMixin
from app.Services.erp.work_orders import WorkOrdersMixin
from app.Services.erp.orders import OrdersMixin
from app.Services.erp.dispatch import DispatchMixin
from app.Services.erp.delivery import DeliveryMixin
from app.Services.erp.sales import SalesMixin
from app.Services.erp.customers import CustomersMixin


class ERPService(
    ERPServiceBase,
    PicksMixin,
    WorkOrdersMixin,
    OrdersMixin,
    DispatchMixin,
    DeliveryMixin,
    SalesMixin,
    CustomersMixin,
):
    """Composed ERP service — domain logic lives in mixins."""
    pass
