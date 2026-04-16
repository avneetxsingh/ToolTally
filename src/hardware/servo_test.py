from __future__ import annotations

import time


def run_servo_test(linearactuator_channel: int) -> None:
    import board
    import busio
    from adafruit_motor import servo
    from adafruit_pca9685 import PCA9685

    i2c = busio.I2C(board.SCL, board.SDA)
    pca = PCA9685(i2c)
    pca.frequency = 50
    linear_actuator = servo.Servo(pca.channels[linearactuator_channel])

    print("Moving slowly....")
    try:
        while True:
            print(f"Servo 4(Channel {linearactuator_channel})")
            linear_actuator.angle = 0
            time.sleep(2)
            linear_actuator.angle = 180
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping servo test.")
    finally:
        linear_actuator.angle = None
        pca.deinit()
