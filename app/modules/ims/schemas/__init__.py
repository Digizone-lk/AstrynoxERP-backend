from app.modules.ims.schemas.auth import LoginRequest, TokenResponse, RegisterOrgRequest
from app.modules.ims.schemas.user import UserCreate, UserUpdate, UserOut
from app.modules.ims.schemas.organization import OrgOut, OrgUpdate
from app.modules.ims.schemas.client import ClientCreate, ClientUpdate, ClientOut
from app.modules.ims.schemas.product import ProductCreate, ProductUpdate, ProductOut
from app.modules.ims.schemas.client_product import ClientProductAssign, ClientProductOut
from app.modules.ims.schemas.quotation import QuotationCreate, QuotationUpdate, QuotationOut, QuotationDetailOut
from app.modules.ims.schemas.invoice import InvoiceCreate, InvoiceUpdate, InvoiceOut, InvoiceDetailOut
from app.modules.ims.schemas.audit_log import AuditLogOut
from app.modules.ims.schemas.dashboard import DashboardStats
