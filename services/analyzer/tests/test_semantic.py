from app.models import EditRequest,FloorPlan,Point,Quality,Room,Source
from app.semantic import _canonical_from_payload,_deterministic_understands,_extract_json,_load_providers


def sample_request(command="وسع غرفه النوم شوي"):
    plan=FloorPlan(
        id="p1",
        widthPx=800,
        heightPx=600,
        metersPerPixel=0.01,
        calibrationConfidence=0.9,
        walls=[],
        rooms=[
            Room(
                id="bed",
                name="غرفة النوم",
                polygon=[Point(x=100,y=100),Point(x=500,y=100),Point(x=500,y=500),Point(x=100,y=500)],
                confidence=0.95,
                areaM2=16,
            ),
            Room(
                id="hall",
                name="الصالة",
                polygon=[Point(x=500,y=100),Point(x=750,y=100),Point(x=750,y=500),Point(x=500,y=500)],
                confidence=0.95,
                areaM2=10,
            ),
        ],
        doors=[],
        windows=[],
        labels=[],
        quality=Quality(overall=0.9,walls=0.9,rooms=0.9,text=0.9,dimensions=0.9,needsCalibration=False,warnings=[]),
        source=Source(fileName="p.png",mimeType="image/png",page=1),
    )
    return EditRequest(project_id="p1",command=command,plan=plan)


def test_extract_json_from_model_text():
    payload=_extract_json('result: {"action":"resize_room","target_room":"غرفة النوم","width_m":5,"height_m":4,"needs_clarification":""}')
    assert payload is not None
    assert payload["target_room"]=="غرفة النوم"


def test_semantic_payload_is_converted_to_canonical_command():
    request=sample_request()
    normalized,clarification=_canonical_from_payload({
        "action":"resize_room",
        "target_room":"غرفة النوم",
        "width_m":5,
        "height_m":4,
        "needs_clarification":"",
    },request)
    assert clarification is None
    assert normalized=="عدل غرفة النوم إلى 5×4"


def test_semantic_payload_cannot_invent_room():
    request=sample_request()
    normalized,clarification=_canonical_from_payload({
        "action":"resize_room",
        "target_room":"غرفة غير موجودة",
        "width_m":5,
        "height_m":4,
        "needs_clarification":"",
    },request)
    assert normalized is None
    assert clarification is None


def test_provider_configuration_references_secret_env(monkeypatch):
    monkeypatch.setenv(
        "H_ENGINEER_PROVIDERS_JSON",
        '[{"name":"free-a","base_url":"https://example.invalid/v1","model":"model-a","key_env":"FREE_A_KEY"}]',
    )
    providers=_load_providers()
    assert len(providers)==1
    assert providers[0].key_env=="FREE_A_KEY"


def test_semantic_merge_payload_is_canonicalized():
    request=sample_request("احذف الصالة وضمها لغرفة النوم")
    normalized,clarification=_canonical_from_payload({
        "action":"merge_room",
        "source_room":"الصالة",
        "target_room":"غرفة النوم",
        "needs_clarification":"",
    },request)
    assert clarification is None
    assert normalized=="ادمج الصالة مع غرفة النوم"


def test_explicit_merge_bypasses_external_semantic_provider():
    request=sample_request("احذف الصالة وضمها الى غرفة النوم")
    assert _deterministic_understands(request) is True


def test_selected_room_context_bypasses_provider_for_exact_size():
    request=sample_request("خليها 5×4")
    request.target_room_id="bed"
    assert _deterministic_understands(request) is True


def test_semantic_payload_can_use_selected_room_when_name_is_omitted():
    request=sample_request("كبرها شوي")
    request.target_room_id="bed"
    normalized,clarification=_canonical_from_payload({
        "action":"resize_room",
        "target_room":"",
        "width_m":5,
        "height_m":4,
        "needs_clarification":"",
    },request)
    assert clarification is None
    assert normalized=="عدل غرفة النوم إلى 5×4"


def test_selected_opening_semantic_payload_is_canonicalized():
    request=sample_request("وسعها شوي")
    request.target_opening_id="door-1"
    request.plan.doors=[]
    from app.models import Opening
    request.plan.doors.append(Opening(
        id="door-1",kind="door",wallId=None,
        a=Point(x=100,y=100),b=Point(x=190,y=100),confidence=.9,
    ))
    normalized,clarification=_canonical_from_payload({
        "action":"opening_resize",
        "amount_m":1.1,
        "needs_clarification":"",
    },request)
    assert clarification is None
    assert normalized=="اجعل عرض الفتحة المحددة 1.1 متر"


def test_selected_wall_semantic_payload_is_canonicalized():
    request=sample_request("حركه شوي")
    request.target_wall_id="wall-1"
    from app.models import Wall
    request.plan.walls=[Wall(
        id="wall-1",a=Point(x=100,y=100),b=Point(x=100,y=500),thicknessPx=10,confidence=.9,
    )]
    normalized,clarification=_canonical_from_payload({
        "action":"wall_move",
        "amount_m":0.3,
        "direction":"right",
        "needs_clarification":"",
    },request)
    assert clarification is None
    assert normalized=="حرك الجدار المحدد 0.3 متر يمين"
