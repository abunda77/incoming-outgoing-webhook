#!/usr/bin/env python3
"""
FastAPI Webhook Bridge dengan Browser Agent
Menerima payload webhook dan meneruskannya ke URL eksternal menggunakan browser automation
"""

import os
import json
import logging
from typing import Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from playwright.async_api import async_playwright, Browser, Page
import httpx

# Konfigurasi logging
logging.basicConfig(
    level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Konfigurasi dari environment
PORT = int(os.getenv("PORT", 3005))
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://n8n.produkmastah.com/webhook-test/3df77d1c-6227-41ee-b4ea-32b8d02f6405")
#WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://webhook.site/42c6e880-bb80-44a5-8509-566d23d8c502")

# Global browser instance
browser: Browser = None
page: Page = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager untuk FastAPI - setup dan cleanup browser"""
    global browser, page
    
    logger.info("Inisialisasi browser Playwright...")
    try:
        playwright = await async_playwright().start()
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page()
        logger.info("Browser berhasil diinisialisasi")
        
        yield
        
    except Exception as e:
        logger.error(f"Error saat inisialisasi browser: {str(e)}")
        raise
    finally:
        if browser:
            await browser.close()
            logger.info("Browser ditutup")
        if 'playwright' in locals():
            await playwright.stop()

# Inisialisasi FastAPI app
app = FastAPI(
    title="Webhook Bridge dengan Browser Agent",
    description="Menerima webhook dan meneruskannya ke URL eksternal via browser automation",
    version="1.0.0",
    lifespan=lifespan
)

@app.get("/")
async def root():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "webhook-bridge",
        "port": PORT,
        "webhook_url": WEBHOOK_URL
    }

@app.get("/health")
async def health_check():
    """Health check endpoint yang lebih detail"""
    return {
        "status": "healthy",
        "timestamp": logging.Formatter().formatTime(logging.LogRecord(
            name="health", level=logging.INFO, pathname="", lineno=0,
            msg="", args=(), exc_info=None
        )),
        "config": {
            "port": PORT,
            "webhook_url": WEBHOOK_URL,
            "log_level": os.getenv("LOG_LEVEL", "INFO")
        }
    }

@app.post("/webhook")
async def receive_webhook(request: Request):
    """
    Endpoint untuk menerima webhook dan meneruskannya ke URL eksternal
    """
    try:
        # Ambil payload dari request
        payload = await request.json()
        logger.info(f"Received webhook payload: {json.dumps(payload, indent=2)}")
        
        # Validasi payload
        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Payload harus berupa JSON object")
        
        # Forward payload ke URL eksternal menggunakan browser
        logger.info(f"Forwarding payload to: {WEBHOOK_URL}")
        
        # Gunakan browser untuk mengirim data
        result = await forward_via_browser(payload)
        
        logger.info(f"Forwarding completed with status: {result.get('status', 'unknown')}")
        
        return JSONResponse(
            status_code=200,
            content={
                "message": "Webhook processed successfully",
                "forwarded_to": WEBHOOK_URL,
                "result": result
            }
        )
        
    except json.JSONDecodeError:
        logger.error("Invalid JSON payload")
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
    except Exception as e:
        logger.error(f"Error processing webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

async def forward_via_browser(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Mengirim payload ke URL eksternal menggunakan browser automation
    """
    global page
    
    try:
        # Navigasi ke URL target
        await page.goto(WEBHOOK_URL)
        
        # Konversi payload ke JSON string
        payload_json = json.dumps(payload)
        
        # Eksekusi JavaScript untuk mengirim data
        result = await page.evaluate(
            """(data) => {
                return fetch(window.location.href, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: data
                }).then(response => {
                    return response.json().then(json => ({
                        status: response.status,
                        statusText: response.statusText,
                        data: json
                    })).catch(() => ({
                        status: response.status,
                        statusText: response.statusText,
                        data: null
                    }));
                }).catch(error => ({
                    status: 0,
                    statusText: 'Network Error',
                    error: error.message
                }));
            }""",
            payload_json
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Error during browser forwarding: {str(e)}")
        return {
            "status": 500,
            "statusText": "Browser Error",
            "error": str(e)
        }

@app.post("/webhook/direct")
async def receive_webhook_direct(request: Request):
    """
    Endpoint alternatif untuk menerima webhook dan meneruskannya langsung via HTTP
    (tanpa browser automation)
    """
    try:
        payload = await request.json()
        logger.info(f"Received direct webhook payload: {json.dumps(payload, indent=2)}")
        
        # Kirim langsung via HTTP
        async with httpx.AsyncClient() as client:
            response = await client.post(
                WEBHOOK_URL,
                json=payload,
                headers={"Content-Type": "application/json"}
            )
        
        logger.info(f"Direct forwarding completed with status: {response.status_code}")
        
        return JSONResponse(
            status_code=200,
            content={
                "message": "Webhook processed successfully via direct HTTP",
                "forwarded_to": WEBHOOK_URL,
                "status_code": response.status_code,
                "response": response.json() if response.content else None
            }
        )
        
    except Exception as e:
        logger.error(f"Error processing direct webhook: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=PORT,
        log_level=os.getenv("LOG_LEVEL", "INFO").lower()
    )