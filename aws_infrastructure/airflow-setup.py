AWSTemplateFormatVersion: 2010-09-09
Parameters:
  ProjectPrefix:
    Type: String
    Description: Project prefix for naming resources
    Default: de-c2w4a1

  AWSRegion:
    Type: String
    Description: Default AWS Region
    Default: us-east-1

  VPCCIDR:
    Type: String
    Description: CIDR of VPC. IPv4 address range in CIDR notation.
    Default: 10.0.0.0/16

  PublicSubnetCIDR:
    Type: String
    Description: CIDR of a public subnet. IPv4 address range in CIDR notation.
    Default: 10.0.1.0/24
  
  PublicBucketName:
    Type: String
    Description: Public bucket name for assets.
    Default: dlai-data-engineering

  PublicBucketLayerKey:
    Type: String
    Description: Public bucket key for dependencies file.
    Default: labs/cfn_dependencies_vocapi/lambda_layer_dependencies/lambda_layer_dependencies_p312.zip    

  # PublicBucketRequirementsKey:
  #   Type: String
  #   Description: Public bucket key MWAA requirements.
  #   Default: labs/cfn_dependencies/c2w4a1/requirements.txt

  PublicBucketGXKey: 
    Type: String
    Description: Public bucket key for Great Expectations configuration.
    Default: labs/cfn_dependencies_vocapi/c2w4a1/dags/gx
  
  PublicBucketDataKey: 
    Type: String
    Description: Public bucket key for Great Expectations configuration.
    Default: labs/cfn_dependencies_vocapi/c2w4a1/data

  Runtime:
    Type: String
    Description: Lambda function Runtime
    Default: python3.12

  Timeout:
    Type: Number
    Description: Lambda function Timeout
    Default: 300

  LatestAmiId:
    Description: The latest Amazon Linux 2023 AMI from the Parameter Store
    Type: 'AWS::SSM::Parameter::Value<AWS::EC2::Image::Id>'
    Default: '/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64'

  InstanceType:
    Description: The EC2 instance type
    Type: String
    Default: t3.large
    AllowedValues:
      - t3.large

  AirflowPort:
    Type: Number
    Description: Airflow port
    Default: 8080

  KeyName:
    Description: Name of an existing EC2 KeyPair
    Type: String

Metadata:
  AWS::CloudFormation::Interface:
    ParameterGroups:
      - Label:
          default: General Configuration
        Parameters:
          - ProjectPrefix
          - AWSRegion
      - Label:
          default: Network Configuration
        Parameters:
          - VPCCIDR
          - PublicSubnetCIDR          
Resources:
  VPC:
    Type: AWS::EC2::VPC
    Properties:
      CidrBlock: !Ref VPCCIDR
      EnableDnsHostnames: true
      EnableDnsSupport: true
      InstanceTenancy: default
      Tags:
        - Key: Name
          Value: !Sub ${ProjectPrefix}
  InternetGateway:
    Type: AWS::EC2::InternetGateway
    Properties:
      Tags:
        - Key: Application
          Value: !Ref AWS::StackId
        - Key: Name
          Value: !Sub ${ProjectPrefix}-igw
  InternetGatewayAttachment:
    DependsOn:
      - InternetGateway
      - VPC
    Type: AWS::EC2::VPCGatewayAttachment
    Properties:
      InternetGatewayId: !Ref InternetGateway
      VpcId: !Ref VPC
  PublicSubnet:
    DependsOn: VPC
    Type: AWS::EC2::Subnet
    Properties:
      AvailabilityZone: !Select
        - '0'
        - !GetAZs ''
      CidrBlock: !Ref PublicSubnetCIDR
      VpcId: !Ref VPC
      Tags:
        - Key: Name
          Value: !Sub ${ProjectPrefix}-public-subnet
  
  InternetGatewayRoute:
    DependsOn:
      - InternetGatewayAttachment
      - PublicRouteTable
    Type: AWS::EC2::Route
    Properties:
      DestinationCidrBlock: 0.0.0.0/0
      GatewayId: !Ref InternetGateway
      RouteTableId: !Ref PublicRouteTable
  PublicRouteTable:
    DependsOn: VPC
    Type: AWS::EC2::RouteTable
    Properties:
      Tags:
        - Key: Name
          Value: !Sub ${ProjectPrefix}-public-routetable
      VpcId: !Ref VPC
  PublicSubnetRouteTableAssociation:
    Type: AWS::EC2::SubnetRouteTableAssociation
    Properties:
      SubnetId: !Ref PublicSubnet
      RouteTableId: !Ref PublicRouteTable
  
  DefaultVPCSecurityGroup:
    DependsOn: VPC
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: Default Security Group for the VPC.
      VpcId: !Ref VPC
      Tags:
        - Key: Name
          Value: !Sub ${ProjectPrefix}-sg
  DefaultVPCSecurityGroupSelfRefIngress:
    DependsOn: DefaultVPCSecurityGroup
    Type: AWS::EC2::SecurityGroupIngress
    Properties:
      SourceSecurityGroupId: !Ref DefaultVPCSecurityGroup
      IpProtocol: '-1'
      GroupId: !Ref DefaultVPCSecurityGroup

  DagsBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub ${ProjectPrefix}-${AWS::AccountId}-${AWS::Region}-dags
      AccessControl: Private
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true

  RawDataBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketName: !Sub ${ProjectPrefix}-${AWS::AccountId}-${AWS::Region}-raw-data
      AccessControl: Private
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true

  LambdaLayer:
    Type: AWS::Lambda::LayerVersion
    Properties:
      CompatibleArchitectures:
        - arm64
      CompatibleRuntimes:
        - python3.12
      Content:
        S3Bucket: !Ref PublicBucketName
        S3Key: !Ref PublicBucketLayerKey
      Description: Lambda layer with dependencies to insert data into MySQL DB
      LayerName: de-c1w4-lambda-layer

  LambdaCopyToAirflowS3Role:
    Type: AWS::IAM::Role
    Properties:
      AssumeRolePolicyDocument:
        Version: 2012-10-17
        Statement:
          - Effect: Allow
            Action: sts:AssumeRole
            Principal:
              Service:
                - lambda.amazonaws.com
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/service-role/AWSLambdaVPCAccessExecutionRole
        - arn:aws:iam::aws:policy/AmazonS3ReadOnlyAccess
      Policies:
        - PolicyName: LambdaS3PutPolicy
          PolicyDocument:
            Version: "2012-10-17"
            Statement:
              - Effect: "Allow"
                Action: "s3:Put*"
                Resource: !Sub "arn:aws:s3:::${DagsBucket}/*"

  LambdaCopyToAirflowS3:
    DependsOn:
      - DagsBucket
    Type: AWS::Lambda::Function
    Properties:
      Environment:
        Variables:
          SOURCE_BUCKET_NAME: !Ref PublicBucketName
          # SOURCE_PATH_REQS: !Ref PublicBucketRequirementsKey
          DESTINATION_BUCKET: !Ref DagsBucket
          SOURCE_GX_PATH: !Ref PublicBucketGXKey
          DESTINATION_DATA_BUCKET: !Ref RawDataBucket
          SOURCE_DATA_PATH: !Ref PublicBucketDataKey
      Code:
        ZipFile: |
          import json
          import logging
          import os

          import boto3
          import cfnresponse
          from botocore import exceptions

          SOURCE_BUCKET_NAME = os.getenv("SOURCE_BUCKET_NAME", "")
          # SOURCE_PATH_REQS = os.getenv("SOURCE_PATH_REQS", "")
          DESTINATION_BUCKET = os.getenv("DESTINATION_BUCKET", "")
          SOURCE_GX_PATH = os.getenv("SOURCE_GX_PATH", "")
          DESTINATION_DATA_BUCKET = os.getenv("DESTINATION_DATA_BUCKET", "")
          SOURCE_DATA_PATH = os.getenv("SOURCE_DATA_PATH", "")
          
          CREATE = "Create"

          response_data = {}

          logger = logging.getLogger()
          logger.setLevel(logging.INFO)


          def copy_s3_to_s3(
              source_bucket: str, source_path: str, dest_bucket: str, dest_path: str
          ) -> bool:
              """Copies files between S3 buckets

              Args:
                  source_bucket (str): Source bucket
                  source_path (str): Source path
                  dest_bucket (str): Destination bucket
                  dest_path (str): Destination path

              Returns:
                  bool: Shows if copy was successful or not
              """

              s3 = boto3.resource("s3")

              copy_source = {"Bucket": source_bucket, "Key": source_path}

              logger.info(f"copy_source {copy_source}")

              try:
                  bucket = s3.Bucket(dest_bucket)
                  bucket.copy(copy_source, dest_path)

                  return True
              except Exception as err:
                  logger.error(f"Error found: {err}")
                  return False


          def lambda_handler(event, context):
              logger.info(f"Event: {event}")

              logger.info(f"SOURCE_BUCKET_NAME {SOURCE_BUCKET_NAME}")
              #?logger.info(f"SOURCE_PATH_REQS {SOURCE_PATH_REQS}")
              logger.info(f"DESTINATION_BUCKET {DESTINATION_BUCKET}")

              try:
                  if event["RequestType"] == CREATE:
                      # Requirements
                      # logger.info(f"copying requirements file")
                      # copy_reqs_response = copy_s3_to_s3(
                      #     source_bucket=SOURCE_BUCKET_NAME,
                      #     source_path=SOURCE_PATH_REQS,
                      #     dest_bucket=DESTINATION_BUCKET,
                      #     dest_path="requirements.txt",
                      # )
                      # logger.info(f"Requirements file copied successfully")

                      # Dags folder
                      s3_client = boto3.client("s3")

                      create_dags_folder_response = s3_client.put_object(Bucket=DESTINATION_BUCKET, Key='dags/')

                      # Copy GX information to destination bucket
                      response = s3_client.list_objects_v2(Bucket=SOURCE_BUCKET_NAME, Prefix=SOURCE_GX_PATH)
                      
                      # Iterate over objects and copy them to the destination bucket
                      for obj in response.get('Contents', []):
                          # Extract the key (object path) and construct the destination key
                          source_key = obj['Key']
                          destination_key = source_key.replace(SOURCE_GX_PATH, '', 1)  # Remove the folder path from the key
                          logger.info(f"destination_key: {destination_key}")

                          # Copy the object to the destination bucket
                          object_gx_copy_response = copy_s3_to_s3(
                                source_bucket=SOURCE_BUCKET_NAME,
                                source_path=source_key,
                                dest_bucket=DESTINATION_BUCKET,
                                dest_path=f"dags/gx{destination_key}",
                            )                                                
                          
                  cfnresponse.send(event, context, cfnresponse.SUCCESS, response_data)

              except Exception as exc:
                  logger.error(f"Error: {str(exc)}")
                  cfnresponse.send(event, context, cfnresponse.FAILED, response_data)
      FunctionName: !Sub ${ProjectPrefix}-copy-s3-to-s3
      Handler: index.lambda_handler
      Layers:
        - !Ref LambdaLayer
      Runtime: !Ref Runtime
      Role: !GetAtt LambdaCopyToAirflowS3Role.Arn
      Timeout: !Ref Timeout

  CFLambdaCopyS3Airflow:
    DependsOn:
      - LambdaCopyToAirflowS3
    Type: Custom::CFLambdaCopyS3Airflow
    Properties:
      ServiceToken: !GetAtt LambdaCopyToAirflowS3.Arn
    DeletionPolicy: Delete

  EC2SecurityGroup:
    Type: AWS::EC2::SecurityGroup
    Properties:
      GroupDescription: EC2 Security Group
      VpcId: !Ref VPC
      Tags:
        - Key: Name
          Value: !Sub ${ProjectPrefix}-ec2-sg

  EC2SecurityGroupIngress:
    Type: AWS::EC2::SecurityGroupIngress
    Properties:
      GroupId: !Ref EC2SecurityGroup
      CidrIp: 0.0.0.0/0
      IpProtocol: tcp
      FromPort: 22
      ToPort: 22

  EC2SecurityGroupIngressAirflow:
    Type: AWS::EC2::SecurityGroupIngress
    Properties:
      GroupId: !Ref EC2SecurityGroup
      CidrIp: 0.0.0.0/0
      IpProtocol: tcp
      FromPort: !Ref AirflowPort
      ToPort: !Ref AirflowPort

  EC2KeyPair:
    Type: AWS::EC2::KeyPair
    Properties:
      KeyName: !Sub ${ProjectPrefix}-ec2-keypair

  EC2IAMRole:
    Type: 'AWS::IAM::Role'
    Properties:
      RoleName: !Sub ${ProjectPrefix}-ec2-role
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              Service: ec2.amazonaws.com
            Action: 'sts:AssumeRole'
      ManagedPolicyArns:
        - arn:aws:iam::aws:policy/AmazonEC2ReadOnlyAccess
        - arn:aws:iam::aws:policy/AmazonS3FullAccess
        - arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore


  EC2InstanceProfile:
    Type: 'AWS::IAM::InstanceProfile'
    Properties:
      Roles:
        - !Ref EC2IAMRole

  AirflowInstance:
    DependsOn:
      - EC2InstanceProfile
      - DagsBucket
    Type: AWS::EC2::Instance
    Properties:
      ImageId: !Ref LatestAmiId
      InstanceType: !Ref InstanceType
      KeyName: !Ref EC2KeyPair
      IamInstanceProfile: !Ref EC2InstanceProfile
      NetworkInterfaces:
        - DeviceIndex: "0"
          SubnetId: !Ref PublicSubnet
          GroupSet:
            - !Ref EC2SecurityGroup
      Tags:
        - Key: Name
          Value: !Sub ${ProjectPrefix}-airflow-instance
      UserData: {
                  "Fn::Base64": {"Fn::Join": ["",
                      ["#!/bin/bash\n",
                      "set -ex\n",
                      "mkdir /opt/airflow\n",
                      "cd /opt/airflow\n",                      
                      "echo -e \"sudo docker compose -f \\/opt\\/airflow\\/docker-compose.yaml down\nsudo docker compose -f \\/opt\\/airflow\\/docker-compose.yaml up -d\n\" > restart_airflow.sh\n",
                      "mkdir -p ./dags ./logs ./plugins\n",
                      "sudo chmod 777 -R ./logs \n",
                      "sudo chmod 777 -R ./dags \n",
                      "wget https://s3.amazonaws.com/mountpoint-s3-release/latest/x86_64/mount-s3.rpm\n",
                      "sudo yum install -y ./mount-s3.rpm\n",                       
                      "sudo mount-s3 --dir-mode 0766 --file-mode 0766 --allow-overwrite --allow-delete --allow-other --prefix dags/ ", {"Ref": "DagsBucket"}, " ./dags", "\n",
                      "echo mount-s3 service ready for dags folder\n",                                            
                      "sudo yum install -y docker\n",
                      "sudo service docker start\n",
                      "sudo usermod -a -G docker ec2-user\n",
                      "mkdir -p /usr/local/lib/docker/cli-plugins\n",
                      "curl -SL https://github.com/docker/compose/releases/download/v2.24.7/docker-compose-linux-x86_64 -o /usr/local/lib/docker/cli-plugins/docker-compose\n",
                      "chmod +x /usr/local/lib/docker/cli-plugins/docker-compose\n",
                      "echo docker compose has been installed\n",
                      "echo Airflow folders created\n",                      
                      "echo -e \"boto3\\npandas\\napache-airflow[amazon]\\ns3fs\\nscipy\\nairflow-provider-great-expectations\\napache-airflow-providers-fab\\n\" > requirements.txt \n",
                      "echo -e \"FROM apache/airflow:2.10.4-python3.12\\nCOPY requirements.txt .\\nUSER airflow\\nRUN pip install -r requirements.txt\\n\" > Dockerfile \n",
                      "curl -LfO 'https://airflow.apache.org/docs/apache-airflow/2.10.4/docker-compose.yaml'\n",
                      "sed -i \"s@image: \\${AIRFLOW_IMAGE_NAME:-apache\\/airflow:|version|}@# image: \\${AIRFLOW_IMAGE_NAME:-apache\\/airflow:|version|}@\" docker-compose.yaml\n",
                      "sed -i \"s|# build: .|build: .\\n  env_file:\\n    - path: .\\/.env\\n      required: true|\" docker-compose.yaml\n",
                      "sed -i \"s/AIRFLOW__CORE__LOAD_EXAMPLES: 'true'/AIRFLOW__CORE__LOAD_EXAMPLES: 'false'/\" docker-compose.yaml\n",
                      "sed -i \"s|# AIRFLOW_CONFIG: '\\/opt\\/airflow\\/config\\/airflow.cfg'|AIRFLOW_CONFIG: '\\/opt\\/airflow\\/config\\/airflow.cfg'|\" docker-compose.yaml\n",
                      "echo -e \"AIRFLOW_UID=$(id -u)\\nAIRFLOW_GID=0\" > .env\n",
                      "echo -e \"AIRFLOW__SCHEDULER__MIN_FILE_PROCESS_INTERVAL=5\\nAIRFLOW__SCHEDULER__DAG_DIR_LIST_INTERVAL=30\" >> .env\n",
                      "echo -e \"PYTHONDONTWRITEBYTECODE=''\\nPYTHONPATH=/opt/airflow/dags:${PYTHONPATH}\" >> .env\n",
                      "sudo docker compose up -d airflow-init\n",
                      "sudo docker compose up -d --build\n",                      
                      "echo Airflow service is running\n",
                      ]
                    ]
                  }
                }
  AirflowInstanceEIP:
    Type: "AWS::EC2::EIP"
    Properties:
      InstanceId: !Ref AirflowInstance


Outputs:
  AWSRegion:
    Description: This is the current AWS Region for this lab
    Value: !Sub ${AWS::Region}
  AWSAccount:
    Description: This is the current AWS Account for this lab
    Value: !Sub ${AWS::AccountId}
  VPCID:
    Description: This is the VPC ID for this Lab
    Value: !Ref VPC
  PublicSubnetID:
    Description: This is the Public Subnet A ID for this Lab
    Value: !Ref PublicSubnet  
  DagsBucket:
    Description: This is the S3 bucket for storing Apache Airflow Dags
    Value: !Ref DagsBucket
  RawDataBucket:
    Description: This is the S3 bucket for storing the extracted data
    Value: !Ref RawDataBucket
  AirflowDNS:
    Description: This is the DNS of the Airflow service
    Value: !Join [ ":", [!GetAtt AirflowInstance.PublicDnsName, !Ref AirflowPort]]
