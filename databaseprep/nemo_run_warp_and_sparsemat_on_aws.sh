#!/bin/bash

set -e 
set -x

subj=$1
algo=$2
mnitracksdir=$3

#try to stop python/numpy from secretly using extra cores sometimes
export OPENBLAS_NUM_THREADS=1
export MKL_NUM_THREADS=1

scriptdir=/home/ubuntu

mkdir -p ${mnitracksdir}
subjdir=${mnitracksdir}/mnitracks_${subj}_${algo}

numtracks=5M

bash ${scriptdir}/run_warp_tck_to_mni.sh $subj $algo ${subjdir}

python ${scriptdir}/nemo_convert_mni_tck_to_sparsemat.py ${subjdir}/CSD_${algo}_${numtracks} ${subjdir}/MNI152_T1_1mm_brain_mask.nii.gz ${subjdir}/${subj}_${algo}_${numtracks}_MNI_sparsemat.mat

mv ${subjdir}/CSD_${algo}_${numtracks}_MNI_tdi.nii.gz ${subjdir}/${subj}_${algo}_${numtracks}_MNI_tdi.nii.gz 

aws s3 sync ${subjdir}/ s3://kuceyeski-wcm-temp/kwj2001/mnitracks/$(basename $subjdir)/ --exclude "*" --include "*sparsemat.mat" --include "*_MNI_tdi.nii.gz"

cd $HOME
rm -rf $subjdir

