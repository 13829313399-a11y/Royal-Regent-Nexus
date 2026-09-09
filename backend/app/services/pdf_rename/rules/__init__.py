from .fixed_region_template import FixedRegionRuleTemplate
from .buzzbee_inspection import BuzzBeeInspectionRule
from .caixing_inspection import CaixingInspectionRule


CATALOG_RULES = (BuzzBeeInspectionRule(), CaixingInspectionRule(), FixedRegionRuleTemplate())

__all__ = ["CATALOG_RULES", "FixedRegionRuleTemplate", "BuzzBeeInspectionRule", "CaixingInspectionRule"]
