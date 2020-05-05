#!/bin/bash

SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

aws s3 cp ${SCRIPTDIR}/../nemo_lesion_to_chaco.py s3://kuceyeski-wcm-web-upload/nemo_scripts/
aws s3 cp ${SCRIPTDIR}/../nemo_save_average_glassbrain.py s3://kuceyeski-wcm-web-upload/nemo_scripts/
aws s3 sync ${SCRIPTDIR}/config s3://kuceyeski-wcm-web-upload/config

aws s3 cp ${SCRIPTDIR}/upload.html s3://kuceyeski-wcm-web/
aws s3 cp ${SCRIPTDIR}/upload_internal.html s3://kuceyeski-wcm-web/
aws s3 cp ${SCRIPTDIR}/uploader.js s3://kuceyeski-wcm-web/
aws s3 cp ${SCRIPTDIR}/styles.css s3://kuceyeski-wcm-web/

echo "Reminder: Need to manually copy/paste contents of s3-lambda.py into the AWS Lambda config!"
