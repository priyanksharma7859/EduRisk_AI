import pandas as pd
from sklearn.ensemble import RandomForestClassifier
import joblib

data = {
    "attendance": [92,65,78,55,88,72,96,60,81,68,90,74,50,86,63,94,77,58,83,70],
    "score": [85,48,62,42,76,58,91,45,69,52,84,61,35,73,47,89,64,40,71,55],
    "lms": [90,40,70,35,82,55,95,38,75,48,88,65,28,80,42,92,68,32,78,52],
    "risk": [
        "Low","High","Medium","High","Low",
        "Medium","Low","High","Low","Medium",
        "Low","Medium","High","Low","High",
        "Low","Medium","High","Low","Medium"
    ]
}

df = pd.DataFrame(data)

X = df[["attendance", "score", "lms"]]
y = df["risk"]

model = RandomForestClassifier(
    n_estimators=100,
    random_state=42
)

model.fit(X, y)

joblib.dump(model, "student_risk_model.pkl")

print("AI Model trained successfully!")
# Predict student risk

student = [[80, 70, 60]]

prediction = model.predict(student)

print("Predicted Risk:", prediction[0])