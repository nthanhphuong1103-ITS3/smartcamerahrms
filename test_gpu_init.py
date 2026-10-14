"""Test GPU OpenCL initialization for AI models"""
import cv2
import os
import sys
sys.stdout.reconfigure(encoding='utf-8')

# Simulate startup
cv2.ocl.setUseOpenCL(False)

_USE_OPENCL_DNN = False
try:
    cv2.ocl.setUseOpenCL(True)
    if cv2.ocl.useOpenCL():
        _USE_OPENCL_DNN = True
    cv2.ocl.setUseOpenCL(False)
except Exception:
    pass

status = "ENABLED (GTX 750 Ti)" if _USE_OPENCL_DNN else "DISABLED - fallback CPU"
print(f"[GPU] OpenCL for DNN: {status}")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODEL_DIR = os.path.join(BASE_DIR, "models")
YUNET_PATH = os.path.join(MODEL_DIR, "face_detection_yunet.onnx")
SFACE_PATH = os.path.join(MODEL_DIR, "face_recognition_sface.onnx")

if _USE_OPENCL_DNN:
    dnn_backend = cv2.dnn.DNN_BACKEND_OPENCV
    dnn_target  = cv2.dnn.DNN_TARGET_OPENCL
    target_label = "OpenCL/GPU"
else:
    dnn_backend = cv2.dnn.DNN_BACKEND_OPENCV
    dnn_target  = cv2.dnn.DNN_TARGET_CPU
    target_label = "CPU"

try:
    det = cv2.FaceDetectorYN.create(
        YUNET_PATH, "", (640, 360),
        score_threshold=0.75, nms_threshold=0.3, top_k=5000,
        backend_id=dnn_backend, target_id=dnn_target
    )
    rec = cv2.FaceRecognizerSF.create(
        SFACE_PATH, "",
        backend_id=dnn_backend, target_id=dnn_target
    )
    print(f"[GPU] AI Models loaded on: {target_label}")
    print("[OK] Model load THANH CONG - he thong san sang!")
    
    # Test CAM AI config
    CAM_AI_CONFIG = {
        1: {"min_face": 60, "ai_sleep": 0.13, "enrich_streak": 3, "border_pct": 0.03},
        2: {"min_face": 40, "ai_sleep": 0.08, "enrich_streak": 3, "border_pct": 0.03},
        3: {"min_face": 45, "ai_sleep": 0.08, "enrich_streak": 2, "border_pct": 0.03},
        4: {"min_face": 55, "ai_sleep": 0.08, "enrich_streak": 2, "border_pct": 0.05},
    }
    print("\n[CFG] CAM AI Configuration:")
    for cam_id, cfg in CAM_AI_CONFIG.items():
        bdr = cfg.get("border_pct", 0.03)
        print(f"  CAM {cam_id:02d}: min_face={cfg['min_face']}px | AI={1/cfg['ai_sleep']:.0f}FPS | enrich={cfg['enrich_streak']} | border={bdr:.0%}")
    
except Exception as e:
    print(f"[FAIL] Model load that bai: {e}")
    import traceback
    traceback.print_exc()
