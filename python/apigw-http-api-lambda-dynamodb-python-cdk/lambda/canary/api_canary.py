# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import json
import os
from aws_synthetics.selenium import synthetics_webdriver as syn_webdriver
from aws_synthetics.common import synthetics_logger as logger
import requests

def handler(event, context):
    """
    CloudWatch Synthetic Canary to monitor API Gateway endpoint.
    Tests API availability and response time with X-Ray tracing.
    """
    
    api_url = os.environ.get('API_URL')
    api_key = os.environ.get('API_KEY')
    
    if not api_url or not api_key:
        raise Exception("API_URL and API_KEY environment variables must be set")
    
    logger.info(f"Testing API endpoint: {api_url}")
    
    # Test payload
    test_data = {
        "year": "2024",
        "title": "Canary Test Movie",
        "id": "canary-test-001"
    }
    
    headers = {
        "x-api-key": api_key,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.post(
            api_url,
            headers=headers,
            json=test_data,
            timeout=10
        )
        
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text}")
        
        if response.status_code != 200:
            raise Exception(f"API returned status code {response.status_code}")
        
        response_json = response.json()
        if "message" not in response_json:
            raise Exception("Response missing expected 'message' field")
        
        logger.info("API test successful")
        return "success"
        
    except Exception as e:
        logger.error(f"API test failed: {str(e)}")
        raise
