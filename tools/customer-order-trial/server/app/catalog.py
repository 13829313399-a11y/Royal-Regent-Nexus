"""Current public customer entries; historical compatibility routes stay closed."""
FACTORIES = {'huakang-a': '华康A', 'huakang-d': '华康D', 'huaxing': '华兴', 'huadeng': '华登'}
CUSTOMERS = {
 'huakang-a': ('360','green-toys','headstart'),
 'huakang-d': ('index','jazwares','maxx','strottman','ubtech','disney','seasons'),
 'huaxing': ('zuru','buzzbee','dickie','caixing','edu','360','yinhui','seasons','maxx','shushupapa','barter','disney'),
 'huadeng': ('goliath','casdon','jakks','simba','spin'),
}
SPECIAL = {'buzzbee':('BuzzBee',('.xls','.xlsx')), 'dickie':('Dickie',('.pdf',)), 'caixing':('彩星',('.pdf',))}


def profiles(factory):
    from app import order_contract as contract
    result=[]
    for code in CUSTOMERS[factory]:
        if code in SPECIAL:
            name, extensions=SPECIAL[code]
        else:
            spec=contract._get_mapped_customer_spec(code,factory)
            name,extensions=spec.name,spec.po_extensions
        result.append({'code':code,'name':name,'po_extensions':list(extensions),'schedule_extensions':['.xlsx']})
    return result
