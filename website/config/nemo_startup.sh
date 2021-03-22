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

tagfile=${HOME}/nemo_tags.json

instanceid=$(curl -sf http://169.254.169.254/latest/meta-data/instance-id)
region=$(curl --silent --fail http://169.254.169.254/latest/dynamic/instance-identity/document/ | grep region | cut -d\" -f4)
aws ec2 describe-tags --region $region --filter "Name=resource-id,Values=$instanceid" | jq --raw-output ".Tags[]" > ${tagfile}

#Download the config file and append it to the ec2 instance tags
s3path=$(jq --raw-output 'select(.Key=="s3path") | .Value' ${tagfile})
aws s3 cp s3://${s3path}_config.json $HOME/tmp_config.json
jq --raw-output '.[]' $HOME/tmp_config.json >> ${tagfile}
rm -f $HOME/tmp_config.json

#(note: there might be duplicates between instance tags and config, so take head -n1)
nemo_version=$(jq --raw-output 'select(.Key=="nemo_version") | .Value' ${tagfile} | head -n1)
nemo_version_date=$(jq --raw-output 'select(.Key=="nemo_version_date") | .Value' ${tagfile} | head -n1)
s3nemoroot=$(jq --raw-output 'select(.Key=="s3nemoroot") | .Value' ${tagfile} | head -n1)
s3configbucket=$(jq --raw-output 'select(.Key=="s3configbucket") | .Value' ${tagfile} | head -n1)
origfilename=$(jq --raw-output 'select(.Key=="filename") | .Value' ${tagfile} | head -n1)
origtimestamp=$(jq --raw-output 'select(.Key=="timestamp") | .Value' ${tagfile} | head -n1)
origtimestamp_unix=$(jq --raw-output 'select(.Key=="unixtime") | .Value' ${tagfile} | head -n1)
email=$(jq --raw-output 'select(.Key=="email") | .Value' ${tagfile} | head -n1)
output_allref=$(jq --raw-output 'select(.Key=="output_allref") | .Value' ${tagfile} | tr "[A-Z]" "[a-z]" | head -n1)
do_smoothing=$(jq --raw-output 'select(.Key=="smoothing") | .Value' ${tagfile} | head -n1)
do_siftweights=$(jq --raw-output 'select(.Key=="siftweights") | .Value' ${tagfile} | head -n1)
do_cumulative=$(jq --raw-output 'select(.Key=="cumulative") | .Value' ${tagfile} | head -n1)
smoothfwhm=$(jq --raw-output 'select(.Key=="smoothfwhm") | .Value' ${tagfile} | head -n1)
smoothmode=$(jq --raw-output 'select(.Key=="smoothmode") | .Value' ${tagfile} | head -n1)
s3direct_outputlocation=$(jq --raw-output 'select(.Key=="s3direct_outputlocation") | .Value' ${tagfile} | head -n1)
status_suffix=$(jq --raw-output 'select(.Key=="status_suffix") | .Value' ${tagfile} | head -n1)
output_prefix_list=$(jq --raw-output 'select(.Key=="output_prefix_list") | .Value' ${tagfile} | head -n1)
do_debug=$(jq --raw-output 'select(.Key=="debug") | .Value' ${tagfile} | head -n1)
tracking_algo=$(jq --raw-output 'select(.Key=="tracking_algorithm") | .Value' ${tagfile} | head -n1)
do_continuous=$(jq --raw-output 'select(.Key=="continuous") | .Value' ${tagfile} | head -n1)

smoothfwhm=$(echo $smoothfwhm 6 | awk '{print $1}')

inputbucket=$(echo $s3path | awk -F/ '{print $1}')
outputbucket=${inputbucket}

inputfile_maxcount=20
unzipdir=


#config_bucket="kuceyeski-wcm-web-upload"
#config_bucket="kuceyeski-wcm-web"
config_bucket=${s3configbucket}

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
    #make sure we ignore any hidden system files that got zipped up
    find ${unzipdir}/ -type f | grep -iE '\.nii(\.gz)?$' | grep -vE '(^\.|/\.|__MACOSX/)' | sort > ${inputfile_listfile}.tmp
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
smoothingmodearg=""
weightedarg=""
cumulativearg=""
continuousarg=""
debugarg=""
binarizearg="--binarize" #for glassbrain.py
s3arg=""
if [ "${do_smoothing}" = "true" ]; then
    smoothedarg="--smoothed"
    smoothingfwhmarg="--smoothfwhm ${smoothfwhm}"
    if [ "x${smoothmode}" != "x" ]; then
        smoothingmodearg="--smoothmode ${smoothmode}"
    fi
fi

if [ "${do_siftweights}" = "true" ]; then
    weightedarg="--weighted"
fi

if [ "${do_cumulative}" = "true" ]; then
    cumulativearg="--cumulative"
fi

if [ "${do_continuous}" = "true" ]; then
    continuousarg="--continuous_value"
    binarizearg=""
fi

if [ "${do_debug}" = "true" ]; then
    debugarg="--debug"
fi

if [ "x${s3nemoroot}" != "x" ]; then
    s3arg="--s3nemoroot ${s3nemoroot}"
fi

    
algostr=""

if [ "${tracking_algo}" = "ifod2act" ] || [ "x${tracking_algo}" = "x" ] ; then
    tracking_algo="ifod2act"
    algostr=""
elif [ "${tracking_algo}" = "sdstream" ]; then
    algostr="_sdstream"
else
    algostr="_${tracking_algo}"
fi

###########
#### need some kind of input/dimension checking HERE, or a way to send log output to end user

#copy latest version of the lesion script
if [ "${do_debug}" != "true" ]; then
    aws s3 cp s3://${config_bucket}/nemo_scripts/nemo_lesion_to_chaco.py ${NEMODIR}/
    aws s3 cp s3://${config_bucket}/nemo_scripts/nemo_save_average_glassbrain.py ${NEMODIR}/
else
    #aws s3 cp s3://${config_bucket}/nemo_scripts/nemo_lesion_to_chaco.py ${NEMODIR}/
    aws s3 cp s3://${config_bucket}/nemo_scripts/nemo_save_average_glassbrain.py ${NEMODIR}/
fi

outputdir=${HOME}/nemo_output_${s3filename_noext}
outputsuffix=nemo_output_${tracking_algo}
outputbasefile=${origfilename_noext}_${outputsuffix}
outputbase=${outputdir}/${outputbasefile}
logfile=${outputbase}_${origtimestamp}_log.txt


############
#For copying data directly to an S3 bucket
s3direct_resultpath=s3://${s3direct_outputlocation}/${origfilename_noext}_nemo_output_${origtimestamp}/

mkdir -p $(dirname $outputbase)

#print a nicer version of the tags to the output directory
output_config_file=${outputbase}_${origtimestamp}_config.json
output_config_s3file=s3://${outputbucket}/logs/${origtimestamp}_${s3filename_noext}_nemo_config.json
echo "{" $(jq '.Key' ${tagfile} | while read k; do echo "$k": $(jq 'select(.Key=='$k') | .Value' ${tagfile} | head -n1) ","; done) | sed -E 's#,[[:space:]]*$#}#' | jq '.' > ${output_config_file}
aws s3 cp ${output_config_file} ${output_config_s3file}

echo "NeMo version ${nemo_version}_${nemo_version_date}" > ${logfile}
date --utc >> ${logfile}
cd ${NEMODIR}

#############
# parse output space options (res, parc)

#atlaslist="aal cc200 cc400"

atlasdir=$HOME/nemo_atlases
atlaslistfile=${atlasdir}/atlas_list.csv

#aws s3 sync s3://${config_bucket}/nemo_atlases ${atlasdir} --exclude "*.npz"
aws s3 sync s3://${s3nemoroot}/nemo_atlases ${atlasdir} --exclude "*.npz"

pairwisearg=""
parcelarg=""
resolutionarg=""
output_pairwiselist=""
output_allreflist=""
output_roilistfile=""
parcfile_testsize_list=""

for o in $(echo ${output_prefix_list} | tr "," " "); do
    
    #file containing ROI definitions
    out_roilistfile="x"
    
    if [[ $o == addparc* ]]; then
        out_type="parc"
        #_name,_allref,_pairwise,_filekey?
        out_name=$(jq --raw-output 'select(.Key=="'${o}_name'") | .Value' ${tagfile} | head -n1)
        out_filekey=$(jq --raw-output 'select(.Key=="'${o}_filekey'") | .Value' ${tagfile} | head -n1)
        
        out_pairwise=$(jq --raw-output 'select(.Key=="'${o}_pairwise'") | .Value' ${tagfile} | head -n1)
        out_allref=$(jq --raw-output 'select(.Key=="'${o}_allref'") | .Value' ${tagfile} | head -n1)

        if [ "x${out_filekey}" != "x" ]; then
            out_filename=$(basename ${out_filekey})
            out_filepath=${unzipdir}/${out_filename}
            aws s3 cp s3://${inputbucket}/${out_filekey} ${out_filepath}
            if [ "${do_debug}" != "true" ]; then
                #delete custom uploaded parc file after downloading
                aws s3 rm s3://${inputbucket}/${out_filekey}
            fi
            parcarg_tmp="--parcelvol ${out_filepath}=${out_name}"
            parcfile_testsize_list+=" ${out_filepath}"
            
        else
            #need to search through available atlas files for the one specified by ${out_name}
            #and assign out_filename=atlases/thatfile.nii.gz

            out_lowername=$(echo ${out_name} | tr "[A-Z]" "[a-z]")
            atlasline=$(grep -E "^${out_lowername}," ${atlaslistfile})
            if [ "x${atlasline}" = "x" ]; then
                echo "Atlas not found: ${out_name}"
                exit 1
            fi
            out_filename=${atlasdir}/$(echo $atlasline | awk -F, '{print $2}')
            
            if [ ! -e ${out_filename} ]; then
                #so we don't have to copy the giant subject-specific files unless we need them
                #aws s3 cp s3://${config_bucket}/nemo_atlases/$(basename ${out_filename}) ${out_filename}
                aws s3 cp s3://${s3nemoroot}/nemo_atlases/$(basename ${out_filename}) ${out_filename}
            fi
            out_roilistfile=${atlasdir}/$(echo $atlasline | awk -F, '{print $3}')
            parcarg_tmp="--parcelvol ${out_filename}=${out_name}"
        fi
        if [ ${out_pairwise} = "false" ]; then
            parcarg_tmp+="?nopairwise"
        fi
        parcelarg+=" ${parcarg_tmp}"

    elif  [[ $o == addres* ]]; then
        out_type="res"
        #_res,_allref,_pairwise
        out_res=$(jq --raw-output 'select(.Key=="'${o}_res'") | .Value' ${tagfile} | head -n1)
        out_name="res${out_res}mm"
        out_pairwise=$(jq --raw-output 'select(.Key=="'${o}_pairwise'") | .Value' ${tagfile} | head -n1)
        out_allref=$(jq --raw-output 'select(.Key=="'${o}_allref'") | .Value' ${tagfile} | head -n1)
        
        resarg_tmp="--resolution ${out_res}=${out_name}"
        if [ ${out_pairwise} = "false" ]; then
            resarg_tmp+="?nopairwise"
        fi
        resolutionarg+=" ${resarg_tmp}"
    fi

    if [ "${out_pairwise}" = "true" ]; then
        pairwisearg="--pairwise"
    fi
    output_namelist+=" ${out_name}"
    output_pairwiselist+=" ${out_pairwise}"
    output_allreflist+=" ${out_allref}"
    output_roilistfile+=" ${out_roilistfile}"
done
#remember: pairwise should be set to "--pairwise" if ANY output asks for it

#############
#create a lesion glassbrain image to feed back to web app for status update
input_lesion_image=${unzipdir}/glassbrain_lesion_orig_listmean.png
input_status_key=$(echo ${s3path} | sed -E 's#^[^/]+/##')${status_suffix}

#password must have worked if we got this far (or it wasn't using a password)
input_status_tagstring='password_status=success'

input_check_status="success"

imgsize=$(python nemo_save_average_glassbrain.py --out ${input_lesion_image} --colormap jet ${binarizearg} $(cat ${inputfile_listfile}))
if [ -e ${input_lesion_image} ]; then
    input_status_tagstring+="&imgshape=${imgsize}"
else
    input_check_status="error"
    failmessage="Input lesion masks are not all the same dimensions"
fi

parcfile_testsize_expected="182x218x182 181x217x181"
for parctmp_file in ${parcfile_testsize_list}; do
    parctmp_image=${unzipdir}/parctmp_image.png
    parctmp_imgsize=$(python nemo_save_average_glassbrain.py --out ${parctmp_image} --colormap jet ${binarizearg} ${parctmp_file})
    rm -f ${unzipdir}/parctmp_image.png
    if [ -z "${parctmp_imgsize}" ]; then
        input_check_status="error"
        failmessage="Unable to determine dimensions of custom parcellation: $(basename $parctmp_file)"
        break
    else
        parctmp_imgsize_isvalid=$(echo ${parcfile_testsize_expected} | tr " " "\n" | grep ${parctmp_imgsize} | wc -l | awk '{print $1}')
        if [ "${parctmp_imgsize_isvalid}" != 1 ]; then
            input_check_status="error"
            failmessage="Invalid dimensions for custom parcellation: $(basename $parctmp_file)"
            break
        fi
    fi
done

if [ ${input_check_status} = "success" ]; then
    input_status_tagstring+="&input_checks=${input_check_status}"
else
    echo "fail" > ${input_lesion_image}
    input_status_tagstring+="&input_checks=${input_check_status}"
fi

#aws s3 cp ${input_lesion_image} s3://${s3path}${status_suffix}

aws s3api put-object --bucket ${inputbucket} --key ${input_status_key} --body ${input_lesion_image} --tagging ${input_status_tagstring}

#delete the input file from the s3 bucket
if [ "${do_debug}" != "true" ]; then
    aws s3 rm s3://${s3path}
fi

if [ ${input_check_status} != "success" ]; then
    #if we failed input checks, don't proceed
    if [ "${do_debug}" != "true" ]; then
        sudo shutdown -h now
    else
        exit 0
    fi
fi


#############

ziplistfile=${outputdir}/output_ziplist.txt
ziplistfile_bytes=${outputdir}/output_bytes_ziplist.txt

finalstatus="success"
success_count=0
while read inputfile; do
    inputfile_noext=$(basename ${inputfile} | sed -E 's/(\.nii|\.nii\.gz)$//i')
    outputbase_infile=${outputdir}/${inputfile_noext}_${outputsuffix}
    
    echo "##########################"  >> ${logfile}
    echo "# Processing " $(basename ${inputfile}) >> ${logfile}
    python nemo_lesion_to_chaco.py --lesion ${inputfile} \
        --outputbase ${outputbase_infile} \
        --chunklist nemo${algostr}_chunklist.npz \
        --chunkdir chunkfiles${algostr} \
        --refvol MNI152_T1_1mm_brain.nii.gz \
        --endpoints nemo${algostr}_endpoints.npy \
        --asum nemo${algostr}_Asum_endpoints.npz \
        --asum_weighted nemo${algostr}_Asum_weighted_endpoints.npz \
        --asum_cumulative nemo${algostr}_Asum_cumulative.npz \
        --asum_weighted_cumulative nemo${algostr}_Asum_weighted_cumulative.npz \
        --trackweights nemo${algostr}_siftweights.npy \
        --tracklengths nemo${algostr}_tracklengths.npy \
        --tracking_algorithm "${tracking_algo}" ${s3arg} ${weightedarg} ${cumulativearg} ${continuousarg} ${pairwisearg} \
            ${parcelarg} ${resolutionarg} ${smoothedarg} ${smoothingfwhmarg} ${smoothingmodearg} ${debugarg} >> ${logfile} 2>&1
    
    #if [ ! -e ${outputbase_infile}_chaco_allref.npz ]; then
    if [ $(ls ${outputbase_infile}_*.pkl 2>/dev/null | wc -l ) = 0 ]; then
        echo "ChaCo output file not found!" >> ${logfile}
        #output file is missing! what happened? 
        #sudo shutdown -h now
        #exit 1
        #depending on where we encountered an error, the temporary directory
        #for this input file may not have been removed
        subjtempdir=$(ls -d ${outputbase_infile}_tmp*/ 2>/dev/null)
        if [ -d "${subjtempdir}" ]; then
            rm -rf ${subjtempdir}
        fi
        finalstatus="error"
    else
        success_count=$((success_count+1))
    fi
    
    o=0
    for out_name in ${output_namelist}; do
        o=$((o+1))
        out_pairwise=$(echo ${output_pairwiselist} | cut -d" " -f$o)
        out_allref=$(echo ${output_allreflist} | cut -d" " -f$o)
        if [ "${out_allref}" = "false" ]; then
            rm -f ${outputbase_infile}_chacovol_${out_name}_allref.pkl
            rm -f ${outputbase_infile}_chacovol_${out_name}_allref_denom.pkl
            rm -f ${outputbase_infile}_chacoconn_${out_name}_allref.pkl
            rm -f ${outputbase_infile}_chacoconn_${out_name}_allref_denom.pkl
        fi
        if [ "${out_pairwise}" = "false" ]; then
            rm -f ${outputbase_infile}_chacoconn_${out_name}_allref.pkl
            rm -f ${outputbase_infile}_chacoconn_${out_name}_allref_denom.pkl
            rm -f ${outputbase_infile}_chacoconn_${out_name}_mean.pkl
            rm -f ${outputbase_infile}_chacoconn_${out_name}_stdev.pkl
        fi
    done

    if [ "${do_s3direct}"  = "1" ]; then
        #copy all data to a new s3 bucket
        aws s3 cp --recursive ${outputdir}/ ${s3direct_resultpath} --exclude "*" --include "${inputfile_noext}_*"
        #update ziplistfile as we go, so we can delete files as we go
        (cd ${outputdir} && du -h --apparent-size ${inputfile_noext}_* >> ${ziplistfile} )
        (cd ${outputdir} && du -b ${inputfile_noext}_* >> ${ziplistfile_bytes} )
        #delete everything for this lesion mask except mean nifti and png (needed for listmean possibly and for upload)
        ls ${outputdir}/${inputfile_noext}_* | grep -vE '(mean.nii.gz|.png|.json|_log.txt)$' | xargs rm -f
    fi
done < ${inputfile_listfile}

if [ "${success_count}" -gt "1" ]; then
    python nemo_save_average_glassbrain.py --out ${outputdir}/${origfilename_noext}_glassbrain_lesion_orig_listmean.png --colormap jet ${binarizearg} $(cat ${inputfile_listfile})
    for out_name in ${output_namelist}; do
        outfile_meanlist=$(ls ${outputdir}/*_chacovol_${out_name}_mean.nii.gz 2>/dev/null)
        if [ "x${outfile_meanlist}" = "x" ]; then
            continue
        fi
        python nemo_save_average_glassbrain.py --out ${outputdir}/${origfilename_noext}_glassbrain_chacovol_${out_name}_listmean.png ${outfile_meanlist}
        if [ "${do_smoothing}" = "true" ]; then
            smoothstr=$(basename $(ls ${outputdir}/*_${out_name}_smooth*.png 2>/dev/null | head -n1) 2>/dev/null | tr "_" "\n" | grep -i smooth | tail -n1)
            outfile_meanlist=$(ls ${outputdir}/*_${out_name}_${smoothstr}_mean.nii.gz 2>/dev/null)
            if [ "x${outfile_meanlist}" = "x" ] || [ "${smoothstr}" = "x" ]; then
                continue
            fi
            python nemo_save_average_glassbrain.py --out ${outputdir}/${origfilename_noext}_glassbrain_chacovol_${out_name}_${smoothstr}_listmean.png ${outfile_meanlist}
        fi
    done
fi


#copy ROI label definitions to output folder (if requested)
o=0
for out_name in ${output_namelist}; do
    o=$((o+1))
    out_roilistfile=$(echo ${output_roilistfile} | cut -d" " -f$o)
    if [ "${out_roilistfile}" = "x" ]; then
        continue
    fi
    cp -f ${out_roilistfile} ${outputdir}/
done

#save subject list to file in output directory:
python -c 'import numpy as np; chunklist=np.load("'nemo${algostr}_chunklist.npz'"); [print(x) for x in chunklist["subjects"]]' > ${outputdir}/nemo_hcp_reference_subjects.txt

uploadjson=${outputbase}_upload_info.json
echo "{}" > ${uploadjson}

##########################################################################################
##########################################################################################
#copy output directly to S3 or zip and upload to website
if [ "${do_s3direct}"  = "1" ]; then
    cd ${outputdir}
    du -h --apparent-size * >> ${ziplistfile}
    sort -uk2 ${ziplistfile} > ${ziplistfile}.tmp && mv ${ziplistfile}.tmp ${ziplistfile}
    grep -vE '_upload_info.json$' ${ziplistfile} > ${ziplistfile}.tmp && mv ${ziplistfile}.tmp ${ziplistfile}
    grep -vE $(basename ${ziplistfile})'$' ${ziplistfile} | grep -vE $(basename ${ziplistfile_bytes})'$' > ${ziplistfile}.tmp && mv ${ziplistfile}.tmp ${ziplistfile}
    
    #outputsize=$(du -hs ./ | awk '{print $1}')
    outputsize_bytes=$(sort -uk2 ${ziplistfile_bytes} | awk 'BEGIN{a=0}{a+=$1}END{print a}')
    #  if(a>1024*1024*1024}')
    outputsize=$(echo ${outputsize_bytes} | awk '{if($1>1024*1024*1024){printf "%.1fG",$1/(1024*1024*1024)} else if($1>1024*1024){printf "%.1fM",$1/(1024*1024)} else if($1>1024){printf "%.1fK",$1/(1024)} else {print $1}}')
    rm -f ${ziplistfile_bytes}
    outputsize_unzipped=""

    endtime=$(date +%s)
    duration=$(echo "$endtime - $starttime" | bc -l)

    #copy any remaining files to s3 bucket
    aws s3 sync ./ ${s3direct_resultpath} --exclude "*_ziplist.txt" --exclude "*_upload_info.json"
    
    #now copy files for email
    #(note: for the s3direct version, the filename isn't downloadable so it doesn't need to be .png or .zip or anything)
    #(It's just for tagging purposes, and forming the subject line in the email)
    outputfilename=${outputbasefile}_${origtimestamp}
    outputkey_base=outputs/${origtimestamp}_${s3filename_noext}
    outputkey=${outputkey_base}/${outputfilename}
    
    #add the s3 output location for internal direct s3 copy mode
    jq --arg resultlocation "${s3direct_resultpath}" '.+{resultlocation:$resultlocation}' < ${uploadjson} > ${uploadjson}.tmp && mv ${uploadjson}.tmp ${uploadjson}
    
    #for s3direct, output body to copy should just be something small like the main png (since it's only used to trigger)
    outputfilename=$(ls *.png | head -n1)
else
    cd ${outputdir}
    outputfilename=${outputbasefile}_${origtimestamp}.zip
    rm -f ${outputfilename}
    du -h --apparent-size * > ${ziplistfile}
    grep -vE '_upload_info.json$' ${ziplistfile} > ${ziplistfile}.tmp && mv ${ziplistfile}.tmp ${ziplistfile}
    
    outputsize_unzipped=$(du -hs ./ | awk '{print $1}')
    zip ${outputfilename} * -x "*_ziplist.txt" -x "*_upload_info.json"

    endtime=$(date +%s)
    duration=$(echo "$endtime - $starttime" | bc -l)
    
    outputsize=$(du -hs ${outputfilename} | awk '{print $1}')
    
    outputkey_base=outputs/${origtimestamp}_${s3filename_noext}
    outputkey=${outputkey_base}/${outputfilename}
    
    #we can't upload >5GB using aws s3api put-object, which is the only way to including tagging AND trigger lambda,
    #so upload the output zip first, then we'll upload a dummy file later with tagging info 
    aws s3 cp ${outputfilename}  s3://${outputbucket}/${outputkey}
    
fi

#build a json file with info we will need to send the email
jq --arg email "${email}" --arg duration "${duration}" --arg status "${finalstatus}" --arg origfilename "${origfilename}" \
    --arg inputfilecount "${inputfile_count}" --arg submittime "${origtimestamp_unix}" --arg successcount "${success_count}" \
    --arg inputfilecount_orig "${inputfile_count_orig}" --arg outputsize "${outputsize}" --arg outputsize_unzipped "${outputsize_unzipped}" \
    --arg outputfile_key "${outputkey}" \
    '.+{email:$email, duration:$duration, status:$status, origfilename:$origfilename, inputfilecount:$inputfilecount,
    submittime:$submittime, successcount:$successcount, inputfilecount_orig:$inputfilecount_orig, outputsize:$outputsize,
    outputsize_unzipped:$outputsize_unzipped, outputfile_key:$outputfile_key
    }' < ${uploadjson} > ${uploadjson}.tmp && mv ${uploadjson}.tmp ${uploadjson}


if [ "${success_count}" -gt "1" ]; then
    aws s3 cp --recursive ./ s3://${outputbucket}/${outputkey_base}/ --exclude "*" --include "*_listmean.png" --include ${ziplistfile} --include ${uploadjson}
else
    aws s3 cp --recursive ./ s3://${outputbucket}/${outputkey_base}/ --exclude "*" --include "*.png" --include ${ziplistfile} --include ${uploadjson}
fi

output_tagstring="email=${email}"
#aws s3api put-object --bucket ${outputbucket} --key ${outputkey} --body ${outputfilename} --tagging ${output_tagstring}
aws s3api put-object --bucket ${outputbucket} --key ${outputkey_base}/upload_trigger --body ${uploadjson} --tagging ${output_tagstring}

#######################################
#add final status, duration, and output path to updated log on s3
#(note: put quotes around each jq value in case they have spaces)
finaljson=${output_config_file}_final.json
output_expiration=$(aws s3api head-object --bucket ${outputbucket} --key ${outputkey_base}/upload_trigger | jq --raw-output ".Expiration // empty" | sed -E 's#expiry-date=\"([^\"]+)\".+$#\1#')

if [ "${do_s3direct}"  = "1" ]; then
    output_expiration=""
fi
jq -s --arg s3result_expiration "${output_expiration}" '.[0]+.[1]+{s3result_expiration:$s3result_expiration}' ${output_config_file} ${uploadjson} > ${finaljson}

aws s3 cp ${finaljson} ${output_config_s3file}
aws s3 cp ${logfile} s3://${outputbucket}/logs/${origtimestamp}_${s3filename_noext}_nemo_log.txt

if [ "${do_debug}" != "true" ]; then
    sudo shutdown -h now
fi
