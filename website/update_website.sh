#!/bin/bash

SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

WEBSITE_S3=kuceyeski-wcm-web
NEMODATA_S3=kuceyeski-wcm-temp/kwj2001/nemo2

aws s3 cp ${SCRIPTDIR}/../nemo_lesion_to_chaco.py s3://${WEBSITE_S3}/nemo_scripts/
aws s3 cp ${SCRIPTDIR}/../nemo_save_average_glassbrain.py s3://${WEBSITE_S3}/nemo_scripts/
aws s3 sync ${SCRIPTDIR}/config s3://${WEBSITE_S3}/config

#aws s3 sync ${SCRIPTDIR}/atlases s3://${WEBSITE_S3}/nemo_atlases
aws s3 sync ${SCRIPTDIR}/atlases s3://${NEMODATA_S3}/nemo_atlases

aws s3 cp ${SCRIPTDIR}/upload.html s3://${WEBSITE_S3}/
aws s3 cp ${SCRIPTDIR}/upload_internal.html s3://${WEBSITE_S3}/
aws s3 cp ${SCRIPTDIR}/uploader.js s3://${WEBSITE_S3}/
aws s3 cp ${SCRIPTDIR}/styles.css s3://${WEBSITE_S3}/
aws s3 sync ${SCRIPTDIR}/images s3://${WEBSITE_S3}/images/

echo "Version info:"
jq --raw-output '.' ${SCRIPTDIR}/config/nemo-version.json

echo
echo "Reminder: Need to manually copy/paste contents of s3-lambda.py into the AWS Lambda config!"
