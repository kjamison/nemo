import boto3
import json
import base64
import re
from urllib.parse import unquote_plus
from botocore.exceptions import ClientError
from botocore.client import Config
import os
import time

CONFIG_BUCKET_NAME = "kuceyeski-wcm-web"
UPLOAD_BUCKET_NAME = "kuceyeski-wcm-web-upload"
CONFIG_FILE_KEY = "config/ec2-launch-config.json"
USER_DATA_FILE_KEY = "config/user-data"
USER_DATA_FILE_KEY_DEBUG = "config/user-data-debug"
BUCKET_INPUT_DIR = "inputs"
BUCKET_OUTPUT_DIR = "outputs"

NEMO_DATA_STORAGE_LOCATION = "kuceyeski-wcm-temp/kwj2001/nemo2"

RESULT_EMAIL_SENDER = "NeMo Notification <nemo-notification@med.cornell.edu>"
OUTPUT_EXPIRATION_STRING = "7 days"
OUTPUT_EXPIRATION_SECONDS = 604800


#note: these are set in the "Environment Variables" section of the AWS Lambda configuration console for this script
#IAM user info needed for URL signing
IAM_USER_KEY=os.environ['IAM_USER_KEY']
IAM_USER_SECRET=os.environ['IAM_USER_SECRET']
COCO_PASSWORD=os.environ['COCO_PASSWORD']


#note: 600gb nemo ami = ami-0cae8b732a1b5b582
#currently using KL3 for testing: ami-0d684e7eb59c59df3
#new smaller nemo ami = ami-0e7f958090b609397
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


def dict2jsonkeyval(mydict):
    jsonresult=[]
    for k,v in mydict.items():
        jsonresult+=[{'Key':k, 'Value':v}]
    return jsonresult

def jsonkeyval2dict(myjson):
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

def sendCompletionEmail(useremail, duration_string, filesize_string, downloadurl, downloadfilename, origfilename, s3region, status, outputimg_list, ziplist_string, submittime_string, result_location):
    SENDER = RESULT_EMAIL_SENDER
    RECIPIENT = useremail

    AWS_REGION = s3region
    if status == "success":
        SUBJECT = "NeMo processing complete! [%s]" % (downloadfilename)
    elif status == "error":
        SUBJECT = "NeMo processing error! [%s]" % (downloadfilename)

    if result_location:
        linkstring="Data has been copied to %s" % (result_location)
        expirestring=""
        linkstring_html="""<p>Data has been copied to:
    %s</p>""" % (result_location)
        expirestring_html=""
    else:
        linkstring="You can download the results here: %s\r\n" % (downloadurl)
        expirestring="\r\nThis link will expire in %s" % (OUTPUT_EXPIRATION_STRING)
        linkstring_html="""<p>You can download your results here:
    <a href='%s'>[%s]</a></p>""" % (downloadurl, downloadfilename)
        expirestring_html="<p>This link will expire in %s</p>" % (OUTPUT_EXPIRATION_STRING)
        
    # The email body for recipients with non-HTML email clients.
    BODY_TEXT = ("Your NeMo output for %s is ready!\r\n"
             "%s"
             "Output file is %s. Job submitted at %s and processing took %s\r\n"
             "%s"
            ) % (origfilename, linkstring, filesize_string, submittime_string, duration_string, expirestring)
            
    imgtext=""
    for i in range(len(outputimg_list)):
        if outputimg_list[i]['label']:
            imgtext+="<div class='imgdiv'><h4>%s [%s]</h4><br/><img src='%s' alt='%s'/></div><br>\n" % (outputimg_list[i]['label'],outputimg_list[i]['name'],outputimg_list[i]['url'],outputimg_list[i]['name'])
        else:
            imgtext+="<div class='imgdiv'><h4>%s</h4><br/><img src='%s' alt='%s'/></div><br>\n" % (outputimg_list[i]['name'],outputimg_list[i]['url'],outputimg_list[i]['name'])
    
    ziplisttext=""
    if ziplist_string:
        ziplisttext="<div class='imgdiv'><h3>Contents of %s</h3><pre>%s</pre></div>" % (downloadfilename,ziplist_string)
    
    # The HTML body of the email.
    BODY_HTML = """<html>
<head><style type='text/css'>.imgdiv {border: solid black 1pt; display: inline-block; padding: 10pt; margin: 10pt;}</style></head>
<body style='font-family: sans-serif'>
  <h1>Your NeMo output for %s is ready!</h1>
  %s
  <p>Output file size is %s. Job submitted at %s and processing took %s</p>
  %s
  <p>Please visit our <a href="https://github.com/kjamison/nemo#code-examples-for-parsing-outputs">github</a> documentation for more information about output files and example scripts for converting or manipulating outputs.</p>
  <hr/><h2>Output summary:</h2>%s%s
</body>
</html>
            """ % (origfilename, linkstring_html, filesize_string, submittime_string, duration_string, expirestring_html, imgtext, ziplisttext)

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
                'BccAddresses': [
                    SENDER,
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
        
    return BODY_HTML
        
def lambda_handler(raw_event, context):
    #print(f"Received raw event: {raw_event}")
    # event = raw_event['Records']

    for record in raw_event['Records']:
        bucket = record['s3']['bucket']['name']
        key = unquote_plus(record['s3']['object']['key'])
        print(f"Triggering S3 object: {bucket}/{key}")
        
        S3 = boto3.client('s3')
        
        #get the email address and timestamp tags we added to the file upload
        s3filetags=S3.get_object_tagging(Bucket=bucket, Key=key)
        s3tagdict=jsonkeyval2dict(s3filetags['TagSet'])
        s3tagdict['md5']=S3.head_object(Bucket=bucket, Key=key)['ETag'].strip('"')
            
        if not 'email' in s3tagdict:
            #this is not a valid input or final result file (might be an image we uploaded to the bucket)
            continue

        ############################################################################
        # input handler
        #
        # launch new EC2 instance if necessary
        if bucket == UPLOAD_BUCKET_NAME and key.startswith(f"{BUCKET_INPUT_DIR}/"):
            s3tagdict['s3path']=bucket+"/"+key
            s3tagdict['s3nemoroot']=NEMO_DATA_STORAGE_LOCATION
            s3tagdict['s3configbucket']=CONFIG_BUCKET_NAME
            
            #remove this if found since it shouldn't be copied over from ['outputlocation'] before we've checked the password
            if 's3direct_outputlocation' in s3tagdict:
                del s3tagdict['s3direct_outputlocation']
                
            #check if password was entered and matches
            if 'coco_password' in s3tagdict: 
                if s3tagdict['coco_password'] == COCO_PASSWORD:
                    if 'outputlocation' in s3tagdict:
                        s3tagdict['s3direct_outputlocation']=s3tagdict['outputlocation']
                    S3.put_object(Bucket=bucket, Key=key+s3tagdict['status_suffix'], Body=b'success', Tagging='password_status=success')
                else:
                    print(f"Bad password!")
                    submittime=int(s3tagdict['unixtime'])
                    submittime_string=time.strftime('%Y-%m-%d %H:%M:%S %Z',time.gmtime(int(submittime/1000)))
                    #S3.delete_object(Bucket=bucket, Key=key)
                    S3.put_object(Bucket=bucket, Key=key+s3tagdict['status_suffix'], Body=b'error', Tagging='password_status=error')
                    return
                del s3tagdict['coco_password']
            
            if 'outputlocation' in s3tagdict:
                del s3tagdict['outputlocation']
            
            # get config from config file stored in S3
            result = S3.get_object(Bucket=CONFIG_BUCKET_NAME, Key=CONFIG_FILE_KEY)
            ec2_config = json.loads(result["Body"].read().decode())
        
            #add s3 file tags to the instance tags
            ec2_config['set_new_instance_tags']+=dict2jsonkeyval(s3tagdict)
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
            if 'debug' in s3tagdict and s3tagdict['debug'].lower()=="true":
                #read debug-mode user-data file
                result = S3.get_object(Bucket=CONFIG_BUCKET_NAME, Key=USER_DATA_FILE_KEY_DEBUG)
            else:
                result = S3.get_object(Bucket=CONFIG_BUCKET_NAME, Key=USER_DATA_FILE_KEY)
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

        ############################################################################
        # output handler
        #
        # send result email
        if bucket == UPLOAD_BUCKET_NAME and key.startswith(f"{BUCKET_OUTPUT_DIR}/"):
            s3region=record['awsRegion']
            
            #create a new S3 client using the IAM user that can create 7-day presigned URLs
            S3_as_user=boto3.client('s3', config=Config(signature_version='s3v4'), aws_access_key_id=IAM_USER_KEY, aws_secret_access_key=IAM_USER_SECRET)
            
            #wr3720_2014.lesion_nemo_output.zip
            #wr3720_2014.lesion_nemo_output_glassbrain_lesion_orig.png
            
            #outputkey_prefix=re.sub('\.zip$','',key)
            outputkey_prefix="/".join(key.split("/")[:-1])+"/"
            outputfiles_response=S3.list_objects(Bucket=bucket,Prefix=outputkey_prefix)
            outputfiles_list=[r['Key'] for r in outputfiles_response['Contents']]
            outputimg_key=[f for f in outputfiles_list if f.endswith(".png")]
            outputimg_name=[s.split("/")[-1] for s in outputimg_key]
            
            ##############################
            # hacky section to give pretty names to specific output images (and reorder them as desired)
            outputimg_list=[]
            for i in range(len(outputimg_name)):
                newlabel=""
                newindex=-1
                if re.match('.+lesion_orig\.png',outputimg_name[i]):
                    newlabel='Input lesion mask'
                    newindex=0
                elif re.match('.+chaco(vol_.+)?_smooth.*_mean\.png',outputimg_name[i]):
                    newlabel='mean(smoothed ChaCo)'
                    newindex=2
                elif re.match('.+chaco(vol_.+)?_mean\.png',outputimg_name[i]):
                    newlabel='ChaCo mean'
                    newindex=1
                elif re.match('.+lesion_orig_listmean\.png',outputimg_name[i]):
                    newlabel='listmean(Input lesion masks)'
                    newindex=0
                elif re.match('.+chaco(vol_.+)?_smooth.*_listmean\.png',outputimg_name[i]):
                    newlabel='listmean(mean(smoothed ChaCo))'
                    newindex=2
                elif re.match('.+chaco(vol_.+)?_listmean\.png',outputimg_name[i]):
                    newlabel='listmean(ChaCo mean)'
                    newindex=1

                if newindex >= 0:
                    newurl=S3_as_user.generate_presigned_url(ClientMethod='get_object', Params={'Bucket':bucket,'Key':outputimg_key[i]}, ExpiresIn=OUTPUT_EXPIRATION_SECONDS)
                    outputimg_list.append({'name':outputimg_name[i], 'key':outputimg_key[i], 'label': newlabel, 'index': newindex, 'url': newurl})
                
            #sort by new index
            outputimg_list = [outputimg_list[i] for i in sorted(range(len(outputimg_list)), key=lambda k: outputimg_list[k]['index'])]

            ##############################
            outputfile_uploadjson_key=[f for f in outputfiles_list if f.endswith("_upload_info.json")]
            if len(outputfile_uploadjson_key) > 0:
                uploadjson_key=outputfile_uploadjson_key[0]
                uploadjson_result = S3.get_object(Bucket=bucket, Key=uploadjson_key)
                uploadinfo = json.loads(uploadjson_result["Body"].read().decode())
                print(f"Upload info {uploadjson_key}:\n{uploadinfo}")
            else:
                [print(s) for s in outputfiles_list]
                uploadinfo=s3tagdict
                            
            if 'outputfile_key' in uploadinfo:
                outputfile_key=uploadinfo['outputfile_key']
            else:
                outputfile_key=key
            
            ##############################
            ziplist_string=""
            outputfile_ziplist_key=[r['Key'] for r in outputfiles_response['Contents'] if r['Key'].endswith("_ziplist.txt")]
            if len(outputfile_ziplist_key) > 0:
                ziplist_key=outputfile_ziplist_key[0]
                ziplist_result = S3.get_object(Bucket=bucket, Key=ziplist_key)
                ziplist_string = ziplist_result["Body"].read().decode()
                print(f"Output ziplist ({ziplist_key}):\n{ziplist_string}")
            
            #generate a link that will expire in 1 week (maximum)
            downloadurl=S3_as_user.generate_presigned_url(ClientMethod='get_object', Params={'Bucket':bucket,'Key':outputfile_key}, ExpiresIn=OUTPUT_EXPIRATION_SECONDS)
            downloadurl_unsigned="https://%s.s3.amazonaws.com/%s" % (bucket,outputfile_key)
            duration_string=durationToString(float(uploadinfo['duration']))
            if 'outputsize' in uploadinfo:
                downloadsize_string=uploadinfo['outputsize']
            else:
                #downloadsize_string=fileSizeString(int(record['s3']['object']['size']))
                #get the file size from outputfile_key instead
                downloadsize_string=fileSizeString(int(S3.head_object(Bucket=bucket, Key=outputfile_key)["ContentLength"]))
                
            if 'outputsize_unzipped' in uploadinfo and uploadinfo['outputsize_unzipped']:
                downloadsize_string+=" ("+uploadinfo['outputsize_unzipped']+" unzipped)"
            
            downloadfilename=outputfile_key.split("/")[-1]
            
            if 'resultlocation' in uploadinfo:
                result_location=uploadinfo['resultlocation']
            else:
                result_location=None
             
            #TODO: relay info about how many files were uploaded, selected, successfully processed
            #TODO: may need to exclude some subjects still!
            
            #timestamp is unix epoch time with milliseconds, so make sure to divide those off
            submittime=int(uploadinfo['submittime'])
            submittime_string=time.strftime('%Y-%m-%d %H:%M:%S %Z',time.gmtime(int(submittime/1000)))
            
            print(f"Output email: {uploadinfo['email']}")
            print(f"Output duration: {uploadinfo['duration']}")
            print(f"Output status: {uploadinfo['status']}")
            print(f"Output origfilename: {uploadinfo['origfilename']}")
            print(f"Output submittime: {submittime_string}")
            print(f"Output filename: {downloadfilename}")
            print(f"Output duration string: {duration_string}")
            print(f"Output file region: {s3region}")
            print(f"Output file size: {downloadsize_string}")
            print(f"Output file URL: {downloadurl}")
            if result_location:
                print(f"Result location (s3 direct copy): {result_location}")
            [print(f"Output image: %s" % (s)) for s in outputimg_name]

            
            outputhtml=sendCompletionEmail(uploadinfo['email'], duration_string, downloadsize_string, downloadurl, downloadfilename, uploadinfo['origfilename'], s3region, uploadinfo['status'], outputimg_list, ziplist_string, submittime_string, result_location)
            
            return {}
            