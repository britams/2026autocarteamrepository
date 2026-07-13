from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO
import threading
import time

app = Flask(__name__)
app.config['SECRET_KEY'] = 'autocar_secret_key'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

try:
    from pop import Pilot
    try:
        from pop import LiDAR as lidar_module
    except ImportError:
        from pop import Lidar as lidar_module

    JETSON_MODE = True
    print("🚀 [System] Jetson 실기 하드웨어 연동 완료.")
    
    Car = Pilot.AutoCar()
    Car.setSpeed(100)
    Car.camPan(50)
    Car.camTilt(45)
    
    lidar = lidar_module.Rplidar()
    lidar.connect()
    lidar.startMotor()
except ImportError as e:
    JETSON_MODE = False
    print(f"💻 [System] 가상 시뮬레이션 모드 구동 (이유: {e})")

current_telemetry = {"steering": 0, "speed": 0, "mode": "MANUAL", "status": "READY"}

@app.route('/remote')
def remote_view(): return render_template('remote.html')

@app.route('/api/control')
def api_control():
    global current_telemetry
    if current_telemetry['mode'] == "MANUAL":
        current_telemetry['steering'] = int(request.args.get('steering', 0))
        current_telemetry['speed'] = int(request.args.get('speed', 0))
        print(f"🕹️ [신호 수신] 조향: {current_telemetry['steering']}, 속도: {current_telemetry['speed']}")
    return jsonify(current_telemetry)

@app.route('/api/mode')
def api_mode():
    global current_telemetry
    current_telemetry['mode'] = request.args.get('mode', 'MANUAL')
    current_telemetry['steering'] = 0
    current_telemetry['speed'] = 0
    if JETSON_MODE: Car.stop()
    print(f"🔄 [모드 변경] 주행 모드가 {current_telemetry['mode']}(으)로 전환되었습니다.")
    return jsonify(current_telemetry)

@app.route('/api/kill')
def api_kill():
    global current_telemetry
    current_telemetry['mode'] = "MANUAL"
    current_telemetry['speed'] = 0
    current_telemetry['steering'] = 0
    current_telemetry['status'] = "EMERGENCY_STOP"
    if JETSON_MODE: Car.stop()
    print("🚨 [비상 정지] KILL SWITCH 활성화!")
    return jsonify(current_telemetry)

def motor_control_runtime():
    global current_telemetry
    print("⚙️ [Core] 순정 모터 구동 엔진이 대기 중입니다.")
    while True:
        try:
            if current_telemetry['mode'] == "MANUAL":
                if JETSON_MODE and current_telemetry['status'] != "EMERGENCY_STOP":
                    steer = current_telemetry['steering']
                    speed = current_telemetry['speed']
                    Car.steering = steer
                    if speed > 0: Car.forward(speed)
                    elif speed < 0: Car.backward(abs(speed))
                    else: Car.stop()
                time.sleep(0.05)
            elif current_telemetry['mode'] == "AUTO":
                if JETSON_MODE:
                    vectors = lidar.getVectors()
                    if vectors is None or len(vectors) == 0:
                        time.sleep(0.02)
                        continue
                    obstacle_left = False
                    obstacle_right = False
                    for angle, distance, *_ in vectors:
                        if 0 < distance < 700:
                            if 315 <= angle <= 360: obstacle_left = True
                            elif 0 <= angle <= 45: obstacle_right = True
                    if obstacle_left and obstacle_right:
                        Car.steering = 0
                        Car.backward(70); time.sleep(1.2)
                        Car.steering = -1; Car.forward(75); time.sleep(0.8)
                        Car.steering = 0
                    elif obstacle_left:
                        Car.steering = 1; Car.forward(75)
                    elif obstacle_right:
                        Car.steering = -1; Car.forward(75)
                    else:
                        Car.steering = 0; Car.forward(85)
                time.sleep(0.1)
        except Exception as e:
            time.sleep(0.1)

if __name__ == '__main__':
    threading.Thread(target=motor_control_runtime, daemon=True).start()
    try:
        socketio.run(app, host='0.0.0.0', port=5000, debug=False)
    finally:
        if JETSON_MODE:
            try: Car.stop(); lidar.stopMotor()
            except: pass
