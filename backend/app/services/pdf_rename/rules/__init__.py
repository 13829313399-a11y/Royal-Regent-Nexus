from .fixed_region_template import FixedRegionRuleTemplate
from .buzzbee_inspection import BuzzBeeInspectionRule
from .caixing_inspection import CaixingInspectionRule
from .buzzbee_indonesia_invoice import BuzzBeeIndonesiaInvoiceRule
from .shipping_so import ShippingSoRule


CATALOG_RULES = (BuzzBeeInspectionRule(), BuzzBeeIndonesiaInvoiceRule(), CaixingInspectionRule(), ShippingSoRule(), FixedRegionRuleTemplate())

__all__ = ["CATALOG_RULES", "FixedRegionRuleTemplate", "BuzzBeeInspectionRule", "BuzzBeeIndonesiaInvoiceRule", "CaixingInspectionRule", "ShippingSoRule"]
