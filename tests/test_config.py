from src.config import load_config


def test_load_config_parses_tool_mappings():
    cfg = load_config("config/settings.yaml")

    assert cfg.hardware.mode in {"mock", "raspberry_pi"}
    assert cfg.hardware.flap_pins
    assert cfg.hardware.solenoid_pins
    assert "1234" in cfg.runtime.allowed_pin_suffixes
    assert cfg.detection.mode in {"manual", "camera"}
    assert isinstance(cfg.detection.camera_index, int)
