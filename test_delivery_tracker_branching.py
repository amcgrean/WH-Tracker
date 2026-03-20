from app.Services.erp_service import ERPService


def test_normalize_branch_system_id_handles_slugs_and_names():
    assert ERPService._normalize_branch_system_id('20gr') == '20GR'
    assert ERPService._normalize_branch_system_id('Grimes') == '20GR'
    assert ERPService._normalize_branch_system_id('25bw') == '25BW'
    assert ERPService._normalize_branch_system_id('Fort Dodge') == '10FD'
    assert ERPService._normalize_branch_system_id('40cv') == '40CV'
    assert ERPService._normalize_branch_system_id('all') is None


def test_expand_branch_filters_keeps_grimes_area_behavior():
    service = ERPService()
    assert service._expand_branch_filters('Grimes Area') == ['20GR', '25BW']
    assert service._expand_branch_filters('20gr,25bw') == ['20GR', '25BW']
