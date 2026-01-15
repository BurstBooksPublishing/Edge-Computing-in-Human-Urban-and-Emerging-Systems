from fastapi import FastAPI
import numpy as np
import tflite_runtime.interpreter as tflite
import uvicorn
import jwt  # use system-keystore signed tokens in production

# load TFLite model on-device
interpreter = tflite.Interpreter(model_path="model.tflite")
interpreter.allocate_tensors()
input_details = interpreter.get_input_details()
output_details = interpreter.get_output_details()

app = FastAPI()

def predict_proba(x: np.ndarray) -> np.ndarray:
    interpreter.set_tensor(input_details[0]['index'], x.astype(np.float32))
    interpreter.invoke()
    return interpreter.get_tensor(output_details[0]['index'])

def compute_ece(probs: np.ndarray, labels: np.ndarray, M: int = 10) -> float:
    n = labels.size
    bins = np.linspace(0.0, 1.0, M+1)
    ece = 0.0
    for m in range(M):
        mask = (probs.max(axis=1) > bins[m]) & (probs.max(axis=1) <= bins[m+1])
        if not np.any(mask):
            continue
        acc = (labels[mask] == probs[mask].argmax(axis=1)).mean()
        conf = probs[mask].max(axis=1).mean()
        ece += (mask.sum()/n) * abs(acc - conf)
    return float(ece)

@app.post("/explain")
def explain(sample: dict):
    x = np.array(sample["input"], dtype=np.float32)
    probs = predict_proba(x.reshape(1, -1))
    ece = compute_ece(probs, np.array(sample.get("label", [0])), M=10)
    # minimal explanation payload; sign with device key in production
    token = jwt.encode({"ece": ece}, "dev-key", algorithm="HS256")
    return {"probs": probs.tolist(), "ece": ece, "signed": token}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8443)