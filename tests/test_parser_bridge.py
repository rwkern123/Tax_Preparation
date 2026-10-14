from preparer.parser_bridge import _CATEGORY_DOC_TYPES


def test_portal_categories_cover_all_shared_form_parsers():
    assert set(_CATEGORY_DOC_TYPES.values()) == {
        "w2",
        "form_1098",
        "form_1098_t",
        "form_1099_nec",
        "form_1099_r",
        "form_1099_g",
        "form_1099_misc",
        "form_1099_q",
        "form_1099_sa",
        "ssa_1099",
        "schedule_c",
        "prior_year_return",
    }


def test_questionnaire_category_aliases_map_to_expected_forms():
    assert _CATEGORY_DOC_TYPES["W2_Taxpayer"] == "w2"
    assert _CATEGORY_DOC_TYPES["W2_Spouse"] == "w2"
    assert _CATEGORY_DOC_TYPES["1099_G_Unemployment"] == "form_1099_g"
    assert _CATEGORY_DOC_TYPES["1099_G_Refund"] == "form_1099_g"
    assert _CATEGORY_DOC_TYPES["HSA_1099SA"] == "form_1099_sa"
