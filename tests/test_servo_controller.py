from src.hardware.servo_controller import ServoController
from src.models import ToolClass


def test_servo_controller_simulation_open_close_cycle():
    controller = ServoController(
        servo_pins={
            ToolClass.PLIER: 17,
            ToolClass.SCREWDRIVER: 27,
            ToolClass.WRENCH: 22,
        },
        open_angle=90,
        close_angle=0,
        open_secs=0.1,
    )

    assert controller.open(ToolClass.PLIER, auto_close=False) is True
    controller.close(ToolClass.PLIER)
    controller.close_all()
    controller.cleanup()
