
# AWS API Gateway HTTP API to AWS Lambda in VPC to DynamoDB CDK Python Sample!


## Overview

Creates an [AWS Lambda](https://aws.amazon.com/lambda/) function writing to [Amazon DynamoDB](https://aws.amazon.com/dynamodb/) and invoked by [Amazon API Gateway](https://aws.amazon.com/api-gateway/) REST API. 

![architecture](docs/architecture.png)

## Setup

The `cdk.json` file tells the CDK Toolkit how to execute your app.

This project is set up like a standard Python project.  The initialization
process also creates a virtualenv within this project, stored under the `.venv`
directory.  To create the virtualenv it assumes that there is a `python3`
(or `python` for Windows) executable in your path with access to the `venv`
package. If for any reason the automatic creation of the virtualenv fails,
you can create the virtualenv manually.

To manually create a virtualenv on MacOS and Linux:

```
$ python3 -m venv .venv
```

After the init process completes and the virtualenv is created, you can use the following
step to activate your virtualenv.

```
$ source .venv/bin/activate
```

If you are a Windows platform, you would activate the virtualenv like this:

```
% .venv\Scripts\activate.bat
```

Once the virtualenv is activated, you can install the required dependencies.

```
$ pip install -r requirements.txt
```

At this point you can now synthesize the CloudFormation template for this code.

```
$ cdk synth
```

To add additional dependencies, for example other CDK libraries, just add
them to your `setup.py` file and rerun the `pip install -r requirements.txt`
command.

## Deploy
At this point you can deploy the stack. 

Using the default profile

```
$ cdk deploy
```

With specific profile

```
$ cdk deploy --profile test
```

## After Deploy

### Retrieve API Key
After deployment, retrieve the API key value from AWS Systems Manager Parameter Store or API Gateway console:

```bash
aws apigateway get-api-keys --include-values --query "items[?name=='DemoApiKey'].value" --output text
```

### Test the API
Navigate to AWS API Gateway console or use curl to test the API. You must include the `x-api-key` header with your requests:

```bash
curl -X POST https://YOUR_API_ID.execute-api.REGION.amazonaws.com/prod/ \
  -H "x-api-key: YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"year":"2023", "title":"kkkg", "id":"12"}'
```

You should get below response:

```json
{"message": "Successfully inserted data!"}
```

### Usage Plan Limits
The API is protected with the following limits per API key:
- Rate limit: 10 requests per second
- Burst limit: 20 concurrent requests
- Daily quota: 10,000 requests

## Monitoring and Observability

### AWS X-Ray Tracing
This application has end-to-end tracing enabled using AWS X-Ray:
- API Gateway traces all incoming requests
- Lambda function traces execution with active tracing
- DynamoDB operations are automatically traced

To view traces:
1. Navigate to AWS X-Ray console
2. Select "Service Map" to see component interactions
3. Select "Traces" to view individual request traces
4. Use filters to find specific requests or errors

### CloudWatch ServiceLens
ServiceLens provides a unified view of your application:
1. Navigate to CloudWatch console
2. Select "ServiceLens" from the left menu
3. View the service map showing all components
4. Click on any service to see metrics, logs, and traces
5. Investigate issues by correlating traces with logs and alarms

### CloudWatch Synthetic Canary
A synthetic canary tests the API endpoint every 5 minutes:
- Canary name: `api-endpoint-canary`
- Tests API availability and response time
- Integrated with X-Ray for end-to-end tracing

To view canary results:
1. Navigate to CloudWatch console
2. Select "Synthetics" under "Application monitoring"
3. Click on `api-endpoint-canary` to view test results

**Note:** After deployment, you must manually upload the canary code and start the canary:
```bash
# Package canary code
cd lambda/canary
zip -r canary-code.zip api_canary.py requirements.txt

# Upload to S3 (replace BUCKET_NAME with the canary artifacts bucket)
aws s3 cp canary-code.zip s3://BUCKET_NAME/canary-code.zip

# Start the canary
aws synthetics start-canary --name api-endpoint-canary
```

### CloudWatch Alarms
Three alarms monitor the application health:
1. **LambdaErrorAlarm**: Triggers when Lambda has >5 errors in 10 minutes
2. **LambdaLatencyAlarm**: Triggers when average duration exceeds 3 seconds
3. **CanaryFailureAlarm**: Triggers when synthetic canary test fails

To configure alarm notifications:
1. Create an SNS topic for notifications
2. Add the SNS topic as an alarm action in the CloudWatch console

## Cleanup 
Run below script to delete AWS resources created by this sample stack.
```
cdk destroy
```

## Useful commands

 * `cdk ls`          list all stacks in the app
 * `cdk synth`       emits the synthesized CloudFormation template
 * `cdk deploy`      deploy this stack to your default AWS account/region
 * `cdk diff`        compare deployed stack with current state
 * `cdk docs`        open CDK documentation

Enjoy!
