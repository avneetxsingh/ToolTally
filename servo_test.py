import time
import board
import busio
from adafruit_pca9685 import PCA9685
from adafruit_motor import servo

i2c = busio.I2C(board.SCL, board.SDA)

pca = PCA9685(i2c)
pca.frequency = 50

#servo1 = servo.Servo(pca.channels[0])
#servo2=servo.Servo(pca.channels[12])
#servo3=servo.Servo(pca.channels[15])
servo4 = servo.Servo(pca.channels[8])


print("Moving slowly....")

while True:
	'''print("Servo 1(Channel 0)")
	servo1.angle=0
	time.sleep(2)
	servo1.angle=180
	time.sleep(1)
	print("Servo 2(Channel 12)")
	servo2.angle=50
	time.sleep(2)
	servo2.angle=120
	time.sleep(1)
	print("Servo 3 (Channel 15)")
	servo3.angle=0
	time.sleep(2)
	servo3.angle=180
	time.sleep(1)'''
	print("Servo 4(Channel 8)")
	servo4.angle=0
	time.sleep(2)
	servo4.angle=180
	time.sleep(1)
