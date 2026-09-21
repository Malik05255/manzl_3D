from app.commands import find_target_room,parse_target_size,resolve_target_size
from app.edits import build_proposals,build_resize_proposals
from app.models import EditRequest,FloorPlan,Point,Quality,Room,Source,Wall


def sample_plan(scale=0.01):
    return FloorPlan(
        id="project-1",
        widthPx=1000,
        heightPx=700,
        metersPerPixel=scale,
        calibrationConfidence=0.9 if scale else None,
        walls=[
            Wall(id="w1",a=Point(x=500,y=100),b=Point(x=500,y=500),thicknessPx=4,confidence=0.9)
        ],
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
                polygon=[Point(x=500,y=100),Point(x=900,y=100),Point(x=900,y=500),Point(x=500,y=500)],
                confidence=0.95,
                areaM2=16,
            ),
        ],
        doors=[],
        windows=[],
        labels=[],
        quality=Quality(overall=0.9,walls=0.9,rooms=0.9,text=0.9,dimensions=0.9,needsCalibration=scale is None,warnings=[]),
        source=Source(fileName="plan.png",mimeType="image/png",page=1),
    )


def room_width(room,scale):
    xs=[point.x for point in room.polygon]
    return (max(xs)-min(xs))*scale


def test_arabic_digits_are_understood():
    assert parse_target_size("عدل غرفة النوم إلى ٥×٥") == (5.0,5.0)


def test_metric_units_around_separator_are_understood():
    assert parse_target_size("خلي غرفة النوم 5 متر في 4 متر") == (5.0,4.0)


def test_named_dimensions_are_understood():
    assert resolve_target_size("خلي عرض غرفة النوم 5 متر وعمقها 4 متر",4.0,4.0) == (5.0,4.0)


def test_relative_width_change_is_understood():
    assert resolve_target_size("زود عرض غرفة النوم متر",4.0,4.0) == (5.0,4.0)
    assert resolve_target_size("نقص عرض غرفة النوم 50 سم",4.0,4.0) == (3.5,4.0)


def test_resize_builds_visible_preview_and_shrinks_neighbor():
    request=EditRequest(project_id="project-1",command="عدل غرفة النوم إلى 5×4",plan=sample_plan())
    response=build_proposals(request)
    assert response.needsClarification is None
    assert response.proposals
    preview=response.proposals[0].previewPlan
    bed=next(room for room in preview.rooms if room.id=="bed")
    hall=next(room for room in preview.rooms if room.id=="hall")
    assert round(room_width(bed,0.01),2)==5.0
    assert round(room_width(hall,0.01),2)==3.0
    assert any("الصالة" in impact.text for impact in response.proposals[0].impacts)
    assert "الصالة" in response.proposals[0].title


def test_relative_resize_builds_preview():
    request=EditRequest(project_id="project-1",command="زود عرض غرفة النوم متر",plan=sample_plan())
    response=build_proposals(request)
    assert response.proposals
    preview=response.proposals[0].previewPlan
    bed=next(room for room in preview.rooms if room.id=="bed")
    assert round(room_width(bed,0.01),2)==5.0


def test_metric_edit_requires_calibration():
    request=EditRequest(project_id="project-1",command="عدل غرفة النوم إلى 5×4",plan=sample_plan(None))
    response=build_proposals(request)
    assert not response.proposals
    assert "مقياس" in (response.needsClarification or "")


def test_generic_room_word_does_not_guess_between_rooms():
    plan=sample_plan()
    plan.rooms.append(Room(
        id="child",
        name="غرفة طفل",
        polygon=[Point(x=100,y=510),Point(x=300,y=510),Point(x=300,y=650),Point(x=100,y=650)],
        confidence=0.9,
        areaM2=2.8,
    ))
    assert find_target_room("عدل الغرفة إلى 5×4",plan.rooms) is None


def test_minor_room_name_typo_is_understood():
    plan=sample_plan()
    target=find_target_room("عدل غرفه النؤم إلى 5×4",plan.rooms)
    assert target is not None
    assert target.id=="bed"


def test_relative_centimeters_take_precedence_over_absolute_width():
    assert resolve_target_size("نقص عرض غرفة النوم 50 سم",4.0,4.0) == (3.5,4.0)


def test_resize_shared_side_updates_all_adjacent_rooms():
    plan=sample_plan()
    plan.rooms=[
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
            polygon=[Point(x=500,y=100),Point(x=900,y=100),Point(x=900,y=300),Point(x=500,y=300)],
            confidence=0.95,
            areaM2=8,
        ),
        Room(
            id="bath",
            name="حمام",
            polygon=[Point(x=500,y=300),Point(x=900,y=300),Point(x=900,y=500),Point(x=500,y=500)],
            confidence=0.95,
            areaM2=8,
        ),
    ]
    response=build_proposals(EditRequest(
        project_id="project-1",
        command="عدل غرفة النوم إلى 5×4",
        plan=plan,
    ))
    assert response.proposals
    preview=response.proposals[0].previewPlan
    hall=next(room for room in preview.rooms if room.id=="hall")
    bath=next(room for room in preview.rooms if room.id=="bath")
    assert round(room_width(hall,0.01),2)==3.0
    assert round(room_width(bath,0.01),2)==3.0
    impact_text=" ".join(item.text for item in response.proposals[0].impacts)
    assert "الصالة" in impact_text
    assert "حمام" in impact_text


def test_bedroom_neighbor_is_not_shrunk_to_unusable_strip():
    plan=sample_plan()
    plan.rooms[1].name="غرفة نوم ثانية"
    request=EditRequest(project_id="project-1",command="عدل غرفة النوم إلى 7×4",plan=plan)
    response=build_proposals(request)
    assert not response.proposals
    assert "لا توجد مساحة" in (response.needsClarification or "")


def test_direct_resize_uses_exact_room_id():
    plan=sample_plan()
    target=next(room for room in plan.rooms if room.id=="bed")
    response=build_resize_proposals(plan,target,5.0,4.0,"تعديل دقيق")
    assert response.proposals
    preview=response.proposals[0].previewPlan
    bed=next(room for room in preview.rooms if room.id=="bed")
    assert round(room_width(bed,0.01),2)==5.0


def test_can_offer_absorbing_aligned_service_room():
    plan=sample_plan()
    plan.rooms=[
        Room(
            id="bed",
            name="غرفة النوم",
            polygon=[Point(x=100,y=100),Point(x=500,y=100),Point(x=500,y=500),Point(x=100,y=500)],
            confidence=0.95,
            areaM2=16,
        ),
        Room(
            id="bath",
            name="حمام",
            polygon=[Point(x=500,y=100),Point(x=600,y=100),Point(x=600,y=500),Point(x=500,y=500)],
            confidence=0.95,
            areaM2=4,
        ),
    ]
    response=build_proposals(EditRequest(
        project_id="project-1",
        command="عدل غرفة النوم إلى 5×4",
        plan=plan,
    ))
    absorb=next((proposal for proposal in response.proposals if proposal.id.startswith("absorb:")),None)
    assert absorb is not None
    assert not any(room.id=="bath" for room in absorb.previewPlan.rooms)
    bed=next(room for room in absorb.previewPlan.rooms if room.id=="bed")
    assert round(room_width(bed,0.01),2)==5.0
    assert any(impact.kind=="room_remove" for impact in absorb.impacts)


def test_explicit_merge_room_command():
    plan=sample_plan()
    plan.rooms=[
        Room(
            id="bed",
            name="غرفة النوم",
            polygon=[Point(x=100,y=100),Point(x=500,y=100),Point(x=500,y=500),Point(x=100,y=500)],
            confidence=.95,
            areaM2=16,
        ),
        Room(
            id="bath",
            name="حمام",
            polygon=[Point(x=500,y=100),Point(x=600,y=100),Point(x=600,y=500),Point(x=500,y=500)],
            confidence=.95,
            areaM2=4,
        ),
    ]
    response=build_proposals(EditRequest(
        project_id="project-1",
        command="احذف حمام وضم مساحته الى غرفة النوم",
        plan=plan,
    ))
    assert response.proposals
    proposal=response.proposals[0]
    assert proposal.id=="merge:bath:into:bed"
    assert not any(room.id=="bath" for room in proposal.previewPlan.rooms)


def test_resize_keeps_perpendicular_wall_junctions_connected():
    plan=sample_plan()
    plan.walls.extend([
        Wall(id="top-left",a=Point(x=100,y=100),b=Point(x=500,y=100),thicknessPx=4,confidence=.9),
        Wall(id="top-right",a=Point(x=500,y=100),b=Point(x=900,y=100),thicknessPx=4,confidence=.9),
    ])
    response=build_proposals(EditRequest(
        project_id="project-1",
        command="عدل غرفة النوم إلى 5×4",
        plan=plan,
    ))
    assert response.proposals
    preview=response.proposals[0].previewPlan
    left=next(wall for wall in preview.walls if wall.id=="top-left")
    right=next(wall for wall in preview.walls if wall.id=="top-right")
    assert left.b.x==600
    assert right.a.x==600


def preference_plan():
    plan=sample_plan()
    plan.widthPx=1300
    plan.rooms=[
        Room(
            id="store",
            name="مخزن",
            polygon=[Point(x=0,y=100),Point(x=300,y=100),Point(x=300,y=500),Point(x=0,y=500)],
            confidence=.95,
            areaM2=12,
        ),
        Room(
            id="bed",
            name="غرفة النوم",
            polygon=[Point(x=300,y=100),Point(x=700,y=100),Point(x=700,y=500),Point(x=300,y=500)],
            confidence=.95,
            areaM2=16,
        ),
        Room(
            id="hall",
            name="الصالة",
            polygon=[Point(x=700,y=100),Point(x=1100,y=100),Point(x=1100,y=500),Point(x=700,y=500)],
            confidence=.95,
            areaM2=16,
        ),
    ]
    plan.walls=[
        Wall(id="left-shared",a=Point(x=300,y=100),b=Point(x=300,y=500),thicknessPx=4,confidence=.9),
        Wall(id="right-shared",a=Point(x=700,y=100),b=Point(x=700,y=500),thicknessPx=4,confidence=.9),
    ]
    return plan


def test_explicit_on_account_of_neighbor_filters_other_directions():
    plan=preference_plan()
    response=build_proposals(EditRequest(
        project_id="project-1",
        command="عدل غرفة النوم إلى 5×4 على حساب الصالة",
        plan=plan,
    ))
    assert response.proposals
    assert all("الصالة" in " ".join(impact.text for impact in proposal.impacts) for proposal in response.proposals)
    assert all("مخزن" not in " ".join(impact.text for impact in proposal.impacts) for proposal in response.proposals)


def test_explicit_do_not_change_neighbor_is_respected():
    plan=preference_plan()
    response=build_proposals(EditRequest(
        project_id="project-1",
        command="عدل غرفة النوم إلى 5×4 بدون تغيير الصالة",
        plan=plan,
    ))
    assert response.proposals
    assert all("الصالة" not in " ".join(impact.text for impact in proposal.impacts) for proposal in response.proposals)
    assert any("مخزن" in " ".join(impact.text for impact in proposal.impacts) for proposal in response.proposals)


def test_action_context_selects_target_when_neighbor_is_also_named():
    plan=preference_plan()
    target=find_target_room("عدل غرفة النوم إلى 5×4 على حساب الصالة",plan.rooms)
    assert target is not None
    assert target.id=="bed"
