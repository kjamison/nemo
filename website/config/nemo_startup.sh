#!/bin/bash

#dont want exit on error because we wont terminate!
#set -e 

starttime=$(date +%s)

set -x

if [ -e $HOME/fsl ]; then
        export FSLDIR=$HOME/fsl
        export PATH=$FSLDIR/bin:$PATH
fi

export PATH=/home/ubuntu/anaconda3/bin:$PATH
export PATH=/home/ubuntu/bin:$PATH

env

###################################
NEMODIR=${HOME}/nemo2
mkdir -p ${NEMODIR}
###################################
instanceid=$(curl -sf http://169.254.169.254/latest/meta-data/instance-id)
region=$(curl --silent --fail http://169.254.169.254/latest/dynamic/instance-identity/document/ | grep region | cut -d\" -f4)
aws ec2 describe-tags --region $region --filter "Name=resource-id,Values=$instanceid" > $HOME/nemo_tags.txt

s3path=$(jq --raw-output '.Tags[] | select(.Key=="s3path") | .Value' $HOME/nemo_tags.txt)
nemo_version=$(jq --raw-output '.Tags[] | select(.Key=="nemo_version") | .Value' $HOME/nemo_tags.txt)
s3nemoroot=$(jq --raw-output '.Tags[] | select(.Key=="s3nemoroot") | .Value' $HOME/nemo_tags.txt)
origfilename=$(jq --raw-output '.Tags[] | select(.Key=="filename") | .Value' $HOME/nemo_tags.txt)
origtimestamp=$(jq --raw-output '.Tags[] | select(.Key=="timestamp") | .Value' $HOME/nemo_tags.txt)
origtimestamp_unix=$(jq --raw-output '.Tags[] | select(.Key=="unixtime") | .Value' $HOME/nemo_tags.txt)
email=$(jq --raw-output '.Tags[] | select(.Key=="email") | .Value' $HOME/nemo_tags.txt)
output_allref=$(jq --raw-output '.Tags[] | select(.Key=="output_allref") | .Value' $HOME/nemo_tags.txt | tr "[A-Z]" "[a-z]")
do_smoothing=$(jq --raw-output '.Tags[] | select(.Key=="smoothing") | .Value' $HOME/nemo_tags.txt)
do_siftweights=$(jq --raw-output '.Tags[] | select(.Key=="siftweights") | .Value' $HOME/nemo_tags.txt)
smoothfwhm=$(jq --raw-output '.Tags[] | select(.Key=="smoothfwhm") | .Value' $HOME/nemo_tags.txt)
s3direct_outputlocation=$(jq --raw-output '.Tags[] | select(.Key=="s3direct_outputlocation") | .Value' $HOME/nemo_tags.txt)
status_suffix=$(jq --raw-output '.Tags[] | select(.Key=="status_suffix") | .Value' $HOME/nemo_tags.txt)

#parcellation:
#provide a single nifti file, or a set of them?, or a name for one of our preset ones

smoothfwhm=$(echo $smoothfwhm 6 | awk '{print $1}')

inputbucket=$(echo $s3path | awk -F/ '{print $1}')
outputbucket=${inputbucket}

inputfile_maxcount=10
unzipdir=

#################################
if [ "x${s3direct_outputlocation}" != "x" ]; then
    do_s3direct=1
    inputfile_maxcount=0
fi
#################################
s3filename=$(basename $s3path)

s3filename_noext=$(echo ${s3filename} | sed -E 's/(\.nii|\.nii\.gz|\.zip|\.tar|\.tar\.gz)$//i')
origfilename_noext=$(echo ${origfilename} | sed -E 's/(\.nii|\.nii\.gz|\.zip|\.tar|\.tar\.gz)$//i')

aws s3 cp s3://${s3path} $HOME/${s3filename}

s3lower=$(echo $s3filename | tr "[A-Z]" "[a-z]")

case ${s3lower} in 
    *.nii|*.nii.gz)
        inputtype="nifti"
        unzipdir=${HOME}/nemo_input_${s3filename_noext}
        mkdir -p ${unzipdir}
        cp -f $HOME/${s3filename} ${unzipdir}/${origfilename}
        ;;
        
    *.zip)
        inputtype="zip"
        
        #echo "zip not supported"
        #exit 1
        unzipdir=${HOME}/nemo_unzip_${s3filename_noext}
        mkdir -p ${unzipdir}
        (cd ${unzipdir} && unzip -j ${HOME}/${s3filename})
        ;;
    *.tar)
        inputtype="tar"
        #echo "tar not supported"
        #exit 1
        unzipdir=${HOME}/nemo_unzip_${s3filename_noext}
        mkdir -p ${unzipdir}
        (cd ${unzipdir} && tar -xf ${HOME}/${s3filename} --transform='s#.*\/##')
        ;;
    *.tar.gz)
        inputtype="tgz"
        #echo "tar.gz not supported"
        #exit 1
        unzipdir=${HOME}/nemo_unzip_${s3filename_noext}
        mkdir -p ${unzipdir}
        (cd ${unzipdir} && tar -xzf ${HOME}/${s3filename} --transform='s#.*\/##')
        ;;
    *)
esac

inputfile_listfile=${HOME}/inputfiles.txt
inputfile_count_orig=
inputfile_count=
if [ -d "${unzipdir}" ]; then
    #delete all but the first N files
    find ${unzipdir}/ -type f | grep -iE '\.nii(\.gz)?$' | sort > ${inputfile_listfile}.tmp
    if [ "${inputfile_maxcount}" = "0" ]; then
        cp -f ${inputfile_listfile}.tmp ${inputfile_listfile}
    else
        cat ${inputfile_listfile}.tmp | head -n ${inputfile_maxcount} > ${inputfile_listfile}
    fi
    inputfile_count_orig=$(cat ${inputfile_listfile}.tmp | wc -l)
    inputfile_count=$(cat ${inputfile_listfile} | wc -l)
    rm -f ${HOME}/${s3filename}
else
    echo "${inputfiles}" > ${inputfile_listfile}
    inputfile_count=1
fi

#output will be:
#${outputbase}_chaco_allref.npz
#${outputbase}_glassbrain_chaco_mean.png
#${outputbase}_glassbrain_chaco_smoothmean.png
#${outputbase}_glassbrain_lesion_orig.png

smoothedarg=""
smoothingfwhmarg=""
weightedarg=""
s3arg=""
if [ "${do_smoothing}" = "true" ]; then
    smoothedarg="--smoothed"
    smoothingfwhmarg="--smoothfwhm ${smoothfwhm}"
fi

if [ "${do_siftweights}" = "true" ]; then
    weightedarg="--weighted"
fi

if [ "x${s3nemoroot}" != "x" ]; then
    s3arg="--s3nemoroot ${s3nemoroot}"
fi

###########
#### need some kind of input/dimension checking HERE, or a way to send log output to end user

#copy latest version of the lesion script
aws s3 cp s3://kuceyeski-wcm-web-upload/nemo_scripts/nemo_lesion_to_chaco.py ${NEMODIR}/
aws s3 cp s3://kuceyeski-wcm-web-upload/nemo_scripts/nemo_save_average_glassbrain.py ${NEMODIR}/

outputdir=${HOME}/nemo_output_${s3filename_noext}
outputbase=${outputdir}/${origfilename_noext}_nemo_output
logfile=${outputbase}_${origtimestamp}_log.txt


############
#For copying data directly to an S3 bucket
s3direct_resultpath=s3://${s3direct_outputlocation}/${origfilename_noext}_nemo_output_${origtimestamp}/

mkdir -p $(dirname $outputbase)

echo "NeMo version ${nemo_version}" > ${logfile}
date --utc >> ${logfile}
cd ${NEMODIR}


#############
#create a lesion glassbrain image to feed back to web app for status update
input_lesion_image=${unzipdir}/glassbrain_lesion_orig_listmean.png
input_status_key=$(echo ${s3path} | sed -E 's#^[^/]+/##')${status_suffix}

#password must have worked if we got this far (or it wasn't using a password)
input_status_tagstring='password_status=success'

imgsize=$(python nemo_save_average_glassbrain.py ${input_lesion_image} --jet $(cat ${inputfile_listfile}))
if [ -e ${input_lesion_image} ]; then
    input_status_tagstring+="&input_checks=success&imgshape=${imgsize}"
else
    echo "fail" > ${input_lesion_image}
    input_status_tagstring+="&input_checks=error"
fi


#aws s3 cp ${input_lesion_image} s3://${s3path}${status_suffix}

aws s3api put-object --bucket ${inputbucket} --key ${input_status_key} --body ${input_lesion_image} --tagging ${input_status_tagstring}

#delete the input file from the s3 bucket
aws s3 rm s3://${s3path}

#############
finalstatus="success"
success_count=0
while read inputfile; do
    inputfile_noext=$(basename ${inputfile} | sed -E 's/(\.nii|\.nii\.gz)$//i')
    outputbase_infile=${outputdir}/${inputfile_noext}_nemo_output
    
    echo "##########################"  >> ${logfile}
    echo "# Processing " $(basename ${inputfile}) >> ${logfile}
    python nemo_lesion_to_chaco.py --lesion ${inputfile} \
        --outputbase ${outputbase_infile} \
        --chunklist nemo_chunklist.npz \
        --chunkdir chunkfiles \
        --refvol MNI152_T1_1mm_brain.nii.gz \
        --endpoints nemo_endpoints.npy \
        --asum nemo_Asum.npz \
        --asum_weighted nemo_Asum_weighted.npz \
        --trackweights nemo_siftweights.npy ${s3arg} ${weightedarg} ${smoothedarg} ${smoothingfwhmarg} >> ${logfile} 2>&1
    
    if [ ! -e ${outputbase_infile}_chaco_allref.npz ]; then
        echo "ChaCo output file not found!" >> ${logfile}
        #output file is missing! what happened? 
        #sudo shutdown -h now
        #exit 1
        finalstatus="error"
    else
        success_count=$((success_count+1))
    fi
    
    if [ "${output_allref}" = "false" ]; then
        rm -f ${outputbase_infile}_chaco_allref.npz
    fi
    
    if [ "${do_s3direct}"  = "1" ]; then
        #copy all data to a new s3 bucket
        aws s3 cp --recursive ${outputdir}/ ${s3direct_resultpath} --exclude "*" --include "${inputfile_noext}_*"
    fi
done < ${inputfile_listfile}

if [ "${success_count}" -gt "1" ]; then
    python nemo_save_average_glassbrain.py ${outputdir}/${origfilename_noext}_glassbrain_lesion_orig_listmean.png --jet $(cat ${inputfile_listfile})
    python nemo_save_average_glassbrain.py ${outputdir}/${origfilename_noext}_glassbrain_chaco_listmean.png $(ls ${outputdir}/*_chaco_mean.nii.gz)
    if [ "${do_smoothing}" = "true" ]; then
        smoothstr=$(basename $(ls ${outputdir}/*smooth*.png | head -n1) | tr "_" "\n" | grep -i smooth | tail -n1)
        python nemo_save_average_glassbrain.py ${outputdir}/${origfilename_noext}_glassbrain_chaco_${smoothstr}_listmean.png $(ls ${outputdir}/*_${smoothstr}_mean.nii.gz)
    fi
fi

if [ "${do_s3direct}"  = "1" ]; then
    endtime=$(date +%s)
    duration=$(echo "$endtime - $starttime" | bc -l)

    cd ${outputdir}
    ziplistfile=${outputbase}_ziplist.txt
    du -h * > ${ziplistfile}
    
    outputsize=$(du -hs ./ | awk '{print $1}')

    #copy any remaining files to s3 bucket
    aws s3 sync ./ ${s3direct_resultpath}
    
    #now copy files for email
    #(note: for the s3direct version, the filename isn't downloadable so it doesn't need to be .png or .zip or anything)
    #(It's just for tagging purposes, and forming the subject line in the email)
    outputfilename=${origfilename_noext}_nemo_output_${origtimestamp}
    outputkey_base=outputs/${origtimestamp}_${s3filename_noext}
    outputkey=${outputkey_base}/${outputfilename}
    
    if [ "${success_count}" -gt "1" ]; then
        aws s3 cp --recursive ./ s3://${outputbucket}/${outputkey_base}/ --exclude "*" --include "*_listmean.png" --include ${ziplistfile}
        outputfilename=$(ls *_listmean.png | head -n1)
    else
        aws s3 cp --recursive ./ s3://${outputbucket}/${outputkey_base}/ --exclude "*" --include "*.png" --include ${ziplistfile}
        outputfilename=$(ls *.png | head -n1)
    fi
    #outputkey=${outputkey_base}/${outputfilename}
    
    output_tagstring='email='${email}'&duration='${duration}'&status='${finalstatus}'&origfilename='${origfilename}'&inputfilecount='${inputfile_count}'&submittime='${origtimestamp_unix}
    output_tagstring+='&successcount='${success_count}'&inputfilecount_orig='${inputfile_count_orig}'&outputsize='${outputsize}'&resultlocation='${s3direct_resultpath}
    aws s3api put-object --bucket ${outputbucket} --key ${outputkey} --body ${outputfilename} --tagging ${output_tagstring}
else
    cd ${outputdir}
    outputfilename=${origfilename_noext}_nemo_output_${origtimestamp}.zip
    ziplistfile=${outputbase}_ziplist.txt
    du -h * > ${ziplistfile}
    zip ${outputfilename} * -x "*_ziplist.txt"

    outputsize=$(du -hs ${outputfilename} | awk '{print $1}')
    
    outputkey_base=outputs/${origtimestamp}_${s3filename_noext}
    outputkey=${outputkey_base}/${outputfilename}
    #aws s3 cp ${outputdir} s3://${outputbucket}/${outputkey}

    endtime=$(date +%s)
    duration=$(echo "$endtime - $starttime" | bc -l)

    if [ "${success_count}" -gt "1" ]; then
        aws s3 cp --recursive ./ s3://${outputbucket}/${outputkey_base}/ --exclude "*" --include "*_listmean.png" --include ${ziplistfile}
    else
        aws s3 cp --recursive ./ s3://${outputbucket}/${outputkey_base}/ --exclude "*" --include "*.png" --include ${ziplistfile}
    fi

    output_tagstring='email='${email}'&duration='${duration}'&status='${finalstatus}'&origfilename='${origfilename}'&inputfilecount='${inputfile_count}'&submittime='${origtimestamp_unix}
    output_tagstring+='&successcount='${success_count}'&inputfilecount_orig='${inputfile_count_orig}'&outputsize='${outputsize}
    aws s3api put-object --bucket ${outputbucket} --key ${outputkey} --body ${outputfilename} --tagging ${output_tagstring}
fi

sudo shutdown -h now
