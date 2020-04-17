import boto3
import json
import base64
import re
from urllib.parse import unquote_plus
from botocore.exceptions import ClientError
from botocore.client import Config


BUCKET_NAME = "kuceyeski-wcm-web-upload"
CONFIG_FILE_KEY = "config/ec2-launch-config.json"
USER_DATA_FILE_KEY = "config/user-data"
BUCKET_INPUT_DIR = "inputs"
BUCKET_OUTPUT_DIR = "outputs"

#RESULT_EMAIL_SENDER = "NeMo Keith <keith.jamison+nemo@gmail.com>"
RESULT_EMAIL_SENDER = "NeMo Notification <nemo-notification@med.cornell.edu>"
OUTPUT_EXPIRATION_STRING = "7 days"
OUTPUT_EXPIRATION_SECONDS = 604800

#note: nemo ami = ami-0cae8b732a1b5b582
#currently using KL3 for testing: ami-0d684e7eb59c59df3
def launch_instance(EC2, config, user_data):
    tag_specs = [{}]
    tag_specs[0]['ResourceType'] = 'instance'
    tag_specs[0]['Tags'] = config['set_new_instance_tags']
    
    ec2_response = EC2.run_instances(
        ImageId=config['ami'],  # ami-0123b531fc646552f
        InstanceType=config['instance_type'],   # t2.nano
        KeyName=config['ssh_key_name'],  # ambar-default
        IamInstanceProfile=config['iam_instance_profile'],
        BlockDeviceMappings=config['block_device_mapping'],
        InstanceInitiatedShutdownBehavior=config['instance_initiated_shutdown_behavior'],
        MinCount=1,
        MaxCount=1,
        SecurityGroupIds=config['security_group_ids'],  # sg-08b6b31110601e924
        TagSpecifications=tag_specs,
        # UserData=base64.b64encode(user_data).decode("ascii")
        UserData=user_data
    )
    
    new_instance_resp = ec2_response['Instances'][0]
    instance_id = new_instance_resp['InstanceId']
    # print(f"[DEBUG] Full ec2 instance response data for '{instance_id}': {new_instance_resp}")
    
    return (instance_id, new_instance_resp)


def dict2json(mydict):
    jsonresult=[]
    for k,v in mydict.items():
        jsonresult+=[{'Key':k, 'Value':v}]
    return jsonresult

def json2dict(myjson):
    dictresult={}
    for i in myjson:
        dictresult[i['Key']]=i['Value']
    return dictresult
    
def fileSizeString(numbytes):
    if numbytes < 1024:
        return "%g B" % (numbytes)
    elif numbytes < 1024*1024:
        return "%g KB" % (numbytes/1024)
    elif numbytes < 1024*1024*1024:
        return "%g MB" % (numbytes/(1024*1024))
    else:
        return "%g GB" % (numbytes/(1024*1024*1024))

def durationToString(numseconds):
    newseconds = int(numseconds) % 60
    newminutes = int(numseconds / 60) % 60
    newhours = int(numseconds / (60*60)) % 24
    newdays = int(numseconds / (60*60*24))
    newstring=""
    if newdays > 0:
        newstring+="%gd" % (newdays)
    if newhours > 0:
        newstring+="%gh" % (newhours)
    if newminutes > 0:
        newstring+="%gm" % (newminutes)
    if newseconds > 0:
        newstring+="%gs" % (newseconds)
    return newstring
    
def sendCompletionEmail(useremail, duration_string, filesize_string, downloadurl, origfilename, s3region, status, outputimg_name, outputimg_url):
    SENDER = RESULT_EMAIL_SENDER
    RECIPIENT = useremail

    AWS_REGION = s3region
    if status == "success":
        SUBJECT = "NeMo processing complete!"
    elif status == "error":
        SUBJECT = "NeMo processing error"


    # The email body for recipients with non-HTML email clients.
    BODY_TEXT = ("Your NeMo output for %s is ready!\r\n"
             "You can download the results here: %s\r\n"
             "Output file is %s, and processing took %s\r\n"
             "\r\nThis link will expire in %s"
            ) % (origfilename, downloadurl, filesize_string, duration_string, OUTPUT_EXPIRATION_STRING)
            
    imgtext=""
    for i in range(len(outputimg_name)):
        imgtext+="<p class='imgdiv'>%s<br/><img src='%s' alt='%s'/></p>\n" % (outputimg_name[i],outputimg_url[i],outputimg_name[i])
    
    # The HTML body of the email.
    BODY_HTML = """<html>
<head><style type='text/css'>.imgdiv {border: solid black 1pt; display: inline-block; padding: 10pt}</style></head>
<body style='font-family: sans-serif'>
  <h1>Your NeMo output for %s is ready!</h1>
  <p>You can download your results here:
    <a href='%s'>[download link]</a></p>
  <p>Output file size is %s, and processing took %s</p>
  <p>This link will expire in %s</p>
  <hr/><h2>Result images:</h2>%s
</body>
</html>
            """ % (origfilename, downloadurl, filesize_string, duration_string, OUTPUT_EXPIRATION_STRING, imgtext)

    CHARSET = "UTF-8"

    # Create a new SES resource and specify a region.
    client = boto3.client('ses',region_name=AWS_REGION)

    # Try to send the email.
    try:
        #Provide the contents of the email.
        response = client.send_email(
            Destination={
                'ToAddresses': [
                    RECIPIENT,
                ],
            },
            Message={
                'Body': {
                    'Html': {
                        'Charset': CHARSET,
                        'Data': BODY_HTML,
                    },
                    'Text': {
                        'Charset': CHARSET,
                        'Data': BODY_TEXT,
                    },
                },
                'Subject': {
                    'Charset': CHARSET,
                    'Data': SUBJECT,
                },
            },
            Source=SENDER,
            # If you are not using a configuration set, comment or delete the
            # following line
            #ConfigurationSetName=CONFIGURATION_SET,
        )
    # Display an error if something goes wrong.	
    except ClientError as e:
        print(e.response['Error']['Message'])
    else:
        print("Email sent! Message ID:"),
        print(response['MessageId'])
    
def lambda_handler(raw_event, context):
    print(f"Received raw event: {raw_event}")
    # event = raw_event['Records']

    for record in raw_event['Records']:
        bucket = record['s3']['bucket']['name']
        print(f"Triggering S3 Bucket: {bucket}")
        key = unquote_plus(record['s3']['object']['key'])
        print(f"Triggering key in S3: {key}")
        
        S3 = boto3.client('s3', config=Config(signature_version='s3v4'))
        
        #get the email address and timestamp tags we added to the file upload
        s3filetags=S3.get_object_tagging(Bucket=bucket, Key=key)
        s3tagdict=json2dict(s3filetags['TagSet'])
        s3tagdict['md5']=S3.head_object(Bucket=bucket, Key=key)['ETag'].strip('"')
        s3tagdict['s3path']=bucket+"/"+key

        if not 'email' in s3tagdict:
            #this is not a valid input or final result file (might be an image we uploaded to the bucket)
            continue
        
        # get config from config file stored in S3
        result = S3.get_object(Bucket=BUCKET_NAME, Key=CONFIG_FILE_KEY)
        ec2_config = json.loads(result["Body"].read().decode())
        
        # launch new EC2 instance if necessary
        if bucket == BUCKET_NAME and key.startswith(f"{BUCKET_INPUT_DIR}/"):
            #add s3 file tags to the instance tags
            ec2_config['set_new_instance_tags']+=dict2json(s3tagdict)
            print(f"Config from S3: {ec2_config}")

        
            ec2_filters = [
                {
                    'Name': f"tag:{ec2_config['filter_tag_key']}",
                    'Values':[ ec2_config['filter_tag_value'] ]
                },
                {
                    'Name': f"tag:s3path",
                    'Values':[ s3tagdict['s3path'] ]
                }
            ]

            EC2 = boto3.client('ec2', region_name=ec2_config['region'])
        
            print("[INFO] Describing EC2 instances with target tags...")
            resp = EC2.describe_instances(Filters=ec2_filters)
            # print(f"[DEBUG] describe_instances response: {resp}")

            if resp["Reservations"] is not []:    # at least one instance with target tags was found
                for reservation in resp["Reservations"] :
                    for instance in reservation["Instances"]:
                        print(f"[INFO] Found '{instance['State']['Name']}' instance '{ instance['InstanceId'] }'"
                            f" having target tags: {instance['Tags']} ")

                        if instance['State']['Code'] == 16: # instance has target tags AND also is in running state
                            print(f"[INFO] instance '{ instance['InstanceId'] }' is already running: so not launching any more instances")
                            return {
                                "newInstanceLaunched": False,
                                "old-instanceId": instance['InstanceId'],
                                "new-instanceId": ""
                            }

            print("[INFO] Could not find even a single running instance matching the desired tag, launching a new one")

            # retrieve EC2 user-data for launch
            result = S3.get_object(Bucket=BUCKET_NAME, Key=USER_DATA_FILE_KEY)
            user_data = result["Body"].read()
            print(f"UserData from S3: {user_data}")

            result = launch_instance(EC2, ec2_config, user_data)
            print(f"[INFO] LAUNCHED EC2 instance-id '{result[0]}'")
            # print(f"[DEBUG] EC2 launch_resp:\n {result[1]}")
            return {
                "newInstanceLaunched": True,
                "old-instanceId": "",
                "new-instanceId": result[0]
            }

        # terminate all tagged EC2 instances
        if bucket == BUCKET_NAME and key.startswith(f"{BUCKET_OUTPUT_DIR}/"):
            s3region=record['awsRegion']
            
            #wr3720_2014.lesion_nemo_output.zip
            #wr3720_2014.lesion_nemo_output_glassbrain_lesion_orig.png
            
            outputkey_prefix=re.sub('\.zip$','',key)
            outputfiles_response=S3.list_objects(Bucket=bucket,Prefix=outputkey_prefix)
            outputimg_key=[r['Key'] for r in outputfiles_response['Contents'] if r['Key'].endswith(".png")]
            
            outputimg_name=[s.split("/")[-1] for s in outputimg_key]
            outputimg_url=[S3.generate_presigned_url(ClientMethod='get_object', Params={'Bucket':bucket,'Key':k}, ExpiresIn=OUTPUT_EXPIRATION_SECONDS) for k in outputimg_key]
            
            #generate a link that will expire in 1 week (maximum)
            downloadurl=S3.generate_presigned_url(ClientMethod='get_object', Params={'Bucket':bucket,'Key':key}, ExpiresIn=OUTPUT_EXPIRATION_SECONDS)
            downloadurl_unsigned="https://%s.s3.amazonaws.com/%s" % (bucket,key)
            duration_string=durationToString(float(s3tagdict['duration']))
            downloadsize_string=fileSizeString(int(record['s3']['object']['size']))
            
            print(f"Output email: {s3tagdict['email']}")
            print(f"Output duration: {s3tagdict['duration']}")
            print(f"Output status: {s3tagdict['status']}")
            print(f"Output origfilename: {s3tagdict['origfilename']}")
            print(f"Output duration string: {duration_string}")
            print(f"Output file region: {s3region}")
            print(f"Output file size: {downloadsize_string}")
            print(f"Output file URL: {downloadurl}")
            [print(f"Output image: %s" % (s)) for s in outputimg_name]
            
            sendCompletionEmail(s3tagdict['email'], duration_string, downloadsize_string, downloadurl, s3tagdict['origfilename'], s3region, s3tagdict['status'], outputimg_name, outputimg_url)
            
            return {}
            