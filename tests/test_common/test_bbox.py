from stages._common import bbox_from_filename


def test_bbox_from_filename_extracts_four_ints():
    assert bbox_from_filename("imgs/img_mineru_001_10_20_300_400.jpg") == (10, 20, 300, 400)


def test_bbox_from_filename_returns_none_when_pattern_absent():
    assert bbox_from_filename("imgs/plain_image.jpg") is None


def test_bbox_from_filename_handles_uppercase_extension():
    assert bbox_from_filename("imgs/foo_1_2_3_4.PNG") == (1, 2, 3, 4)


def test_bbox_from_filename_ignores_directory_components():
    assert bbox_from_filename("/abs/path/foo/bar_5_6_7_8.jpg") == (5, 6, 7, 8)
