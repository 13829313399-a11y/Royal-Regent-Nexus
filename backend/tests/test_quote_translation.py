import re

import pytest

from app.services.quote_translation import translate_quote_descriptions
from app.services.document_translation import DocumentTranslationUnavailableError


def test_manufacturing_terms_keep_polarity_specs_and_do_not_need_model():
    texts = [
        "電池片 0.5x17.0x29.8mm AA標準正負極鐵電池叻片 鐵+琴線 Nickel Plated(2PCS)",
        "電池片 0.5x17.0x29.8mm AA標準負正極鐵電池叻片 鐵+琴線 Nickel Plated(2PCS)",
        "線圈 自繞 55X80mm 24 圈 線徑 0.2mm100uH 1.6g/5.7m (2PCS)",
        "PET镜面 ∮50.0x0.7mm PC 單面電鍍（藍色覆膜面）(2PCS)",
    ]
    def no_model(_):
        pytest.fail("Known manufacturing terms should not load the model")
    result = translate_quote_descriptions(texts, model_dir="unused", translator=no_model)
    assert "Positive-Negative" in result["items"][0]["translation"]
    assert "Negative-Positive" in result["items"][1]["translation"]
    assert not any(row["needs_review"] for row in result["items"])
    for row in result["items"]:
        assert re.findall(r"\d+(?:\.\d+)?",row["source"]) == re.findall(r"\d+(?:\.\d+)?",row["translation"])
        assert "(2PCS)" in row["translation"]


def test_model_receives_only_deduplicated_chinese_fragments():
    calls = []
    def model(texts):
        calls.append(texts)
        return ["Special Process" for _ in texts]
    result = translate_quote_descriptions(["特殊工艺 ABS M2.6 (2PCS)","特殊工艺 PP 0.8mm"],model_dir="unused",translator=model)
    assert calls == [["特殊工艺"]]
    assert result["items"][0]["translation"] == "Special Process ABS M2.6 (2PCS)"
    assert not result["warning"]


def test_unknown_phrases_are_not_split_by_short_dictionary_terms():
    calls=[]
    def model(texts):
        calls.append(texts)
        return ["Surface Treatment"]
    result=translate_quote_descriptions(["表面处理 ABS"],model_dir="unused",translator=model)
    assert calls == [["表面处理"]]
    assert result['items'][0]['translation'] == 'Surface Treatment ABS'


@pytest.mark.parametrize("translation", ["", "Unknown 3mm", "仍是中文", "<script>alert</script>", None])
def test_bad_model_outputs_cannot_erase_chinese_or_invent_specifications(translation):
    result=translate_quote_descriptions(["特殊工艺 0.5mm"],model_dir="unused",translator=lambda _: [translation])
    assert result["items"][0]["needs_review"]
    assert "特殊工艺" in result["items"][0]["translation"]
    assert result["warning"]


def test_missing_engine_still_translates_known_terms_and_preserves_unknown_text():
    def unavailable(_):
        raise DocumentTranslationUnavailableError("no model")
    result=translate_quote_descriptions(["配重塊 4.0mm 特殊工艺"],model_dir="unused",translator=unavailable)
    assert "Counterweight" in result["items"][0]["translation"]
    assert "特殊工艺" in result["items"][0]["translation"]
    assert result["warning"]


@pytest.mark.parametrize("texts", [[],[""],["x"*1001],["x"]*201,["x"*1000]*21])
def test_request_resource_bounds(texts):
    with pytest.raises(ValueError):
        translate_quote_descriptions(texts,model_dir="unused")
