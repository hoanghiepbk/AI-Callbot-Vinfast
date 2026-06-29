from callbot.normalization.vietnamese_numbers import VietnameseNormalizer, normalize_field

normalizer = VietnameseNormalizer()


def value(name: str, raw: str) -> str | None:
    result = normalizer.normalize_field(name, raw)
    assert result.parse_failed is False
    return result.value


def test_phone_spoken_digits() -> None:
    assert value("phone", "khong chin mot hai ba bon nam sau bay tam") == "0912345678"


def test_owner_phone_with_linh_and_digits() -> None:
    assert value("owner_phone", "khong tam tam nam khong hai ba bon sau bay") == "0885023467"


def test_order_phone_mixed_text() -> None:
    assert value("order_phone", "so em la 0987 654 321") == "0987654321"


def test_short_phone_parse_fails() -> None:
    result = normalize_field("phone", "khong chin mot")
    assert result.value == "091"
    assert result.parse_failed is True


def test_vietnamese_plate_with_dots() -> None:
    assert value("license_plate_vin", "ba muoi a cham nam sau bay cham tam chin") == "30A-567.89"


def test_vietnamese_plate_with_hyphen_words() -> None:
    assert value("license_plate_vin", "nam mot f gach mot hai ba bon nam") == "51F-12345"


def test_split_plate_after_buffer_join_parse_passes() -> None:
    joined = "30F 1234"
    assert value("license_plate_vin", joined) == "30F-1234"


def test_missing_plate_parse_fails() -> None:
    result = normalize_field("license_plate_vin", "ba muoi a")
    assert result.value == "30A"
    assert result.parse_failed is True


def test_vin_compacts_letters_and_digits() -> None:
    raw = "r l r b v mot e x hai n c khong mot hai ba bon nam"
    result = normalize_field("license_plate_vin", raw)
    assert result.value == "RLRBV1EX2NC012345"
    assert result.parse_failed is False


def test_invalid_vin_with_forbidden_letter_fails() -> None:
    result = normalize_field("license_plate_vin", "VF3 ABCD I 123456789")
    assert result.parse_failed is True


def test_odo_van_to_kilometers() -> None:
    assert value("current_odo", "nam van cay") == "50000"


def test_odo_nghin_to_kilometers() -> None:
    assert value("current_odo", "hai muoi nghin km") == "20000"


def test_odo_digits_passthrough() -> None:
    assert value("current_odo", "34567 km") == "34567"


def test_odo_hundred_thousand_composes() -> None:
    # Regression: "một trăm nghìn" used to drop "trăm" and yield 1,000 (100x too small).
    assert value("current_odo", "một trăm nghìn") == "100000"
    assert value("current_odo", "hai trăm nghìn") == "200000"


def test_odo_hundred_plus_tens_thousand_composes() -> None:
    assert value("current_odo", "một trăm hai mươi nghìn") == "120000"
    assert value("current_odo", "năm mươi lăm nghìn") == "55000"


def test_odo_million_composes() -> None:
    assert value("current_odo", "một triệu") == "1000000"


def test_odo_with_no_number_parse_fails() -> None:
    # No number heard -> garbled (#5) re-ask, never a silently-confirmed empty odo.
    result = normalize_field("current_odo", "anh chưa xem")
    assert result.value is None
    assert result.parse_failed is True


def test_free_text_preserved_for_name() -> None:
    assert value("full_name", "Nguyen Van Nam") == "Nguyen Van Nam"


def test_free_text_preserved_for_location() -> None:
    assert (
        value("current_location", "cao toc Ha Noi Hai Phong km 32")
        == "cao toc Ha Noi Hai Phong km 32"
    )


def test_empty_strict_field_fails() -> None:
    result = normalize_field("owner_phone", " ")
    assert result.value is None
    assert result.parse_failed is True


def test_empty_non_strict_field_fails_as_no_value() -> None:
    result = normalize_field("full_name", "")
    assert result.value is None
    assert result.parse_failed is True
