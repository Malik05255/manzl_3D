import cv2
import numpy as np

from app.walls import _collapse_parallel_wall_bands,_estimate_thickness,_merge_axis_lines,_merge_near_collinear_candidates,add_vector_wall_candidates,enrich_walls_with_vector,quarantine_dimension_aligned_walls,rasterize_wall_mask


def test_estimates_filled_horizontal_wall_thickness():
    ink=np.zeros((120,220),dtype=np.uint8)
    cv2.rectangle(ink,(20,50),(200,62),255,-1)
    thickness=_estimate_thickness(ink,(20,56,200,56))
    assert 11<=thickness<=15


def test_estimates_filled_vertical_wall_thickness():
    ink=np.zeros((220,120),dtype=np.uint8)
    cv2.rectangle(ink,(50,20),(62,200),255,-1)
    thickness=_estimate_thickness(ink,(56,20,56,200))
    assert 11<=thickness<=15


def test_vector_evidence_boosts_matching_wall_confidence():
    detected=[{
        "id":"wall-1",
        "a":{"x":50.0,"y":100.0},
        "b":{"x":350.0,"y":100.0},
        "thicknessPx":8.0,
        "confidence":0.80,
    }]
    vectors=[{
        "a":{"x":52.0,"y":101.0},
        "b":{"x":348.0,"y":101.0},
        "widthPx":5.0,
    }]
    enriched=enrich_walls_with_vector(detected,vectors)
    assert enriched[0]["confidence"]>0.90


def test_unrelated_vector_line_does_not_boost_wall_confidence():
    detected=[{
        "id":"wall-1",
        "a":{"x":50.0,"y":100.0},
        "b":{"x":350.0,"y":100.0},
        "thicknessPx":8.0,
        "confidence":0.80,
    }]
    vectors=[{
        "a":{"x":52.0,"y":180.0},
        "b":{"x":348.0,"y":180.0},
        "widthPx":5.0,
    }]
    enriched=enrich_walls_with_vector(detected,vectors)
    assert enriched[0]["confidence"]==0.80


def test_rasterized_canonical_wall_closes_detected_opening_gap():
    base=np.zeros((220,420),dtype=np.uint8)
    cv2.line(base,(20,100),(160,100),255,8)
    cv2.line(base,(260,100),(400,100),255,8)
    walls=[{
        "id":"canonical",
        "a":{"x":20.0,"y":100.0},
        "b":{"x":400.0,"y":100.0},
        "thicknessPx":8.0,
        "confidence":.9,
    }]
    barrier=rasterize_wall_mask(walls,220,420,base)
    assert barrier[100,210]>0
    assert barrier[100,100]>0


def test_rasterized_wall_mask_rejects_wrong_base_shape():
    import pytest
    with pytest.raises(ValueError,match="WALL_MASK_SHAPE"):
        rasterize_wall_mask([],200,300,np.zeros((100,100),dtype=np.uint8))


def test_parallel_pdf_vectors_can_seed_missing_wall():
    vectors=[
        {"a":{"x":100.0,"y":100.0},"b":{"x":500.0,"y":100.0},"widthPx":1.5},
        {"a":{"x":100.0,"y":112.0},"b":{"x":500.0,"y":112.0},"widthPx":1.5},
    ]
    result=add_vector_wall_candidates([],vectors,800,1000)
    assert len(result)==1
    wall=result[0]
    assert wall["id"]=="wall-vector-1"
    assert wall["provenance"]=="pdf-vector"
    assert wall["confidence"]>=.95
    assert wall["a"]["y"]==wall["b"]["y"]==106.0
    assert 12<=wall["thicknessPx"]<=15


def test_single_pdf_vector_line_is_not_promoted_to_wall():
    vectors=[{"a":{"x":100.0,"y":100.0},"b":{"x":500.0,"y":100.0},"widthPx":1.0}]
    assert add_vector_wall_candidates([],vectors,800,1000)==[]


def test_vector_wall_candidate_does_not_duplicate_detected_wall():
    detected=[{
        "id":"wall-1",
        "a":{"x":100.0,"y":106.0},
        "b":{"x":500.0,"y":106.0},
        "thicknessPx":12.0,
        "confidence":.8,
    }]
    vectors=[
        {"a":{"x":100.0,"y":100.0},"b":{"x":500.0,"y":100.0},"widthPx":1.0},
        {"a":{"x":100.0,"y":112.0},"b":{"x":500.0,"y":112.0},"widthPx":1.0},
    ]
    result=add_vector_wall_candidates(detected,vectors,800,1000)
    assert [wall["id"] for wall in result]==["wall-1"]


def test_thick_single_pdf_vector_can_seed_wall():
    vectors=[
        {"a":{"x":100.0,"y":180.0},"b":{"x":700.0,"y":180.0},"widthPx":10.0},
        {"a":{"x":120.0,"y":260.0},"b":{"x":300.0,"y":260.0},"widthPx":1.2},
        {"a":{"x":120.0,"y":300.0},"b":{"x":300.0,"y":300.0},"widthPx":1.2},
    ]
    result=add_vector_wall_candidates([],vectors,900,1200)
    wall=next(item for item in result if item["a"]["y"]==item["b"]["y"]==180.0)
    assert wall["provenance"]=="pdf-vector"
    assert wall["confidence"]>=.90
    assert wall["thicknessPx"]==10.0


def test_ordinary_single_vector_dimension_line_stays_ignored():
    vectors=[
        {"a":{"x":100.0,"y":180.0},"b":{"x":700.0,"y":180.0},"widthPx":1.2},
        {"a":{"x":100.0,"y":260.0},"b":{"x":700.0,"y":260.0},"widthPx":1.2},
    ]
    assert add_vector_wall_candidates([],vectors,900,1200)==[]


def test_parallel_diagonal_pdf_vectors_seed_slanted_wall():
    vectors=[
        {"a":{"x":100.0,"y":100.0},"b":{"x":500.0,"y":400.0},"widthPx":1.5},
        {"a":{"x":91.6,"y":111.2},"b":{"x":491.6,"y":411.2},"widthPx":1.5},
    ]
    result=add_vector_wall_candidates([],vectors,900,1200)
    assert len(result)==1
    wall=result[0]
    assert abs((wall["b"]["x"]-wall["a"]["x"])-(wall["b"]["y"]-wall["a"]["y"])*4/3)<3
    assert wall["provenance"]=="pdf-vector"
    assert wall["confidence"]>=.94


def test_raster_detector_finds_double_line_slanted_wall():
    from app.walls import detect_walls

    ink=np.zeros((500,600),dtype=np.uint8)
    cv2.line(ink,(100,100),(450,350),255,3)
    cv2.line(ink,(92,111),(442,361),255,3)

    walls,_=detect_walls(ink)
    slanted=[
        wall for wall in walls
        if abs(wall["b"]["x"]-wall["a"]["x"])>120
        and abs(wall["b"]["y"]-wall["a"]["y"])>80
    ]
    assert slanted
    assert any(wall["confidence"]>=.85 for wall in slanted)



def test_merges_tiny_slanted_fragments_but_preserves_opening_gap():
    fragments=[
        {
            "a":{"x":100.0,"y":100.0},
            "b":{"x":220.0,"y":190.0},
            "thicknessPx":10.0,
            "confidence":.88,
            "provenance":"opencv",
        },
        {
            "a":{"x":224.0,"y":193.0},
            "b":{"x":350.0,"y":287.5},
            "thicknessPx":10.0,
            "confidence":.90,
            "provenance":"opencv",
        },
    ]
    merged=_merge_near_collinear_candidates(fragments)
    assert len(merged)==1
    assert merged[0]["confidence"]==.9
    assert merged[0]["b"]["x"]>340

    opening_gap=[
        fragments[0],
        {
            "a":{"x":280.0,"y":235.0},
            "b":{"x":410.0,"y":332.5},
            "thicknessPx":10.0,
            "confidence":.9,
            "provenance":"opencv",
        },
    ]
    assert len(_merge_near_collinear_candidates(opening_gap))==2



def test_axis_merge_unions_overlapping_fragments():
    merged=_merge_axis_lines([
        (20,50,180,50),
        (150,52,320,52),
        (40,100,40,220),
        (42,200,42,340),
    ])
    horizontal=[line for line in merged if line[1]==line[3]]
    vertical=[line for line in merged if line[0]==line[2]]
    assert len(horizontal)==1
    assert horizontal[0][0]==20 and horizontal[0][2]==320
    assert 50<=horizontal[0][1]<=52
    assert len(vertical)==1
    assert vertical[0][1]==100 and vertical[0][3]==340
    assert 40<=vertical[0][0]<=42


def test_axis_merge_preserves_opening_sized_gap():
    merged=_merge_axis_lines([
        (20,80,120,80),
        (170,80,300,80),
    ])
    assert len(merged)==2


def test_vector_wall_fragments_union_but_real_gap_stays_open():
    contiguous=[
        {"a":{"x":50.0,"y":100.0},"b":{"x":210.0,"y":100.0},"widthPx":1.0},
        {"a":{"x":50.0,"y":110.0},"b":{"x":210.0,"y":110.0},"widthPx":1.0},
        {"a":{"x":190.0,"y":100.0},"b":{"x":360.0,"y":100.0},"widthPx":1.0},
        {"a":{"x":190.0,"y":110.0},"b":{"x":360.0,"y":110.0},"widthPx":1.0},
    ]
    walls=add_vector_wall_candidates([],contiguous,600,800)
    assert len(walls)==1
    assert min(walls[0]["a"]["x"],walls[0]["b"]["x"])<=51
    assert max(walls[0]["a"]["x"],walls[0]["b"]["x"])>=359

    with_opening=[
        {"a":{"x":50.0,"y":100.0},"b":{"x":150.0,"y":100.0},"widthPx":1.0},
        {"a":{"x":50.0,"y":110.0},"b":{"x":150.0,"y":110.0},"widthPx":1.0},
        {"a":{"x":250.0,"y":100.0},"b":{"x":360.0,"y":100.0},"widthPx":1.0},
        {"a":{"x":250.0,"y":110.0},"b":{"x":360.0,"y":110.0},"widthPx":1.0},
    ]
    walls=add_vector_wall_candidates([],with_opening,600,800)
    assert len(walls)==2



def test_high_resolution_detector_keeps_short_thick_partition():
    from app.walls import detect_walls

    ink=np.zeros((4000,4000),dtype=np.uint8)
    # 150px is shorter than the old ~222px Hough minimum at this resolution.
    cv2.rectangle(ink,(1800,1900),(1950,1910),255,-1)
    walls,_=detect_walls(ink)
    assert any(
        abs(wall["b"]["x"]-wall["a"]["x"])>=120
        and abs(wall["b"]["y"]-wall["a"]["y"])<8
        for wall in walls
    )


def test_high_resolution_detector_rejects_short_thin_annotation_stroke():
    from app.walls import detect_walls

    ink=np.zeros((4000,4000),dtype=np.uint8)
    cv2.line(ink,(1800,1900),(1950,1900),255,1)
    walls,_=detect_walls(ink)
    assert not any(
        abs(wall["b"]["x"]-wall["a"]["x"])>=120
        and abs(((wall["a"]["y"]+wall["b"]["y"])/2)-1900)<10
        for wall in walls
    )



def test_collapses_duplicate_centerlines_inside_one_thick_wall_band():
    ink=np.zeros((220,420),dtype=np.uint8)
    cv2.rectangle(ink,(20,90),(400,110),255,-1)
    collapsed=_collapse_parallel_wall_bands(ink,[
        (20,92,400,92),
        (20,100,400,100),
        (20,108,400,108),
    ])
    assert len(collapsed)==1
    assert 96<=collapsed[0][1]<=104
    assert collapsed[0][0]<=20 and collapsed[0][2]>=400


def test_parallel_wall_band_collapse_does_not_bridge_opening_gap():
    ink=np.zeros((220,420),dtype=np.uint8)
    cv2.rectangle(ink,(20,90),(150,110),255,-1)
    cv2.rectangle(ink,(250,90),(400,110),255,-1)
    collapsed=_collapse_parallel_wall_bands(ink,[
        (20,96,150,96),
        (20,104,150,104),
        (250,96,400,96),
        (250,104,400,104),
    ])
    assert len(collapsed)==2



def test_dimension_aligned_thin_vector_candidate_is_quarantined():
    vectors=[
        {"a":{"x":100.0,"y":100.0},"b":{"x":500.0,"y":100.0},"widthPx":1.0},
        {"a":{"x":100.0,"y":104.0},"b":{"x":500.0,"y":104.0},"widthPx":1.0},
    ]
    labels=[{
        "text":"4.00 m",
        "center":{"x":300.0,"y":84.0},
        "confidence":.96,
        "kind":"dimension",
    }]
    result=add_vector_wall_candidates([],vectors,800,1000,labels=labels)
    assert len(result)==1
    assert result[0]["provenance"]=="pdf-vector"
    assert result[0]["confidence"]<=.64


def test_room_barrier_skips_quarantined_pdf_vector_but_keeps_wall_in_model():
    wall={
        "id":"dimension-like",
        "a":{"x":50.0,"y":100.0},
        "b":{"x":350.0,"y":100.0},
        "thicknessPx":10.0,
        "confidence":.64,
        "provenance":"pdf-vector",
    }
    unrestricted=rasterize_wall_mask([wall],220,420)
    trusted=rasterize_wall_mask(
        [wall],220,420,
        min_pdf_vector_confidence=.70,
    )
    assert unrestricted[100,200]>0
    assert trusted[100,200]==0


def test_high_confidence_pdf_vector_remains_in_trusted_room_barrier():
    wall={
        "id":"wall-vector",
        "a":{"x":50.0,"y":100.0},
        "b":{"x":350.0,"y":100.0},
        "thicknessPx":10.0,
        "confidence":.95,
        "provenance":"pdf-vector",
    }
    trusted=rasterize_wall_mask(
        [wall],220,420,
        min_pdf_vector_confidence=.70,
    )
    assert trusted[100,200]>0



def test_thin_dimension_aligned_raster_wall_is_quarantined():
    walls=[{
        "id":"thin-line",
        "a":{"x":100.0,"y":100.0},
        "b":{"x":500.0,"y":100.0},
        "thicknessPx":2.5,
        "confidence":.80,
        "provenance":"opencv",
    }]
    labels=[{
        "text":"4.00 m",
        "center":{"x":300.0,"y":82.0},
        "confidence":.96,
        "kind":"dimension",
    }]
    quarantined=quarantine_dimension_aligned_walls(walls,labels,800,1000)
    assert quarantined=={"thin-line"}
    assert walls[0]["confidence"]<=.64


def test_thick_wall_near_dimension_label_is_not_quarantined():
    walls=[{
        "id":"real-wall",
        "a":{"x":100.0,"y":100.0},
        "b":{"x":500.0,"y":100.0},
        "thicknessPx":14.0,
        "confidence":.90,
        "provenance":"opencv",
    }]
    labels=[{
        "text":"4.00 m",
        "center":{"x":300.0,"y":82.0},
        "confidence":.96,
        "kind":"dimension",
    }]
    quarantined=quarantine_dimension_aligned_walls(walls,labels,800,1000)
    assert quarantined==set()
    assert walls[0]["confidence"]==.90



def test_thin_pdf_vector_quarantines_wall_even_when_raster_thickness_is_inflated():
    walls=[{
        "id":"inflated-dimension-line",
        "a":{"x":100.0,"y":100.0},
        "b":{"x":500.0,"y":100.0},
        "thicknessPx":20.0,
        "confidence":.93,
        "provenance":"mixed",
    }]
    labels=[{
        "text":"4.00 m",
        "center":{"x":300.0,"y":82.0},
        "confidence":.99,
        "kind":"dimension",
    }]
    vectors=[{
        "a":{"x":100.0,"y":100.0},
        "b":{"x":500.0,"y":100.0},
        "widthPx":2.4,
    }]
    quarantined=quarantine_dimension_aligned_walls(
        walls,labels,800,1000,vector_lines=vectors,
    )
    assert quarantined=={"inflated-dimension-line"}
    assert walls[0]["confidence"]<=.64



def test_thick_vector_wall_near_dimension_text_keeps_high_confidence():
    vectors=[
        {"a":{"x":100.0,"y":180.0},"b":{"x":700.0,"y":180.0},"widthPx":10.0},
        {"a":{"x":120.0,"y":260.0},"b":{"x":300.0,"y":260.0},"widthPx":1.2},
    ]
    labels=[{
        "text":"6.00 m",
        "center":{"x":400.0,"y":160.0},
        "confidence":.98,
        "kind":"dimension",
    }]
    result=add_vector_wall_candidates([],vectors,900,1200,labels=labels)
    wall=next(item for item in result if item["a"]["y"]==item["b"]["y"]==180.0)
    assert wall["confidence"]>=.90
