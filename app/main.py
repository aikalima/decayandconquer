import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import pandas as pd
import os

from app.modules.health import get_ping_response
from app.predicion_pipline.predict import predict_price
from app.predicion_pipline.smoothing import BSplineParams

logging.basicConfig(filename='server.log', level=logging.INFO)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/ping")
async def ping():
    logging.info("ping received")
    return get_ping_response()

@app.get("/predict")
async def predict_price_route(
    input_csv_path: str = "app/data/nvidia_date20250128_strikedate20250516_price12144.csv",
    spot: float = 121.44,
    days_forward: int = 100,
    risk_free_rate: float = 0.03,
    solver: str = "brent",
    bspline_k: int = 3,
    bspline_smooth: float = 10.0,
    bspline_dx: float = 0.1,
    kernel_smooth: bool = True,
):
    logging.info(f"predict_price received with params: {input_csv_path}, {spot}, {days_forward}, {risk_free_rate}, {solver}, {bspline_k}, {bspline_smooth}, {bspline_dx}, {kernel_smooth}")
    
    if not os.path.exists(input_csv_path):
        input_csv_path = "app/data/dummy_options.csv"

    quotes_df = pd.read_csv(input_csv_path)

    bspline_params = BSplineParams(k=bspline_k, smooth=bspline_smooth, dx=bspline_dx)

    result_df = predict_price(
        quotes=quotes_df,
        spot=spot,
        days_forward=days_forward,
        risk_free_rate=risk_free_rate,
        solver=solver,
        bspline=bspline_params,
        kernel_smooth=kernel_smooth,
    )
    
    print(result_df)
    return result_df