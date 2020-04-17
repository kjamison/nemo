#!/bin/bash

#dont want exit on error because we wont terminate!
#set -e 
set -x

if [ -e $HOME/fsl ]; then
        export FSLDIR=$HOME/fsl
        export PATH=$FSLDIR/bin:$PATH
fi

export PATH=/home/ubuntu/anaconda3/bin:$PATH
export PATH=/home/ubuntu/bin:$PATH

env

starttime=$(date +%s)

instanceid=$(curl -sf http://169.254.169.254/latest/meta-data/instance-id)
region=$(curl --silent --fail http://169.254.169.254/latest/dynamic/instance-identity/document/ | grep region | cut -d\" -f4)
aws ec2 describe-tags --region $region --filter "Name=resource-id,Values=$instanceid" > $HOME/nemo_tags.txt

s3path=$(jq --raw-output '.Tags[] | select(.Key=="s3path") | .Value' $HOME/nemo_tags.txt)

outputbucket=$(echo $s3path | awk -F/ '{print $1}')

origfilename=$(jq --raw-output '.Tags[] | select(.Key=="filename") | .Value' $HOME/nemo_tags.txt)
email=$(jq --raw-output '.Tags[] | select(.Key=="email") | .Value' $HOME/nemo_tags.txt)
output_allref=$(jq --raw-output '.Tags[] | select(.Key=="output_allref") | .Value' $HOME/nemo_tags.txt | tr "[A-Z]" "[a-z]")
smoothfwhm=$(jq --raw-output '.Tags[] | select(.Key=="smoothfwhm") | .Value' $HOME/nemo_tags.txt)
smoothfwhm=$(echo $smoothfwhm 6 | awk '{print $1}')

s3filename=$(basename $s3path)

aws s3 cp s3://${s3path} $HOME/${s3filename}

#delete the input file from the s3 bucket
aws s3 rm s3://${s3path}

s3lower=$(echo $s3filename | tr "[A-Z]" "[a-z]")
case ${s3lower} in 
    *.nii|*.nii.gz)
        inputfile=$HOME/${s3filename}
        ;;
    *.zip)
        echo "zip not supported"
        exit 1
        ;;
    *.tar)
        echo "tar not supported"
        exit 1
        ;;
    *.tar.gz)
        echo "tar.gz not supported"
        exit 1
        ;;
    *)
esac

s3filename_noext=$(echo ${s3filename} | sed -E 's/(\.nii|\.nii\.gz|\.zip|\.tar|\.tar\.gz)$//i')
origfilename_noext=$(echo ${origfilename} | sed -E 's/(\.nii|\.nii\.gz|\.zip|\.tar|\.tar\.gz)$//i')

outputdir=${HOME}/nemo_output_${s3filename_noext}
outputbase=${outputdir}/${origfilename_noext}_nemo_output

mkdir -p $(dirname $outputbase)

#output will be:
#${outputbase}_chaco_allref.npz
#${outputbase}_glassbrain_chaco_mean.png
#${outputbase}_glassbrain_chaco_smoothmean.png
#${outputbase}_glassbrain_lesion_orig.png

cd $HOME/nemo2

weightedarg="--weighted"
smoothedarg="--smoothed"
smoothingfwhmarg="--smoothfwhm ${smoothfwhm}"
###########
#### need some kind of input/dimension checking HERE, or a way to send log output to end user

#copy latest version of the lesion script
aws s3 cp s3://kuceyeski-wcm-web-upload/nemo_scripts/nemo_lesion_to_chaco.py ./

python nemo_lesion_to_chaco.py --lesion ${inputfile} \
    --outputbase ${outputbase} \
    --chunklist nemo_chunklist.npz \
    --chunkdir chunkfiles \
    --refvol MNI152_T1_1mm_brain.nii.gz \
    --endpoints nemo_endpoints.npy \
    --asum nemo_Asum.npz \
    --asum_weighted nemo_Asum_weighted.npz \
    --trackweights nemo_siftweights.npy ${weightedarg} ${smoothedarg} ${smoothingfwhmarg}  2>&1 > ${outputbase}_log.txt

finalstatus="success"
if [ ! -e ${outputbase}_chaco_allref.npz ]; then
    echo "ChaCo output file not found!" >> ${outputbase}_log.txt
    #output file is missing! what happened? 
    #sudo shutdown -h now
    #exit 1
    finalstatus="error"
fi

#aws s3 sync ${outputdir} s3://${outputbucket}/outputs/${s3filename_noext}

cd ${outputdir}
outputfilename=${origfilename_noext}_nemo_output.zip

if [ "${output_allref}" = "false" ]; then
    rm -f ${outputbase}_chaco_allref.npz
fi
zip ${outputfilename} *

outputkey_base=outputs/${s3filename_noext}
outputkey=${outputkey_base}/${outputfilename}
#aws s3 cp ${outputdir} s3://${outputbucket}/${outputkey}

endtime=$(date +%s)
duration=$(echo "$endtime - $starttime" | bc -l)

aws s3 sync ./ s3://${outputbucket}/${outputkey_base}/ --exclude "*" --include "*.png"
aws s3api put-object --bucket ${outputbucket} --key ${outputkey} --body ${outputfilename} --tagging 'email='${email}'&duration='${duration}'&status='${finalstatus}'&origfilename='${origfilename}''

sudo shutdown -h now
