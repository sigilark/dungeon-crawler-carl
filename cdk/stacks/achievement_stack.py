import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import (
    aws_certificatemanager as acm,
)
from aws_cdk import (
    aws_dynamodb as dynamodb,
)
from aws_cdk import (
    aws_ec2 as ec2,
)
from aws_cdk import (
    aws_ecr_assets as ecr_assets,
)
from aws_cdk import (
    aws_ecs as ecs,
)
from aws_cdk import (
    aws_elasticloadbalancingv2 as elbv2,
)
from aws_cdk import (
    aws_logs as logs,
)
from aws_cdk import (
    aws_route53 as route53,
)
from aws_cdk import (
    aws_route53_targets as targets,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_secretsmanager as secretsmanager,
)
from constructs import Construct


class AchievementStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # --- VPC ---
        vpc = ec2.Vpc(
            self, "Vpc",
            max_azs=2,
            nat_gateways=1,
        )

        # --- DNS + TLS ---
        domain_name = "achievement.sigilark.com"

        hosted_zone = route53.HostedZone.from_lookup(
            self, "Zone",
            domain_name="sigilark.com",
        )

        certificate = acm.Certificate(
            self, "Cert",
            domain_name=domain_name,
            validation=acm.CertificateValidation.from_dns(hosted_zone),
        )

        # --- DynamoDB ---
        table = dynamodb.Table(
            self, "AchievementsTable",
            table_name="achievements",
            partition_key=dynamodb.Attribute(name="id", type=dynamodb.AttributeType.NUMBER),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # --- S3 ---
        bucket = s3.Bucket(
            self, "AudioBucket",
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
            lifecycle_rules=[
                s3.LifecycleRule(
                    transitions=[
                        s3.Transition(
                            storage_class=s3.StorageClass.INFREQUENT_ACCESS,
                            transition_after=Duration.days(90),
                        ),
                    ],
                ),
            ],
        )

        # --- Secrets Manager (pre-created, referenced by name) ---
        anthropic_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "AnthropicKey", "achievement-intercom/anthropic-api-key",
        )
        elevenlabs_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "ElevenLabsKey", "achievement-intercom/elevenlabs-api-key",
        )
        elevenlabs_voice_secret = secretsmanager.Secret.from_secret_name_v2(
            self, "ElevenLabsVoice", "achievement-intercom/elevenlabs-voice-id",
        )

        # --- Docker Image ---
        image_asset = ecr_assets.DockerImageAsset(
            self, "AppImage",
            directory="..",
            exclude=["cdk", "finetune_data", "finetune_output", ".venv",
                      "reference_audio", "transcripts", "original_source",
                      "output", ".git", "__pycache__"],
        )

        # --- ECS Cluster ---
        cluster = ecs.Cluster(self, "Cluster", vpc=vpc)

        # --- Task Definition ---
        task_def = ecs.FargateTaskDefinition(
            self, "TaskDef",
            cpu=512,
            memory_limit_mib=1024,
        )

        # Grant DynamoDB + S3 access to task role
        table.grant_read_write_data(task_def.task_role)
        bucket.grant_read_write(task_def.task_role)

        # --- Container ---
        log_group = logs.LogGroup(
            self, "Logs",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        task_def.add_container(
            "App",
            image=ecs.ContainerImage.from_docker_image_asset(image_asset),
            logging=ecs.LogDrivers.aws_logs(
                log_group=log_group,
                stream_prefix="achievement",
            ),
            environment={
                "MODEL": "claude-opus-4-5",
                "MAX_TOKENS": "400",
                "STORAGE_MODE": "cloud",
                "DYNAMODB_TABLE": table.table_name,
                "S3_BUCKET": bucket.bucket_name,
                "OUTPUT_DIR": "/tmp/output",
            },
            secrets={
                "ANTHROPIC_API_KEY": ecs.Secret.from_secrets_manager(anthropic_secret),
                "ELEVENLABS_API_KEY": ecs.Secret.from_secrets_manager(elevenlabs_secret),
                "ELEVENLABS_VOICE_ID": ecs.Secret.from_secrets_manager(elevenlabs_voice_secret),
            },
            port_mappings=[ecs.PortMapping(container_port=8000)],
        )

        # --- ALB + Fargate Service ---
        alb = elbv2.ApplicationLoadBalancer(
            self, "Alb",
            vpc=vpc,
            internet_facing=True,
        )

        service = ecs.FargateService(
            self, "Service",
            cluster=cluster,
            task_definition=task_def,
            desired_count=1,
            assign_public_ip=False,
            platform_version=ecs.FargatePlatformVersion.LATEST,
        )

        # HTTP → HTTPS redirect
        alb.add_listener(
            "HttpRedirect",
            port=80,
            default_action=elbv2.ListenerAction.redirect(
                protocol="HTTPS",
                port="443",
                permanent=True,
            ),
        )

        # HTTPS listener
        https_listener = alb.add_listener(
            "HttpsListener",
            port=443,
            certificates=[certificate],
        )
        https_listener.add_targets(
            "EcsTarget",
            port=8000,
            targets=[service],
            health_check=elbv2.HealthCheck(
                path="/health",
                interval=Duration.seconds(30),
                timeout=Duration.seconds(5),
                healthy_threshold_count=2,
                unhealthy_threshold_count=3,
            ),
        )

        # --- DNS Record ---
        route53.ARecord(
            self, "DnsRecord",
            zone=hosted_zone,
            record_name="achievement",
            target=route53.RecordTarget.from_alias(targets.LoadBalancerTarget(alb)),
        )

        # --- Outputs ---
        cdk.CfnOutput(self, "Url", value=f"https://{domain_name}")
        cdk.CfnOutput(self, "TableName", value=table.table_name)
        cdk.CfnOutput(self, "BucketName", value=bucket.bucket_name)
        cdk.CfnOutput(self, "AlbDns", value=alb.load_balancer_dns_name)
