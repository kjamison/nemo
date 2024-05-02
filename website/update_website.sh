#!/bin/bash

SCRIPTDIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

WEBSITE_S3=kuceyeski-wcm-web
NEMODATA_S3=kuceyeski-wcm-temp/kwj2001/nemo2

BACKUP_TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
WEBSITE_S3_BACKUP_DIR=${WEBSITE_S3}/nemo_website_backups/backup_${BACKUP_TIMESTAMP}

function backup_and_upload {
    localfile=$1
    s3dest=$2
    repstr=$3
    
    if [[ ${s3dest} == */ ]]; then
        #destination is a folder
        s3localfile=$(basename ${localfile})
        s3dest=$(echo ${s3dest} | sed -E 's#/$##')
    else
        #destination is a filename
        s3localfile=$(basename ${s3dest})
        s3dest=$(dirname ${s3dest})
        #destination is a file
    fi
    #copy current version to backup location
    aws s3 cp ${s3dest}/${s3localfile} s3://${WEBSITE_S3_BACKUP_DIR}/${s3localfile}
    
    if [ -z ${repstr} ]; then
        aws s3 cp ${localfile} ${s3dest}/${s3localfile}
    else
        r=$(date '+%s')
        tmpfile=$(dirname $localfile)/tmp${r}_$(basename $localfile)
        sed -E 's#'${repstr}'[^"]*#'${repstr}'?r='$r'#' ${localfile} > ${tmpfile} && aws s3 cp ${tmpfile} ${s3dest}/${s3localfile} && rm -f ${tmpfile}
    fi
    #now upload new version
    
}

function randupload {
    localfile=$1
    s3dest=$2
    repstr=$3
    if [[ ${s3dest} == */ ]]; then
        s3dest=${s3dest}$(basename $localfile)
    fi
    #r=$RANDOM$RANDOM$RANDOM
    r=$(date '+%s')
    tmpfile=$(dirname $localfile)/tmp${r}_$(basename $localfile)
    sed -E 's#'${repstr}'[^"]*#'${repstr}'?r='$r'#' ${localfile} > ${tmpfile} && aws s3 cp ${tmpfile} ${s3dest} && rm -f ${tmpfile}
}


#echo "CURRENTLY SKIPPING" 
backup_and_upload ${SCRIPTDIR}/../nemo_lesion_to_chaco.py s3://${WEBSITE_S3}/nemo_scripts/
backup_and_upload ${SCRIPTDIR}/../nemo_save_average_glassbrain.py s3://${WEBSITE_S3}/nemo_scripts/
backup_and_upload ${SCRIPTDIR}/../nemo_save_average_matrix_figure.py s3://${WEBSITE_S3}/nemo_scripts/
backup_and_upload ${SCRIPTDIR}/../nemo_save_average_graphbrain.py s3://${WEBSITE_S3}/nemo_scripts/
backup_and_upload ${SCRIPTDIR}/../chacoconn_to_nemosc.py s3://${WEBSITE_S3}/nemo_scripts/
backup_and_upload ${SCRIPTDIR}/../chacovol_to_nifti.py s3://${WEBSITE_S3}/nemo_scripts/
backup_and_upload ${SCRIPTDIR}/../dilate_parcellation.py s3://${WEBSITE_S3}/nemo_scripts/
backup_and_upload ${SCRIPTDIR}/../check_input_dimensions.py s3://${WEBSITE_S3}/nemo_scripts/

backup_and_upload ${SCRIPTDIR}/uploader.js s3://${WEBSITE_S3}/
backup_and_upload ${SCRIPTDIR}/styles.css s3://${WEBSITE_S3}/

aws s3 sync ${SCRIPTDIR}/config s3://${WEBSITE_S3}/config

#aws s3 sync ${SCRIPTDIR}/atlases s3://${WEBSITE_S3}/nemo_atlases
aws s3 sync ${SCRIPTDIR}/atlases s3://${NEMODATA_S3}/nemo_atlases

#aws s3 cp ${SCRIPTDIR}/upload.html s3://${WEBSITE_S3}/
#aws s3 cp ${SCRIPTDIR}/upload_internal.html s3://${WEBSITE_S3}/
#replace src="./uploader.js" with src="./uploader.js?r=<randomvalue>" so the javascript doesn't get cached
backup_and_upload ${SCRIPTDIR}/upload.html s3://${WEBSITE_S3}/ "uploader.js"
backup_and_upload ${SCRIPTDIR}/upload_internal.html s3://${WEBSITE_S3}/ "uploader.js"
backup_and_upload ${SCRIPTDIR}/index.html s3://${WEBSITE_S3}/nemo/

aws s3 sync ${SCRIPTDIR}/images s3://${WEBSITE_S3}/images/

echo "Version info:"
jq --raw-output '.' ${SCRIPTDIR}/config/nemo-version.json

echo
echo "Reminder: Need to manually copy/paste contents of s3-lambda.py into the AWS Lambda config!"
