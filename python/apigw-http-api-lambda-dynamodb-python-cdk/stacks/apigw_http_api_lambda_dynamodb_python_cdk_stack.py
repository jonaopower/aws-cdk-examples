# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

import os
from aws_cdk import (
    Stack,
    aws_dynamodb as dynamodb_,
    aws_lambda as lambda_,
    aws_apigateway as apigw_,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_logs as logs,
    aws_wafv2 as wafv2,
    aws_s3 as s3,
    aws_synthetics as synthetics,
    aws_cloudwatch as cloudwatch,
    Duration,
    RemovalPolicy,
    CfnOutput,
)
from constructs import Construct

TABLE_NAME = "demo_table"


class ApigwHttpApiLambdaDynamodbPythonCdkStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # VPC
        vpc = ec2.Vpc(
            self,
            "Ingress",
            cidr="10.1.0.0/16",
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Private-Subnet", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24
                )
            ],
        )
        
        # Create log group for VPC Flow Logs
        vpc_flow_log_group = logs.LogGroup(
            self,
            "VpcFlowLogs",
            retention=logs.RetentionDays.ONE_YEAR,
        )

        # Create IAM role for VPC Flow Logs
        flow_log_role = iam.Role(
            self,
            "VpcFlowLogRole",
            assumed_by=iam.ServicePrincipal("vpc-flow-logs.amazonaws.com"),
        )

        # Enable VPC Flow Logs
        ec2.FlowLog(
            self,
            "VpcFlowLog",
            resource_type=ec2.FlowLogResourceType.from_vpc(vpc),
            destination=ec2.FlowLogDestination.to_cloud_watch_logs(
                vpc_flow_log_group, flow_log_role
            ),
        )
        
        # Create VPC endpoint
        dynamo_db_endpoint = ec2.GatewayVpcEndpoint(
            self,
            "DynamoDBVpce",
            service=ec2.GatewayVpcEndpointAwsService.DYNAMODB,
            vpc=vpc,
        )

        # This allows to customize the endpoint policy
        dynamo_db_endpoint.add_to_policy(
            iam.PolicyStatement(  # Restrict to listing and describing tables
                principals=[iam.AnyPrincipal()],
                actions=[                "dynamodb:DescribeStream",
                "dynamodb:DescribeTable",
                "dynamodb:Get*",
                "dynamodb:Query",
                "dynamodb:Scan",
                "dynamodb:CreateTable",
                "dynamodb:Delete*",
                "dynamodb:Update*",
                "dynamodb:PutItem"],
                resources=["*"],
            )
        )

        # Create DynamoDb Table
        demo_table = dynamodb_.Table(
            self,
            TABLE_NAME,
            partition_key=dynamodb_.Attribute(
                name="id", type=dynamodb_.AttributeType.STRING
            ),
            point_in_time_recovery=True,
        )

        # Create the Lambda function to receive the request
        api_hanlder = lambda_.Function(
            self,
            "ApiHandler",
            function_name="apigw_handler",
            runtime=lambda_.Runtime.PYTHON_3_9,
            code=lambda_.Code.from_asset("lambda/apigw-handler"),
            handler="index.handler",
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            memory_size=1024,
            timeout=Duration.minutes(5),
            reserved_concurrent_executions=100,
            log_retention=logs.RetentionDays.ONE_YEAR,
            tracing=lambda_.Tracing.ACTIVE,
        )

        # grant permission to lambda to write to demo table
        demo_table.grant_write_data(api_hanlder)
        api_hanlder.add_environment("TABLE_NAME", demo_table.table_name)

        # Create log group for API Gateway access logs
        api_log_group = logs.LogGroup(
            self,
            "ApiGatewayAccessLogs",
            retention=logs.RetentionDays.ONE_YEAR,
        )

        # Create WAF Web ACL with rate-based rule
        web_acl = wafv2.CfnWebACL(
            self,
            "ApiWebAcl",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            scope="REGIONAL",
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="ApiWebAclMetric",
                sampled_requests_enabled=True
            ),
            rules=[
                wafv2.CfnWebACL.RuleProperty(
                    name="RateLimitRule",
                    priority=1,
                    statement=wafv2.CfnWebACL.StatementProperty(
                        rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                            limit=2000,
                            aggregate_key_type="IP"
                        )
                    ),
                    action=wafv2.CfnWebACL.RuleActionProperty(
                        block={}
                    ),
                    visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                        cloud_watch_metrics_enabled=True,
                        metric_name="RateLimitRuleMetric",
                        sampled_requests_enabled=True
                    )
                )
            ]
        )

        # Create API Gateway
        api = apigw_.LambdaRestApi(
            self,
            "Endpoint",
            handler=api_hanlder,
            default_method_options=apigw_.MethodOptions(
                api_key_required=True
            ),
            deploy_options=apigw_.StageOptions(
                throttling_burst_limit=100,
                throttling_rate_limit=50,
                access_log_destination=apigw_.LogGroupLogDestination(api_log_group),
                access_log_format=apigw_.AccessLogFormat.json_with_standard_fields(
                    caller=True,
                    http_method=True,
                    ip=True,
                    protocol=True,
                    request_time=True,
                    resource_path=True,
                    response_length=True,
                    status=True,
                    user=True,
                ),
                tracing_enabled=True,
            ),
        )

        # Create usage plan
        usage_plan = api.add_usage_plan(
            "UsagePlan",
            name="StandardUsagePlan",
            throttle=apigw_.ThrottleSettings(
                rate_limit=10,
                burst_limit=20
            ),
            quota=apigw_.QuotaSettings(
                limit=10000,
                period=apigw_.Period.DAY
            )
        )

        # Create API key
        api_key = api.add_api_key("ApiKey", api_key_name="DemoApiKey")

        # Associate API key with usage plan
        usage_plan.add_api_key(api_key)

        # Add API stage to usage plan
        usage_plan.add_api_stage(
            stage=api.deployment_stage
        )

        # Associate WAF with API Gateway stage
        wafv2.CfnWebACLAssociation(
            self,
            "WebAclAssociation",
            resource_arn=f"arn:aws:apigateway:{self.region}::/restapis/{api.rest_api_id}/stages/{api.deployment_stage.stage_name}",
            web_acl_arn=web_acl.attr_arn
        )

        # Create S3 bucket for canary artifacts
        canary_bucket = s3.Bucket(
            self,
            "CanaryArtifacts",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )

        # Create IAM role for canary
        canary_role = iam.Role(
            self,
            "CanaryRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "CloudWatchSyntheticsFullAccess"
                )
            ],
        )

        # Grant canary access to S3 bucket
        canary_bucket.grant_read_write(canary_role)

        # Create CloudWatch Synthetic Canary
        canary = synthetics.CfnCanary(
            self,
            "ApiCanary",
            name="api-endpoint-canary",
            artifact_s3_location=f"s3://{canary_bucket.bucket_name}/canary",
            execution_role_arn=canary_role.role_arn,
            runtime_version="syn-python-selenium-1.3",
            schedule=synthetics.CfnCanary.ScheduleProperty(
                expression="rate(5 minutes)", duration_in_seconds=0
            ),
            code=synthetics.CfnCanary.CodeProperty(
                handler="api_canary.handler",
                s3_bucket=canary_bucket.bucket_name,
                s3_key="canary-code.zip",
            ),
            start_canary_after_creation=False,
            run_config=synthetics.CfnCanary.RunConfigProperty(
                timeout_in_seconds=60,
                environment_variables={
                    "API_URL": api.url,
                    "API_KEY": api_key.key_id,
                },
            ),
        )

        # Create CloudWatch alarms for Lambda errors
        error_alarm = cloudwatch.Alarm(
            self,
            "LambdaErrorAlarm",
            metric=api_hanlder.metric_errors(
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=5,
            evaluation_periods=2,
            datapoints_to_alarm=2,
            alarm_description="Alert when Lambda function has more than 5 errors in 10 minutes",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # Create CloudWatch alarm for Lambda duration
        latency_alarm = cloudwatch.Alarm(
            self,
            "LambdaLatencyAlarm",
            metric=api_hanlder.metric_duration(
                statistic="Average",
                period=Duration.minutes(5),
            ),
            threshold=3000,
            evaluation_periods=2,
            alarm_description="Alert when Lambda average duration exceeds 3 seconds",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # Create CloudWatch alarm for canary failures
        canary_alarm = cloudwatch.Alarm(
            self,
            "CanaryFailureAlarm",
            metric=cloudwatch.Metric(
                namespace="CloudWatchSynthetics",
                metric_name="Failed",
                dimensions_map={"CanaryName": "api-endpoint-canary"},
                statistic="Sum",
                period=Duration.minutes(5),
            ),
            threshold=1,
            evaluation_periods=1,
            alarm_description="Alert when canary test fails",
            treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
        )

        # Outputs
        CfnOutput(
            self,
            "ApiUrl",
            value=api.url,
            description="API Gateway endpoint URL",
        )

        CfnOutput(
            self,
            "CanaryName",
            value="api-endpoint-canary",
            description="CloudWatch Synthetic Canary name",
        )
